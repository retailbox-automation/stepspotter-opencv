"""Where a job lives between commands, and the trace that proves what happened.

Two files per job under ``data/jobs/``:

* ``<job_id>.json``       — the JobState, rewritten on every change;
* ``<job_id>.trace.jsonl`` — append-only, one JSON object per line: every tool call,
  every verdict, every gate refusal. Nothing that happened is only in a chat scroll.

With ``STEPSPOTTER_TRACE_STDOUT=1`` the ``perception`` events and the ``limits`` rows are
ALSO printed to stdout, one JSON object per line, for log-based metrics (CloudWatch
metric filters read ``event``, ``decision``, ``reason_code``, ``llm_called``,
``ms_total``, ``step_id`` off the ``perception`` line). Nothing else is mirrored — no task
text, no chat, no plan — the caller's IP becomes a short salted hash, and file paths
are cut to their basename. See ``stdout_line``.
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
import os
import secrets
import sys
import uuid
from pathlib import Path
from typing import Any

from stepspotter.models import JobState


def data_root() -> Path:
    """Runtime output root. ``STEPSPOTTER_DATA`` overrides it (demos write elsewhere)."""
    env = os.environ.get("STEPSPOTTER_DATA")
    if env:
        return Path(env).expanduser()
    return Path(__file__).resolve().parents[2] / "data"


def jobs_dir() -> Path:
    d = data_root() / "jobs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def new_job_id() -> str:
    return f"job-{_dt.datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:4]}"


def job_path(job_id: str) -> Path:
    return jobs_dir() / f"{job_id}.json"


def trace_path(job_id: str) -> Path:
    return jobs_dir() / f"{job_id}.trace.jsonl"


def cards_dir(job_id: str) -> Path:
    d = jobs_dir() / job_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def save(state: JobState) -> Path:
    state.touch()
    p = job_path(state.job_id)
    p.write_text(state.model_dump_json(indent=2))
    return p


def load(job_id: str) -> JobState:
    p = job_path(job_id)
    if not p.is_file():
        raise FileNotFoundError(f"No job {job_id} at {p}")
    return JobState.model_validate_json(p.read_text())


#: Events mirrored to stdout when STEPSPOTTER_TRACE_STDOUT=1. Everything else in a trace
#: (task text, questions, answers, plans, verdict prose) stays in the job's own file.
STDOUT_EVENTS = frozenset({"perception"})
#: ...plus every row of the "limits" pseudo-job (refusals, the configured caps).
STDOUT_JOBS = frozenset({"limits"})
#: Row fields that hold a filesystem path: only the file name goes to stdout.
_PATH_FIELDS = frozenset({"photo", "card", "img_match", "img_heatmap", "img_quality", "video"})
_SALT = (os.environ.get("STEPSPOTTER_LOG_SALT") or secrets.token_hex(16)).encode()


def _ip_tag(ip: object) -> str | None:
    """A short salted hash of an address: the same caller groups together, nobody's IP
    is in the log. The salt is per process unless STEPSPOTTER_LOG_SALT pins it."""
    if not ip:
        return None
    return hashlib.sha256(_SALT + str(ip).encode()).hexdigest()[:10]


def stdout_line(line: dict[str, Any]) -> dict[str, Any] | None:
    """The stdout copy of one trace row, or None when the row must not leave the file."""
    if line.get("event") not in STDOUT_EVENTS and line.get("job_id") not in STDOUT_JOBS:
        return None
    out: dict[str, Any] = {}
    for key, value in line.items():
        if key == "ip":
            out["ip_tag"] = _ip_tag(value)
        elif key in _PATH_FIELDS and isinstance(value, str) and value:
            out[key] = os.path.basename(value)
        elif isinstance(value, (bytes, bytearray)):
            continue  # never photo bytes
        else:
            out[key] = value
    return out


def trace(job_id: str, event: str, **fields: Any) -> None:
    """Append one trace line. Best-effort: a broken trace must never break the repair."""
    line = {
        "at": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
        "job_id": job_id,
        "event": event,
        **fields,
    }
    try:
        with trace_path(job_id).open("a") as fh:
            fh.write(json.dumps(line, default=str) + "\n")
    except Exception:  # noqa: BLE001 - never let logging take down the run
        pass
    if os.environ.get("STEPSPOTTER_TRACE_STDOUT", "").strip() == "1":
        try:
            mirrored = stdout_line(line)
            if mirrored is not None:
                sys.stdout.write(json.dumps(mirrored, default=str, separators=(",", ":")) + "\n")
                sys.stdout.flush()
        except Exception:  # noqa: BLE001
            pass


def read_trace(job_id: str) -> list[dict]:
    p = trace_path(job_id)
    if not p.is_file():
        return []
    return [json.loads(ln) for ln in p.read_text().splitlines() if ln.strip()]
