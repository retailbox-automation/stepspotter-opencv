# Operating StepSpotter × OpenCV 5

The service is public and needs no login, and two of its endpoints spend money on Amazon Bedrock. This page covers how spend is bounded, how to stop it, where to look when something is wrong, and what happens to people's photos.

## Spend controls, from fastest to bluntest

| Control | Where | Effect | How to change it |
|---|---|---|---|
| Per-address caps | `src/stepspotter/web/limits.py`, env `STEPSPOTTER_JOBS_PER_IP_HOUR` (6), `STEPSPOTTER_PHOTOS_PER_IP_HOUR` (30) | A 7th job or 31st photo check from one address in an hour gets a 429 with a readable sentence. | `JOBS_PER_IP_HOUR=… PHOTOS_PER_IP_HOUR=… infra/deploy.sh --yes` |
| Global daily caps | env `STEPSPOTTER_MAX_JOBS_PER_DAY` (6), `STEPSPOTTER_MAX_PHOTOS_PER_DAY` (30) | Bound the Bedrock calls at ≤ 6 × 3 + 30 × 2 = 78 per UTC day (≈ $1.51 at Sonnet 4.6 prices), whoever asks. The per-address window is keyed on a header the caller controls, so these caps are what stops rotation of `X-Forwarded-For`. | `MAX_JOBS_PER_DAY=… MAX_PHOTOS_PER_DAY=… infra/deploy.sh --yes` |
| OpenCV gate | `src/stepspotter/perception/` | A photo that fails the OpenCV checks (blurry, wrong place, unchanged, touched a "do not touch" zone) is refused **without** a Bedrock call. The `LlmCallsSaved` metric counts these. | Code (see docs/PERCEPTION.md) |
| Cheaper model | stack parameter `DemoModelId` → env `STEPSPOTTER_MODEL` | Moves the photo-check and planning calls from Claude Sonnet 4.6 to e.g. Amazon Nova 2 Lite (`us.amazon.nova-2-lite-v1:0`). The plan for this deployment is to do this, or pause, when the Budget reaches 80 %. | `DEMO_MODEL_ID=us.amazon.nova-2-lite-v1:0 infra/deploy.sh --yes` (empty = back to Sonnet) |
| **Kill switch** | env `STEPSPOTTER_PAUSED=1` | `POST /api/jobs`, `/api/demo/jobs` and the photo endpoints answer 503 with "Demo paused to protect the hackathon budget…". The page, finished jobs, traces and `/healthz` stay up. | `PAUSED=1 infra/deploy.sh --yes` (a new deployment, a few minutes) |
| Pause the service | App Runner `pause-service` | Compute goes to zero and App Runner stops billing for it. The URL is kept, but **every job and photo on the instance is lost**, and nothing answers until `resume-service`. | `aws apprunner pause-service --service-arn <ServiceArn>` / `resume-service` |
| Tear down | `infra/destroy.sh --yes` | Everything the stack made is gone. | |
| Budget | AWS Budget `stepspotter-opencv`, $15/month | Emails at 80 % of actual (gross) spend. It notifies; it doesn't stop anything. It only sees spend once the `project` tag is an active cost allocation tag (docs/DEPLOY.md § Budget). | `BUDGET_LIMIT_USD=… infra/deploy.sh --yes` |

There is one instance (`MinSize = MaxSize = 1`) on purpose. Job state lives on the instance's disk, and the in-process rate-limit counters are only correct when there is one process. App Runner can't scale this service out on its own.

To check which caps the running image actually enforces, without shell access: `GET /api/jobs/limits/trace`. Its `configured` row lists the caps and today's counts. Refusals appear there too.

## Budget read-back (live deployment)

Read with `aws budgets describe-budget`, `describe-notifications-for-budget` and `describe-subscribers-for-notification` at 2026-10-21T11:32:04Z, right after phase 1 and before the service existed. The cost allocation tag `project` was Active (activated 2026-10-21T11:28:32Z).

```json
{
    "BudgetName": "stepspotter-opencv",
    "BudgetLimit": {
        "Amount": "15.0",
        "Unit": "USD"
    },
    "TimeUnit": "MONTHLY",
    "BudgetType": "COST",
    "CostFilters": {
        "TagKeyValue": [
            "user:project$stepspotter-opencv"
        ]
    },
    "CostTypes": {
        "IncludeTax": true,
        "IncludeSubscription": true,
        "UseBlended": false,
        "IncludeRefund": false,
        "IncludeCredit": false,
        "IncludeUpfront": true,
        "IncludeRecurring": true,
        "IncludeOtherSubscription": true,
        "IncludeSupport": false,
        "IncludeDiscount": true,
        "UseAmortized": false
    },
    "FilterExpression": null
}
{
    "Notifications": [
        {
            "NotificationType": "ACTUAL",
            "ComparisonOperator": "GREATER_THAN",
            "Threshold": 80.0,
            "NotificationState": "OK"
        }
    ]
}
{
    "Subscribers": [
        {
            "SubscriptionType": "EMAIL",
            "Address": "admin@retailbox-automation.com"
        }
    ]
}
```

## Where to look

| Question | Place |
|---|---|
| Is it up? | `GET /healthz` → `{"ok": true}`. App Runner's health check hits the same path every 10 s and replaces the instance after 5 failures. |
| What did the OpenCV gate decide, and did it save model calls? | CloudWatch dashboard **`stepspotter-opencv`**: decisions per type, LLM calls saved vs made, perception p50/p95, last 50 perception events. Namespace `StepSpotterOpenCV`, metrics `PerceptionDecisions{Decision}`, `LlmCallsSaved`, `LlmCallsMade`, `PerceptionLatencyMs`. |
| What happened in one job? | `GET /api/jobs/<id>/trace` (the full per-job trace, kept on the instance). |
| Raw logs | Log group `/aws/apprunner/stepspotter-opencv/<service-id>/application` (the app's stdout), plus `…/service` for App Runner's deployment events. Retention: 14 days. Build logs: `/aws/codebuild/stepspotter-opencv-build`, 14 days. |
| Alarms | `stepspotter-opencv-5xx` (≥ 3 server errors in 5 min), `stepspotter-opencv-request-flood` (≥ 400 requests in 5 min), `stepspotter-opencv-perception-p95` (p95 > 2000 ms in 2 of 3 five-minute periods). All three notify the SNS topic, which emails the operator. Missing data counts as OK. |
| What runs right now? | `aws apprunner describe-service` → `ImageIdentifier` is `…/stepspotter-opencv@sha256:…`. The ECR tag on that digest is `git-<commit>`, so you can read the code that runs with `git show <commit>`. |

The metrics come from CloudWatch Logs metric filters over JSON lines the app prints to stdout (`STEPSPOTTER_TRACE_STDOUT=1`). The filters expect one JSON object per line with `"event": "perception"` and the fields `decision`, `llm_called` (bool), `ms_total` (number) and `step_id`. If the app stops printing them, the dashboard goes flat but nothing errors. So a flat `PerceptionDecisions` while `Requests` grows is itself the signal.

## Privacy: photos and logs

**Photos.** Start photos and evidence photos are written under `STEPSPOTTER_DATA=/tmp/stepspotter` on the App Runner instance's ephemeral disk. They aren't copied to S3, ECR or any database. They're gone when the instance is replaced, which happens on every deploy, on pause/resume, and whenever App Runner swaps an unhealthy instance. Photos are sent to Amazon Bedrock (Claude Sonnet 4.6) for the steps that need a model. Per AWS, model providers "don't have access to Amazon Bedrock logs or to customer prompts and completions" ([Bedrock data protection](https://docs.aws.amazon.com/bedrock/latest/userguide/data-protection.html), read 2026-10-21). This stack does not turn on Bedrock model-invocation logging. The S3 bucket in this stack holds **source code zips only**, and they expire after 7 days.

**What goes to CloudWatch Logs (14 days):**
- App Runner request logs and the app server's access log (method, path, status). The socket peer is App Runner's proxy, not the visitor.
- The JSON trace lines the app prints to stdout. The intended content is perception decisions and their metrics (sharpness, exposure, match/overlap figures, timings, `llm_called`), keyed by job id and step id. These lines carry no image data.
- Rate-limit rows from `limits.py` (refusals, the configured caps, which header identified the caller). The caller address is **not** in them: `store.py` replaces it with `ip_tag`, the first 10 hex characters of a salted SHA-256 of the address, so repeat callers group together without the address being logged. The salt is random per process unless `STEPSPOTTER_LOG_SALT` pins it; with a per-process salt the same caller gets a new tag after every restart or deploy.

**What we don't log:** image bytes, image URLs outside the instance, credentials, request headers, or the caller's address (only its salted tag, above).

**Status at this commit:** checked against `src/stepspotter/store.py` (`stdout_line`, `STDOUT_EVENTS`, `STDOUT_JOBS`) and its test `tests/test_trace_stdout.py`. With `STEPSPOTTER_TRACE_STDOUT=1` only two kinds of trace row reach stdout: `perception` events and rows of the `limits` pseudo-job. Everything else in a job's trace (task text, plans, verdict prose, chat questions and answers) stays in the job's own file on the instance's disk and never reaches CloudWatch. In the mirrored rows, file paths are cut to their basename and byte values are dropped.

**Faces.** The perception layer blurs faces in the stored photo before it goes to the model (`perception/privacy.py`, YuNet from opencv_zoo, MIT). The image build fetches the model and checks its SHA256 (`perception/fetch_yunet.py`, run by the Dockerfile); without the file nothing is blurred. Whether it ran is reported per photo as `faces_checked`. Read that field; don't assume it ran.

## Access

- The service has no secrets in its environment. It reaches Bedrock through the instance role `stepspotter-opencv-apprunner-instance`, which may only `InvokeModel`/`InvokeModelWithResponseStream` on Claude Sonnet 4.6 (that inference profile, its foundation-model ARNs and the stack's application profile). Its only other permission is `PutMetricData` into the namespace `StepSpotterOpenCV`.
- App Runner pulls images with `stepspotter-opencv-apprunner-ecr`, which can read this one repository.
- CodeBuild (`stepspotter-opencv-codebuild`) can read `source/*` in this stack's bucket, push to this one repository, and write to its own log group.
- ECR tags are immutable and scanned on push. The source bucket blocks all public access and denies non-TLS requests.
