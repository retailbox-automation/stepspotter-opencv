#!/usr/bin/env bash
# Remove everything infra/deploy.sh created, and nothing else.
#
#   infra/destroy.sh --yes
#
# Deletes: the CloudFormation stack (App Runner service, scaling config, ECR repo with
# its images, S3 source bucket, CodeBuild project + its log group, IAM roles, inference
# profile, metric filters, alarms, dashboard, Budget, and the SNS topic if the stack made
# one), after emptying the source bucket; then the two log groups App Runner itself
# created for this service (/aws/apprunner/<service>/<service-id>/{service,application}),
# matched by exact name. An existing SNS topic passed in as ALERT_TOPIC_ARN is never
# touched. Safe to re-run: a missing stack or log group is not an error.
set -euo pipefail

REGION="${AWS_REGION:-${AWS_DEFAULT_REGION:-us-east-1}}"
export AWS_REGION="$REGION" AWS_DEFAULT_REGION="$REGION" AWS_PAGER=""
SERVICE_NAME="${SERVICE_NAME:-stepspotter-opencv}"
STACK_NAME="${STACK_NAME:-$SERVICE_NAME}"

say() { printf '%s  %s\n' "$(date -u +%H:%M:%SZ)" "$*"; }
die() { say "ERROR: $*" >&2; exit 1; }

case "$SERVICE_NAME" in
  stepspotter|stepspotter-guide|fleetmemory*) die "refusing: '$SERVICE_NAME' is a frozen deployment" ;;
esac
case "$STACK_NAME" in
  stepspotter|stepspotter-guide|fleetmemory*) die "refusing: '$STACK_NAME' is not this project's stack" ;;
esac
[ "${1:-}" = "--yes" ] || die "this deletes the live service and its images; run: $0 --yes"

say "account $(aws sts get-caller-identity --query Account --output text)  region $REGION  stack $STACK_NAME"

STATUS="$(aws cloudformation describe-stacks --stack-name "$STACK_NAME" \
  --query 'Stacks[0].StackStatus' --output text 2>/dev/null || echo NONE)"

output() {
  aws cloudformation describe-stacks --stack-name "$STACK_NAME" \
    --query "Stacks[0].Outputs[?OutputKey=='$1'].OutputValue | [0]" --output text 2>/dev/null || echo None
}

SERVICE_ID=""
if [ "$STATUS" != NONE ]; then
  # The stack must have been made by this template: it carries our tag.
  OWNER="$(aws cloudformation describe-stacks --stack-name "$STACK_NAME" \
    --query "Stacks[0].Tags[?Key=='project'].Value | [0]" --output text)"
  [ "$OWNER" = "$SERVICE_NAME" ] || die "stack $STACK_NAME is not tagged project=$SERVICE_NAME (found '$OWNER'); not deleting"

  SERVICE_ID="$(output ServiceId)"
  [ "$SERVICE_ID" = None ] && SERVICE_ID=""

  BUCKET="$(output SourceBucketName)"
  if [ "$BUCKET" != None ] && aws s3api head-bucket --bucket "$BUCKET" 2>/dev/null; then
    say "emptying s3://$BUCKET"
    aws s3 rm "s3://${BUCKET:?}" --recursive --only-show-errors
  fi

  say "deleting stack $STACK_NAME (was $STATUS)"
  aws cloudformation delete-stack --stack-name "$STACK_NAME"
  aws cloudformation wait stack-delete-complete --stack-name "$STACK_NAME"
  say "stack deleted"
else
  say "no stack $STACK_NAME - nothing to delete there"
fi

# App Runner's own log groups survive the service. Exact names only when we know the id;
# otherwise the ones under this service's own prefix (the service name is ours).
if [ -n "$SERVICE_ID" ]; then
  LOG_GROUPS="/aws/apprunner/$SERVICE_NAME/$SERVICE_ID/service /aws/apprunner/$SERVICE_NAME/$SERVICE_ID/application"
else
  LOG_GROUPS="$(aws logs describe-log-groups --log-group-name-prefix "/aws/apprunner/$SERVICE_NAME/" \
    --query 'logGroups[].logGroupName' --output text)"
fi
for lg in $LOG_GROUPS; do
  case "$lg" in "/aws/apprunner/$SERVICE_NAME/"*) ;; *) continue ;; esac
  if aws logs delete-log-group --log-group-name "$lg" 2>/dev/null; then say "deleted log group $lg"; fi
done
say "done"
