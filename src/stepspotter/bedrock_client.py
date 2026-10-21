"""How every Bedrock client the app creates is set up, and what "the model is busy" means.

Every model the app builds (the Guide agent, the web question agent, and the single-shot
Planner / Marker / Verifier agents in ``vision.make_agent``) gets:

* a botocore ``Config`` with **adaptive** retries — 4 attempts in all, the first one
  included (``total_max_attempts``; ``STEPSPOTTER_BEDROCK_MAX_ATTEMPTS``), plus botocore's
  client-side rate limiter that adaptive mode adds — a 10 s connect timeout and a 120 s
  read timeout.
  Strands 1.55.0 ``BedrockModel(boto_client_config=...)`` merges only its user agent into a
  config it is given (``strands/models/bedrock.py`` ``__init__``), so the read timeout it
  would otherwise default to (120 s) is set here explicitly.
* a Strands retry strategy (``BusyRetry``) that also retries a "service unavailable" that
  arrives INSIDE the response stream. botocore retries the request, but once Bedrock has
  answered 200 and started streaming, a ``serviceUnavailableException`` event is raised by
  the stream reader, after botocore's retry loop; Strands 1.55.0 retries only its own
  ``ModelThrottledException`` by default. Kept short (one retry after 1 s): a person is
  waiting on the other end of a web request.

``is_model_busy`` tells the web layer when a failure that survived all of that is the
service being busy (a friendly 503) rather than a fault (502).
"""

from __future__ import annotations

import os
from typing import Any

from botocore.config import Config
from botocore.exceptions import ClientError
from strands.agent import ModelRetryStrategy
from strands.types.exceptions import ModelThrottledException

CONNECT_TIMEOUT_S = 10
READ_TIMEOUT_S = 120
#: Bedrock error codes that mean "busy, try again", in both spellings: the HTTP API uses
#: ``ServiceUnavailableException``, events inside a ConverseStream response use
#: ``serviceUnavailableException``.
BUSY_CODES = frozenset({
    "ServiceUnavailableException", "serviceUnavailableException",
    "ThrottlingException", "throttlingException",
})


def max_attempts() -> int:
    raw = os.environ.get("STEPSPOTTER_BEDROCK_MAX_ATTEMPTS", "")
    try:
        v = int(raw)
        return v if v > 0 else 4
    except ValueError:
        return 4


def client_config() -> Config:
    """The botocore config for every Bedrock-Runtime client the app creates."""
    return Config(
        # total_max_attempts counts the first request; botocore's "max_attempts" would not
        retries={"total_max_attempts": max_attempts(), "mode": "adaptive"},
        connect_timeout=CONNECT_TIMEOUT_S,
        read_timeout=READ_TIMEOUT_S,
    )


def bedrock_model(model_id: str | None = None, region_name: str | None = None) -> Any:
    """A Strands ``BedrockModel`` with :func:`client_config`. ``model_id`` None = the SDK default."""
    from strands.models.bedrock import BedrockModel

    kwargs: dict[str, Any] = {"boto_client_config": client_config()}
    if region_name:
        kwargs["region_name"] = region_name
    if model_id:
        kwargs["model_id"] = model_id
    return BedrockModel(**kwargs)


def _chain(exc: BaseException | None):
    seen: set[int] = set()
    while exc is not None and id(exc) not in seen:
        seen.add(id(exc))
        yield exc
        exc = exc.__cause__ or exc.__context__


def is_model_busy(exc: BaseException) -> bool:
    """True when the failure is Bedrock being busy or throttling (anywhere in the cause chain)."""
    for e in _chain(exc):
        if isinstance(e, ModelThrottledException):
            return True
        if isinstance(e, ClientError) and (e.response or {}).get("Error", {}).get("Code") in BUSY_CODES:
            return True
    return False


class BusyRetry(ModelRetryStrategy):
    """Strands' own retry, widened to a busy service as well as throttling."""

    def is_retryable(self, exception: Exception) -> bool:
        return isinstance(exception, ModelThrottledException) or is_model_busy(exception)


def retry_strategy() -> BusyRetry:
    return BusyRetry(max_attempts=2, initial_delay=1, max_delay=4)
