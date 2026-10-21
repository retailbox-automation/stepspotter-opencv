# StepSpotter — the phone-first web UI in a container.
#
# Port 8080 is the App Runner / Bedrock AgentCore Runtime convention. Build for the
# platform you deploy to: App Runner runs x86_64 (linux/amd64) images; AgentCore Runtime
# takes ARM64 only. The cloud build (infra/buildspec.yml) passes --platform explicitly
# and checks the result; see docs/DEPLOY.md.
#
# BASE_IMAGE: the cloud build pulls the same official image from ECR Public
# (public.ecr.aws/docker/library/python:3.12-slim) to stay clear of Docker Hub's
# anonymous pull limit on shared build hosts. Locally the default is fine.
ARG BASE_IMAGE=python:3.12-slim
FROM ${BASE_IMAGE}

# STEPSPOTTER_DATA is writable but ephemeral — App Runner throws the filesystem away
# with the container. Jobs, cards, evidence photos, traces and the per-day job counter
# that backs the global rate cap all live under it; losing them with the container is a
# demo trade-off written down in docs/DEPLOY.md, not an accident. (The running service
# overrides this to /tmp/stepspotter, which is equally ephemeral.)
# STEPSPOTTER_MANUALS points at the read-only manual cache copied
# in below, so a judge's first request answers from the image instead of from a search
# engine that may be rate-limiting us (DuckDuckGo returned HTTP 202 on 2026-09-11).
#
# The request caps and the kill switch (STEPSPOTTER_PAUSED, STEPSPOTTER_JOBS_PER_IP_HOUR,
# STEPSPOTTER_PHOTOS_PER_IP_HOUR, STEPSPOTTER_MAX_JOBS_PER_DAY,
# STEPSPOTTER_MAX_PHOTOS_PER_DAY) are deliberately NOT set
# here: the defaults in src/stepspotter/web/limits.py are the safe ones, and the switch
# belongs to whoever is operating the service. See docs/OPERATIONS.md.
ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=8080 \
    STEPSPOTTER_DATA=/data \
    STEPSPOTTER_MANUALS=/app/data/manuals

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
COPY data/manuals ./data/manuals
RUN pip install --no-cache-dir . \
 && mkdir -p /data/jobs \
 && useradd --create-home --uid 10001 spotter \
 && chown -R spotter:spotter /data /app
USER spotter

EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8080/healthz',timeout=4).status==200 else 1)"

CMD ["python", "-m", "uvicorn", "stepspotter.web.app:app", "--host", "0.0.0.0", "--port", "8080"]
