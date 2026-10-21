# Deploying StepSpotter × OpenCV 5 on AWS

One CloudFormation stack (`infra/template.yaml`), one command to deploy (`infra/deploy.sh --yes`), one to remove it (`infra/destroy.sh --yes`). The image is built in AWS CodeBuild from the committed code, so you don't need Docker on your machine.

```
git HEAD ──git archive──▶ S3 (source zip, 7-day lifecycle)
                              │
                              ▼
                 CodeBuild (general1.small, x86_64)
                 docker build → arch check → import smoke (cv2, app) → push
                              │
                              ▼
                 ECR stepspotter-opencv (immutable tags, scan on push, keep last 5)
                              │  image digest
                              ▼
   App Runner stepspotter-opencv (1 vCPU / 2 GB, min = max = 1 instance)
     ├─ instance role: Bedrock InvokeModel on ONE model + PutMetricData in ONE namespace
     ├─ stdout (JSON trace) → CloudWatch Logs → metric filters → StepSpotterOpenCV/*
     ├─ alarms (5xx, request flood, perception p95) → SNS → email
     └─ dashboard stepspotter-opencv
   AWS Budget stepspotter-opencv ($15/month, email at 80 % actual), created before the service
```

## Prerequisites

| What | Why |
|---|---|
| An AWS account where **App Runner accepts new services** | App Runner closed to *new customers* on 2026-04-30. Accounts that already used it can still create services ([availability change](https://docs.aws.amazon.com/apprunner/latest/dg/apprunner-availability-change.html), read 2026-10-21). If yours is new, the stack fails at `Service`. AWS recommends ECS Express Mode instead, but this template doesn't target it. |
| Amazon Bedrock access to **Claude Sonnet 4.6** in `us-east-1` | The app calls the `global.anthropic.claude-sonnet-4-6` inference profile. |
| AWS CLI v2, `git`, `curl`, `python3` | Used by the scripts. |
| Credentials allowed to create IAM roles, CloudFormation, App Runner, ECR, S3, CodeBuild, CloudWatch, SNS, Budgets, Bedrock inference profiles | The stack needs `CAPABILITY_NAMED_IAM`. |
| A clean checkout of the commit you want to run | `deploy.sh` refuses a dirty tree. The image is `git archive HEAD`, nothing else. |

Credentials come from the normal AWS CLI chain (env vars, profile, SSO). The scripts never read, print or store a key. No `.env` file is involved, and the service gets no secrets: it reaches Bedrock through its instance role.

## Deploy

```bash
git clone <this repo> && cd stepspotter-opencv
export AWS_REGION=us-east-1                 # plus your usual credentials
BUDGET_EMAIL=you@example.com ALERT_EMAIL=you@example.com infra/deploy.sh --yes
```

`--yes` is required on every run because the script creates billable resources.

What happens (each step is idempotent, so re-running is safe):

1. Refuses a dirty working tree. The image tag is `git-<first 12 chars of HEAD>`.
2. **Phase 1** (only while the service doesn't exist): stack with `DeployService=false` creates the ECR repo, the S3 source bucket, the CodeBuild project and its log group, the IAM roles, the Bedrock application inference profile and the **Budget**.
3. **Image.** If ECR already has the tag, it is reused (tags are immutable). Otherwise: `git archive HEAD` → `s3://<bucket>/source/<tag>.zip` → CodeBuild. The build fails if the image isn't `linux/amd64`, or if `import cv2, numpy, stepspotter.web.app` fails inside it.
4. **Phase 2**: stack update with `DeployService=true` and the image **digest** (not the tag). This creates or updates the App Runner service, the metric filters, the alarms and the dashboard. CloudFormation returns once the service is `RUNNING`. The script then checks that the service really runs `@<digest>`.
5. Sets retention (14 days) on the two log groups App Runner creates for the service.
6. Smoke: `GET /`, `GET /healthz` and `GET /api/demo` must each return 200. The script lists any perception-only route the build exposes (read from `/openapi.json`).

Expected output (the values are placeholders):

```
hh:mm:ssZ  template valid
hh:mm:ssZ  phase 1: build infrastructure (no service yet)
hh:mm:ssZ  built git-xxxxxxxxxxxx in NNNs -> sha256:…
hh:mm:ssZ  phase 2: service on sha256:… (CloudFormation waits for RUNNING)
hh:mm:ssZ  smoke  GET /  -> 200 in 0.xs  OK
hh:mm:ssZ  smoke  GET /healthz  -> 200 in 0.xs  OK
hh:mm:ssZ  smoke  GET /api/demo  -> 200 in 0.xs  OK

  service URL    https://xxxxxxxxxx.us-east-1.awsapprunner.com
  image          <acct>.dkr.ecr.us-east-1.amazonaws.com/stepspotter-opencv@sha256:…  (git-…)
  dashboard      stepspotter-opencv   https://us-east-1.console.aws.amazon.com/cloudwatch/…
  app logs       /aws/apprunner/stepspotter-opencv/<service-id>/application
  model          arn:aws:bedrock:us-east-1:<acct>:application-inference-profile/…
  durations      infra Ns  build Ns  service Ns  total Ns
```

Measured durations: **not measured yet.** The pipeline has been validated (`cloudformation validate-template`, `cfn-lint`, `shellcheck`), but it hasn't been run end to end. Fill this in from the first real run.

### Settings (environment variables for `deploy.sh`)

| Variable | Default | Effect |
|---|---|---|
| `CPU` / `MEMORY` | `1 vCPU` / `2 GB` | App Runner instance size. `0.25 vCPU` / `0.5 GB` is ~4× cheaper when idle, but OpenCV runs on a quarter of a core and Python + Strands + OpenCV must fit in 0.5 GB. That size is untested. |
| `PAUSED` | `0` | Kill switch, see [OPERATIONS.md](OPERATIONS.md). |
| `JOBS_PER_IP_HOUR` / `PHOTOS_PER_IP_HOUR` | 6 / 30 | Per-address hourly caps. |
| `MAX_JOBS_PER_DAY` / `MAX_PHOTOS_PER_DAY` | 6 / 30 | Global daily caps. They bound the Bedrock spend at ≤ 6 × 3 + 30 × 2 = 78 calls/day. |
| `BUDGET_LIMIT_USD` | 15 | Monthly Budget. The email goes out at 80 % of actual spend. |
| `DEMO_MODEL_ID` | empty | Cost fallback. Empty means Claude Sonnet 4.6. `us.amazon.nova-2-lite-v1:0` points the photo-check and planning path (`STEPSPOTTER_MODEL`) at Amazon Nova 2 Lite, and the instance role is widened to exactly that profile and model. The in-app Guide chat keeps the Strands default model. |
| `ALERT_TOPIC_ARN` | empty | Use an existing SNS topic for alarms. Empty means the stack creates `<service>-alerts` and subscribes `ALERT_EMAIL` (you must confirm the email). |
| `USE_APP_INFERENCE_PROFILE` | `true` | Creates a tagged Bedrock *application inference profile* over the global Sonnet 4.6 profile, so model spend carries the `project` tag. Set `false` to call the global profile directly. |
| `PERCEPTION_P95_ALARM_MS` | 2000 | Perception p95 alarm threshold. Provisional until the eval run publishes the real p95. |
| `SERVICE_NAME` / `STACK_NAME` / `AWS_REGION` | `stepspotter-opencv` / same / `us-east-1` | |

Architecture: **App Runner runs x86_64 images only.** The service that StepSpotter's first deployment runs on is `linux/amd64`. Strands' own App Runner helper says "Builds a Docker image for x86_64 architecture (App Runner requirement)". The App Runner pricing page and developer guide don't mention ARM at all (read 2026-10-21). The template can build an arm64 (Graviton) image in CodeBuild (`ImageArch=arm64`), but a CloudFormation rule stops you from pointing App Runner at one.

### Budget

The Budget counts gross usage (credits excluded) of resources tagged `project=<service name>`. Every taggable resource in the stack carries the tag, including the Bedrock application inference profile, so model calls made through it are attributed too. Calls the in-app Guide chat makes through the global profile are not. AWS Budgets only sees a tag after it is **activated as a cost allocation tag**. That's an account-wide billing setting, so `deploy.sh` doesn't change it; it prints a note when the tag is inactive. To activate it once the tag has shown up in billing (up to 24 h after the first tagged usage):

```bash
aws ce update-cost-allocation-tags-status --cost-allocation-tags-status TagKey=project,Status=Active
```

Until then the Budget reads $0. The app's request caps are what actually bound spend; the Budget only notifies.

## Smoke and perception check by hand

```bash
URL=$(aws cloudformation describe-stacks --stack-name stepspotter-opencv \
  --query "Stacks[0].Outputs[?OutputKey=='ServiceUrl'].OutputValue" --output text)
curl -s -o /dev/null -w '%{http_code} %{time_total}s\n' "$URL/"         # 200, free
curl -s "$URL/healthz"                                                   # {"ok":true,...}
curl -s "$URL/api/jobs/limits/trace" | python3 -m json.tool | head -40  # the caps this image enforces
```

`POST /api/demo/jobs` starts a real job on packaged photos. It spends Bedrock calls and counts against the daily caps.

## Cost

Prices are from the AWS Price List API (`aws pricing get-products`, us-east-1, retrieved 2026-10-21; effective date in brackets) and the public pricing pages.

| Item | Unit price | This deployment |
|---|---|---|
| App Runner provisioned instance (idle) | $0.007 per GB-hour of memory [2024-06-01] — [pricing](https://aws.amazon.com/apprunner/pricing/) | 2 GB → $0.014/h → **$0.336/day, ≈ $10.22/month** |
| App Runner active instance | $0.064 per vCPU-hour + $0.007 per GB-hour [2024-06-01]; per second, 1-min minimum per activation | +$0.064 per hour spent processing requests |
| App Runner paused | compute goes to zero ([pause docs](https://docs.aws.amazon.com/apprunner/latest/dg/manage-pause.html)); "you are only billed while your application is running" (pricing page) | $0 for App Runner; ECR/CloudWatch remain |
| CodeBuild general1.small (x86_64) | $0.005 per build-minute, rounded up per minute [2026-08-01] — [pricing](https://aws.amazon.com/codebuild/pricing/) | build time not yet measured; ≈ 5–8 min estimated → ≈ $0.03–0.04 per build. 100 min/month on small is in the free tier where it applies |
| ECR storage | $0.10 per GB-month [2025-11-01] — [pricing](https://aws.amazon.com/ecr/pricing/) | ≈ 0.2 GB per image (estimate: 128 MB previous image + 61 MB OpenCV wheel + 16 MB numpy wheel), ≤ 5 kept → ≤ $0.10/month |
| S3 source zips | $0.023 per GB-month [Price List] — [pricing](https://aws.amazon.com/s3/pricing/) | ≈ 21 MB per deploy, deleted after 7 days → < $0.01 |
| CloudWatch custom metrics | $0.30 per metric-month (first 10,000) — [pricing](https://aws.amazon.com/cloudwatch/pricing/) | 9 metrics; 10 are in the free tier → $0–2.70/month |
| CloudWatch alarms | $0.10 per standard alarm-month | 3 alarms; 10 in the free tier → $0–0.30/month |
| CloudWatch dashboard | $3.00 per dashboard-month; 3 dashboards ≤ 50 metrics free | $0–3.00/month |
| CloudWatch Logs | $0.50 per GB ingested, $0.03 per GB-month stored [2026-10-01]; 5 GB/month free | health checks every 10 s plus trace lines ≈ 1 MB/day → ≈ $0.02/month |
| Bedrock Claude Sonnet 4.6 (global profile) | $3 per 1M input tokens, $15 per 1M output tokens [2026-09-01] — [pricing](https://aws.amazon.com/bedrock/pricing/) | ≈ $0.019 per call (3,142 in / 657 out tokens average, measured on the first deployment 01.09–15.10.2026). Daily caps bound it at ≤ 78 calls ≈ **≤ $1.51/day**. A photo that OpenCV refuses costs no call. |

**Idle total at 1 vCPU / 2 GB ≈ $0.34/day ≈ $10.5/month** before Bedrock. Most of that is the provisioned 2 GB.

## Tear down

```bash
infra/destroy.sh --yes
```

This empties the source bucket, deletes the stack (service, ECR repo with its images, bucket, CodeBuild project, roles, inference profile, metric filters, alarms, dashboard, Budget, and the SNS topic if the stack made one), then deletes the two log groups App Runner created for this service, matched by exact name. It refuses to run against a stack that isn't tagged `project=<service name>`, or one named after a frozen deployment. A topic passed in via `ALERT_TOPIC_ARN` is left alone. Re-running is harmless.
