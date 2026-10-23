# Platform findings — OpenCV 5, AWS, Strands Agents

Things about the sponsors' products we ran into while building this entry. Each one says
what we expected, what we saw, and the evidence: a command, a file and line, or a page
with the date we read it. Nothing here is a guess; where we could not re-check something
ourselves, it says so.

## 1. AWS App Runner runs x86_64 images only

- **Expected:** to run the OpenCV service on Graviton (arm64), which is also where the
  competition's COOL award lives.
- **Saw:** App Runner has no architecture setting, and the Strands Agents guide for App
  Runner builds for x86_64 explicitly: *"Builds a Docker image for x86_64 architecture
  (App Runner requirement)"*, and in its CDK sample
  `platform: ecr_assets.Platform.LINUX_AMD64, // App Runner requires x86_64`
  (<https://strandsagents.com/docs/user-guide/sdk/deploy/deploy_to_aws_apprunner/index.md>,
  read 2026-10-21T12:07Z, lines 184–187 and 240).
- **Our evidence:** the cloud build checks the built image's architecture and imports
  OpenCV inside it (`infra/buildspec.yml:22–24`); the first build printed
  `arch x86_64 cv2 5.0.0 numpy 2.5.4` (`docs/DEPLOY.md`).
- **What we did:** the stack can build an arm64 image (`ImageArch=arm64`), but a
  CloudFormation rule refuses to point App Runner at it (`infra/template.yaml:145–152`).
  No COOL entry: it would need a Graviton host, and App Runner is not one.

## 2. App Runner is closed to new customers, but an existing account could still create a service

- **Saw:** *"After careful consideration, we decided to close AWS App Runner to new
  customers."* and *"If you're not an existing customer, AWS recommends Amazon ECS Express
  Mode."* (<https://docs.aws.amazon.com/apprunner/latest/dg/apprunner-availability-change.html>,
  read 2026-10-21).
- **Our evidence:** on 2026-10-21 the stack created a new App Runner service
  (`stepspotter-opencv`) in an account that already ran one; it is the live URL
  <https://utgfmpcgxf.us-east-1.awsapprunner.com>. `docs/DEPLOY.md` lists "an account
  where App Runner accepts new services" as a prerequisite, so a stranger with a new
  account knows the stack will fail at the service.

## 3. The Bedrock price list files Claude Sonnet 4.6 as "AWS Marketplace software usage"

- **Expected:** Bedrock model usage to be listed as an Amazon Bedrock charge, since AWS
  promotional credits do not cover AWS Marketplace.
- **Saw:** in the AWS Price List API, every Claude Sonnet 4.6 price dimension in us-east-1
  sits under service code `AmazonBedrockFoundationModels`, usage types `USE1-MP:…`, with
  descriptions such as `AWS Marketplace software usage|us-east-1|Million Input Tokens Global`
  (SKU `4BCSX42248MW35W4`, $3.00 per 1M) and
  `AWS Marketplace software usage|us-east-1|Million Response Tokens Global`
  (SKU `CMWTKXQCAJ2T8A4U`, $15.00 per 1M); effective 2026-09-01, publication
  2026-10-12T08:40:08Z; 22 matching price dimensions in all.
  Command (the Price List API is free to call):

  ```python
  import boto3, json
  c = boto3.client("pricing", region_name="us-east-1")
  for page in c.get_paginator("get_products").paginate(
          ServiceCode="AmazonBedrockFoundationModels",
          Filters=[{"Type": "TERM_MATCH", "Field": "regionCode", "Value": "us-east-1"}]):
      for s in page["PriceList"]:
          p = json.loads(s); a = p["product"]["attributes"]
          if "Sonnet 4.6" in json.dumps(a):
              print(a["usagetype"], [d["description"] for t in p["terms"]["OnDemand"].values()
                                     for d in t["priceDimensions"].values()])
  ```

  Run 2026-10-21T12:06Z.
- **Billing showed the opposite of what the label suggests:** our coordinator's Cost
  Explorer query for September–October 2026, grouped by record type, showed a credit line
  equal to every usage line, Bedrock included. That query was not re-run for this file
  (each Cost Explorer API request is billed); we report it as observed, not reproduced
  here.
- **Why it matters:** a builder deciding from the price list alone would conclude that
  credits do not pay for Claude on Bedrock. We kept a Budget on the stack either way
  (`infra/template.yaml:177`).

## 4. Strands Agents: `Agent.structured_output()` is deprecated

- **Saw:** the installed `strands-agents==1.55.0` warns *"Agent.structured_output method
  is deprecated. You should pass in `structured_output_model` directly into the agent
  invocation."* (`strands/agent/agent.py:1031`, `DeprecationWarning`). The same warning
  was first seen on 1.54.0 in the original spike (`spikes/SPIKE-A-RESULT.md:119`). The
  same file also deprecates `**kwargs` on invocation in favour of `invocation_state`
  (`agent.py:1391`).
- **What we did:** every typed call uses `agent(blocks, structured_output_model=schema)`
  and reads `result.structured_output` (`src/stepspotter/vision.py:91–92`), including
  the new two-photo verdict with its required `same_place` field.

## 5. OpenCV 5.0.0: the DNN warns about the new graph engine when a face detector is created

- **Saw:** creating `cv2.FaceDetectorYN` with the YuNet model from opencv_zoo prints
  `[ WARN:0@0.010] global net_impl_backend.cpp:345 setPreferableTarget Targets are not
  supported by the new graph engine for now`. Detection works (one face found on the
  public-domain test portrait, twice in a row).
- **Reproduce** (`opencv-python-headless==5.0.0.93`, macOS arm64, 2026-10-21):

  ```python
  import cv2
  img = cv2.imread("tests/fixtures/faces/nasa-s69-31741-portrait.jpg")
  d = cv2.FaceDetectorYN.create("models/face_detection_yunet_2023mar.onnx", "",
                                (img.shape[1], img.shape[0]), 0.8, 0.3, 5000)
  print(d.detect(img)[1].shape)   # the warning is printed at create()
  ```

  In our run it appeared once, at `create()`, not on each `detect()`.
- **What we did:** the service lowers OpenCV's log level to errors before creating the
  detector, so the warning does not read like a fault in the service log
  (`src/stepspotter/perception/privacy.py`, `_quiet`).

## 6. OpenCV 5.0.0 wheel: typed, and the model files are separate

- `opencv-python-headless==5.0.0.93` ships type stubs (`cv2/__init__.pyi`, per-module
  `.pyi` files and `py.typed`), checked in the installed package on 2026-10-21.
- The YuNet face model is not in the wheel. We fetch it from opencv_zoo at image build
  time and check its size and SHA256 against the Git LFS pointer
  (`src/stepspotter/perception/fetch_yunet.py`); the build fails on a mismatch
  (`Dockerfile`).

## Method observations (not product defects)

- **SIFT inliers did not separate a real re-shot from another room** on our photos: real
  photos of the same place from another angle or after cables moved kept 4–8 inliers
  after `findHomography(USAC_MAGSAC)`; photos of different rooms kept 5–8
  (`eval/results/opencv.md` at commit `ff97511`, `docs/PERCEPTION.md`). CLAHE on the luminance before SIFT
  roughly doubled inliers on the one real pair that did match (33 → 62). This is why a
  photo OpenCV cannot line up goes to a two-photo model check instead of being refused.
- **Laplacian sharpness depends on the scale it is read at.** Thresholds measured at a
  2x downscale refused a low-resolution close-up read at full scale; quality is now read
  after at least a 2x downscale (`docs/PERCEPTION.md`, eval run 1).
