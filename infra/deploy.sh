#!/usr/bin/env bash
# One command: build the committed code in the cloud and run it on App Runner.
#
#   AWS credentials in the environment (any normal AWS CLI setup), then:
#     BUDGET_EMAIL=you@example.com infra/deploy.sh --yes
#
# What it does, in order (re-running it is safe; each step is idempotent):
#   1. refuses a dirty working tree - what runs is exactly `git rev-parse HEAD`;
#   2. phase 1 stack (DeployService=false): ECR repo, S3 source bucket, CodeBuild, IAM,
#      Budget - only when the service does not exist yet;
#   3. image: tag git-<sha12>; if ECR already has it, reuse it; otherwise
#      `git archive HEAD` -> S3 -> CodeBuild -> ECR (immutable tag);
#   4. phase 2 stack (DeployService=true, ImageDigest=<digest>): the App Runner service
#      at min=max=1 plus metric filters, alarms, dashboard; CloudFormation waits until
#      the service is RUNNING;
#   5. sets log retention on the two log groups App Runner creates;
#   6. smoke: GET / and GET /healthz must be 200 (plus GET /api/demo, a free route).
# Prints the service URL, the image digest and how long each stage took.
#
# Tunables (env, with defaults): AWS_REGION=us-east-1, SERVICE_NAME=stepspotter-opencv,
# STACK_NAME=$SERVICE_NAME, ALERT_TOPIC_ARN (empty = stack makes its own topic and
# subscribes ALERT_EMAIL), CPU="1 vCPU", MEMORY="2 GB", PAUSED=0, JOBS_PER_IP_HOUR=6,
# PHOTOS_PER_IP_HOUR=30, MAX_JOBS_PER_DAY=20, MAX_PHOTOS_PER_DAY=80, BUDGET_LIMIT_USD=20,
# USE_APP_INFERENCE_PROFILE=true, PERCEPTION_P95_ALARM_MS=2000.
set -euo pipefail

REGION="${AWS_REGION:-${AWS_DEFAULT_REGION:-us-east-1}}"
export AWS_REGION="$REGION" AWS_DEFAULT_REGION="$REGION" AWS_PAGER=""
SERVICE_NAME="${SERVICE_NAME:-stepspotter-opencv}"
STACK_NAME="${STACK_NAME:-$SERVICE_NAME}"
CPU="${CPU:-1 vCPU}"
MEMORY="${MEMORY:-2 GB}"
PAUSED="${PAUSED:-0}"
JOBS_PER_IP_HOUR="${JOBS_PER_IP_HOUR:-6}"
PHOTOS_PER_IP_HOUR="${PHOTOS_PER_IP_HOUR:-30}"
MAX_JOBS_PER_DAY="${MAX_JOBS_PER_DAY:-20}"
MAX_PHOTOS_PER_DAY="${MAX_PHOTOS_PER_DAY:-80}"
BUDGET_LIMIT_USD="${BUDGET_LIMIT_USD:-20}"
USE_APP_INFERENCE_PROFILE="${USE_APP_INFERENCE_PROFILE:-true}"
PERCEPTION_P95_ALARM_MS="${PERCEPTION_P95_ALARM_MS:-2000}"
LOG_RETENTION_DAYS="${LOG_RETENTION_DAYS:-14}"
ALERT_TOPIC_ARN="${ALERT_TOPIC_ARN:-}"
ALERT_EMAIL="${ALERT_EMAIL:-}"

ROOT="$(git rev-parse --show-toplevel)"
TEMPLATE="$ROOT/infra/template.yaml"
cd "$ROOT"

say() { printf '%s  %s\n' "$(date -u +%H:%M:%SZ)" "$*"; }
die() { say "ERROR: $*" >&2; exit 1; }
now() { date -u +%s; }

for tool in aws git curl python3; do command -v "$tool" >/dev/null || die "$tool is not installed"; done
# It creates billable resources, so it never runs by accident (a stray copy-paste, a
# shell history search): the spend is acknowledged on the command line, every time.
[ "${1:-}" = "--yes" ] || die "this builds and runs a billable service (≈\$0.34/day idle at 1 vCPU / 2 GB, see docs/DEPLOY.md); run: $0 --yes"

# 1 ---------------------------------------------------------------- what runs = HEAD
case "$SERVICE_NAME" in
  stepspotter|stepspotter-guide|fleetmemory*) die "refusing: '$SERVICE_NAME' is a frozen deployment" ;;
esac
if [ -n "$(git status --porcelain)" ]; then
  git status --short >&2
  die "working tree is dirty - commit or stash first; the image is built from HEAD only"
fi
SHA="$(git rev-parse HEAD)"
TAG="git-${SHA:0:12}"

ACCOUNT="$(aws sts get-caller-identity --query Account --output text)"
[ -n "${BUDGET_EMAIL:-}" ] || die "set BUDGET_EMAIL (receives the 80 % Budget alert)"
[ -n "$ALERT_TOPIC_ARN" ] || [ -n "$ALERT_EMAIL" ] || die "set ALERT_TOPIC_ARN (existing SNS topic) or ALERT_EMAIL (the stack makes a topic)"
say "account $ACCOUNT  region $REGION  stack $STACK_NAME  commit $SHA"

aws cloudformation validate-template --template-body "file://$TEMPLATE" >/dev/null
say "template valid"

stack_status() {
  aws cloudformation describe-stacks --stack-name "$STACK_NAME" \
    --query 'Stacks[0].StackStatus' --output text 2>/dev/null || echo NONE
}
stack_param() {
  aws cloudformation describe-stacks --stack-name "$STACK_NAME" \
    --query "Stacks[0].Parameters[?ParameterKey=='$1'].ParameterValue | [0]" --output text 2>/dev/null || echo ""
}
stack_output() {
  aws cloudformation describe-stacks --stack-name "$STACK_NAME" \
    --query "Stacks[0].Outputs[?OutputKey=='$1'].OutputValue | [0]" --output text
}

deploy_stack() {  # $1 = DeployService, $2 = ImageDigest
  aws cloudformation deploy \
    --stack-name "$STACK_NAME" \
    --template-file "$TEMPLATE" \
    --capabilities CAPABILITY_NAMED_IAM \
    --no-fail-on-empty-changeset \
    --tags "project=$SERVICE_NAME" \
    --parameter-overrides \
      "ServiceName=$SERVICE_NAME" \
      "DeployService=$1" \
      "ImageDigest=$2" \
      "ImageArch=amd64" \
      "Cpu=$CPU" \
      "Memory=$MEMORY" \
      "AlertTopicArn=$ALERT_TOPIC_ARN" \
      "AlertEmail=$ALERT_EMAIL" \
      "BudgetEmail=$BUDGET_EMAIL" \
      "BudgetLimitUsd=$BUDGET_LIMIT_USD" \
      "UseAppInferenceProfile=$USE_APP_INFERENCE_PROFILE" \
      "Paused=$PAUSED" \
      "JobsPerIpHour=$JOBS_PER_IP_HOUR" \
      "PhotosPerIpHour=$PHOTOS_PER_IP_HOUR" \
      "MaxJobsPerDay=$MAX_JOBS_PER_DAY" \
      "MaxPhotosPerDay=$MAX_PHOTOS_PER_DAY" \
      "PerceptionP95AlarmMs=$PERCEPTION_P95_ALARM_MS" \
      "LogRetentionDays=$LOG_RETENTION_DAYS"
}

# 2 ---------------------------------------------------------------- build infrastructure
T0=$(now)
STATUS="$(stack_status)"
case "$STATUS" in
  *IN_PROGRESS) die "stack is $STATUS - wait for it to finish" ;;
  ROLLBACK_COMPLETE) die "stack is ROLLBACK_COMPLETE (first create failed); run infra/destroy.sh --yes, fix, re-run" ;;
esac
if [ "$STATUS" = NONE ] || [ "$(stack_param DeployService)" != "true" ]; then
  say "phase 1: build infrastructure (no service yet)"
  deploy_stack false ""
fi
T1=$(now)
REPO_NAME="$(stack_output RepositoryName)"
BUCKET="$(stack_output SourceBucketName)"
PROJECT="$(stack_output BuildProjectName)"

# 3 ---------------------------------------------------------------- image
image_digest() {
  aws ecr describe-images --repository-name "$REPO_NAME" --image-ids "imageTag=$TAG" \
    --query 'imageDetails[0].imageDigest' --output text 2>/dev/null || true
}
DIGEST="$(image_digest)"
BUILD_SECONDS=0
if [[ "$DIGEST" == sha256:* ]]; then
  say "image $TAG already in ECR ($DIGEST) - not rebuilding"
else
  ZIPDIR="$(mktemp -d)"
  trap 'rm -rf "${ZIPDIR:?}"' EXIT
  ZIP="$ZIPDIR/src.zip"
  git archive --format=zip --output="$ZIP" HEAD
  KEY="source/$TAG.zip"
  aws s3 cp --only-show-errors "$ZIP" "s3://$BUCKET/$KEY"
  say "source $KEY uploaded ($(wc -c <"$ZIP" | tr -d ' ') bytes); starting CodeBuild"
  B0=$(now)
  BUILD_ID="$(aws codebuild start-build --project-name "$PROJECT" \
    --source-type-override S3 --source-location-override "$BUCKET/$KEY" \
    --environment-variables-override "name=IMAGE_TAG,value=$TAG,type=PLAINTEXT" \
    --query 'build.id' --output text)"
  while :; do
    BSTATUS="$(aws codebuild batch-get-builds --ids "$BUILD_ID" --query 'builds[0].buildStatus' --output text)"
    [ "$BSTATUS" = IN_PROGRESS ] || break
    sleep 15
  done
  BUILD_SECONDS=$(( $(now) - B0 ))
  if [ "$BSTATUS" != SUCCEEDED ]; then
    # shellcheck disable=SC2016  # backticks are a JMESPath literal, not shell
    aws codebuild batch-get-builds --ids "$BUILD_ID" \
      --query 'builds[0].{phases:phases[?phaseStatus!=`SUCCEEDED`].[phaseType,phaseStatus,contexts[0].message],logs:logs.deepLink}' >&2
    die "CodeBuild $BUILD_ID ended $BSTATUS after ${BUILD_SECONDS}s"
  fi
  DIGEST="$(image_digest)"
  [[ "$DIGEST" == sha256:* ]] || die "build said SUCCEEDED but ECR has no $TAG"
  say "built $TAG in ${BUILD_SECONDS}s -> $DIGEST"
fi

# 4 ---------------------------------------------------------------- service
say "phase 2: service on $DIGEST (CloudFormation waits for RUNNING)"
S0=$(now)
deploy_stack true "$DIGEST"
SERVICE_SECONDS=$(( $(now) - S0 ))
URL="$(stack_output ServiceUrl)"
ARN="$(stack_output ServiceArn)"
SID="$(stack_output ServiceId)"
RUNNING="$(aws apprunner describe-service --service-arn "$ARN" --query 'Service.Status' --output text)"
[ "$RUNNING" = RUNNING ] || die "service status is $RUNNING"
LIVE_IMAGE="$(aws apprunner describe-service --service-arn "$ARN" \
  --query 'Service.SourceConfiguration.ImageRepository.ImageIdentifier' --output text)"
[[ "$LIVE_IMAGE" == *"@$DIGEST" ]] || die "service runs $LIVE_IMAGE, expected @$DIGEST"

# 5 ---------------------------------------------------------------- log retention
for kind in service application; do
  LG="/aws/apprunner/$SERVICE_NAME/$SID/$kind"
  if aws logs put-retention-policy --log-group-name "$LG" --retention-in-days "$LOG_RETENTION_DAYS" 2>/dev/null; then
    say "retention ${LOG_RETENTION_DAYS}d on $LG"
  else
    say "WARN: could not set retention on $LG (not created yet?) - re-run deploy.sh later"
  fi
done

# 6 ---------------------------------------------------------------- smoke
SMOKE_FAIL=0
probe() {  # $1 path, $2 expected code
  local out code secs
  out="$(curl -s -o /dev/null -w '%{http_code} %{time_total}' --max-time 30 "$URL$1" || echo "000 0")"
  code="${out%% *}"; secs="${out##* }"
  if [ "$code" = "$2" ]; then say "smoke  GET $1  -> $code in ${secs}s  OK"
  else say "smoke  GET $1  -> $code in ${secs}s  EXPECTED $2"; SMOKE_FAIL=1; fi
}
probe / 200
probe /healthz 200
probe /api/demo 200
# A perception-only route, if this build has one (looked up, never guessed).
PERC="$(curl -s --max-time 15 "$URL/openapi.json" | python3 -c \
  'import json,sys
try: d=json.load(sys.stdin)
except Exception: sys.exit(0)
print(" ".join(p for p in d.get("paths",{}) if "percep" in p or "inspect" in p))' || true)"
if [ -n "$PERC" ]; then say "perception routes in this build: $PERC (exercise them with docs/DEPLOY.md section Smoke)"
else say "no perception-only route in this build"; fi

# Is the Budget able to see this stack's spend yet?
TAG_STATE="$(aws ce list-cost-allocation-tags --tag-keys project --query 'CostAllocationTags[0].Status' --output text 2>/dev/null || echo unknown)"
[ "$TAG_STATE" = Active ] || say "NOTE: cost allocation tag 'project' is '$TAG_STATE' - the Budget filters on it; see docs/DEPLOY.md section Budget"

cat <<EOF

  service URL    $URL
  image          $(stack_output RepositoryUri)@$DIGEST  ($TAG)
  dashboard      $(stack_output DashboardName)   https://$REGION.console.aws.amazon.com/cloudwatch/home?region=$REGION#dashboards/dashboard/$(stack_output DashboardName)
  app logs       $(stack_output ApplicationLogGroup)
  model          $(stack_output ModelInUse)
  durations      infra $((T1 - T0))s  build ${BUILD_SECONDS}s  service ${SERVICE_SECONDS}s  total $(( $(now) - T0 ))s
EOF
[ "$SMOKE_FAIL" = 0 ] || die "smoke failed"
