"""The OpenCV layer on the web: the judge scenarios, /api/inspect, the feed and the trace.

Offline: real OpenCV, the real gate, the real app; the model is faked where a test needs
one and is never reached in the judge scenarios (the judge service's verifier raises).
"""

from __future__ import annotations

import io
import json
import re
from pathlib import Path

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient

from stepspotter.guide import JobService
from stepspotter.models import Box, Plan, Step, StepVerdict
from stepspotter.perception import synthetic
from stepspotter.web import judge
from stepspotter.web.app import create_app
from stepspotter.web.limits import PHOTOS, bucket_for

ROOT = Path(__file__).resolve().parents[1]
SCENES = json.loads((ROOT / "fixtures" / "perception" / "scenes.json").read_text())["photos"]
START = ROOT / SCENES["02"]["file"]

FORBIDDEN = (
    re.compile(r"/(?:Users|home|tmp|private|var|data|app)/"),
    re.compile(r"\.jpe?g\b"),
    re.compile(r"\bjob-\d{8}-\d{6}-[0-9a-f]{4}\b"),
)


@pytest.fixture(autouse=True)
def perception_on(monkeypatch):
    monkeypatch.setenv("STEPSPOTTER_PERCEPTION", "1")


def _jpeg(img: np.ndarray) -> bytes:
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 90])
    assert ok
    return buf.tobytes()


class Model:
    def __init__(self) -> None:
        self.calls = 0

    def __call__(self, step, photo, model_id=None, **kw) -> StepVerdict:
        self.calls += 1
        return StepVerdict(step_id=step.id, passed=True, reason="the model agrees")


@pytest.fixture
def model() -> Model:
    return Model()


@pytest.fixture
def client(model) -> TestClient:
    plan = Plan(
        job_title="Fit the splitter",
        safety_class="diy_ok",
        steps=[Step(id=1, title="Fit it", action="a", evidence_required="e", expects_change=True)],
    )
    service = JobService(
        plan_fn=lambda *a, **k: plan,
        verify_fn=model,
        locate_fn=lambda *a, **k: list(judge.ZONES_02),
    )
    return TestClient(create_app(service))


# ------------------------------------------------------------------------ judge path


def test_the_judge_zones_are_the_hand_placed_ones():
    want = [(z["label"], z["kind"], z["box"]) for z in SCENES["02"]["zones"]]
    got = [(b.label, b.kind, [b.x0, b.y0, b.x1, b.y1]) for b in judge.ZONES_02]
    assert got == want


def test_the_judge_menu_lists_the_branches(client):
    info = client.get("/api/judge").json()
    assert info["available"] is True
    assert {s["name"] for s in info["scenarios"]} == {"retake", "wrong_place", "replay", "human_approval"}


@pytest.mark.parametrize("name", ["retake", "wrong_place", "replay", "human_approval"])
def test_each_judge_scenario_ends_in_opencv_and_the_gate(client, model, name):
    out = client.post(f"/api/judge/{name}").json()
    assert out["as_expected"], out
    assert out["llm_called"] is False and out["verdict_source"] == "opencv"
    assert model.calls == 0
    assert out["gate"]["blocked"] is True
    assert out["gate"]["human_review"] is (name == "human_approval")
    assert out["ms_total"] > 0 and out["instruction"]
    for url in out["images"].values():
        r = client.get(url)
        assert r.status_code == 200 and r.headers["content-type"] == "image/jpeg"
        assert r.content[:2] == b"\xff\xd8"
    jid = out["job_id"]

    feed = client.get(f"/api/jobs/{jid}/feed").json()
    kinds = [m["kind"] for m in feed["messages"]]
    assert "perception" in kinds and "verdict" not in kinds  # OpenCV's card is the refusal
    cv = next(m for m in feed["messages"] if m["kind"] == "perception")
    assert cv["final"] and cv["images"] and not cv["llm_called"]
    assert any(m["kind"] == "note" and "Judge scenario" in m["text"] for m in feed["messages"])
    if name == "human_approval":
        assert any(m["kind"] == "block" and m.get("review") for m in feed["messages"])
        # the gate has already stopped for a person, so the one action left is theirs
        assert feed["composer"]["action"] == "approve"
    else:
        assert feed["composer"]["label"] == "Take a new photo" and feed["composer"]["hint"]

    human = client.get(f"/api/jobs/{jid}/trace?view=human").json()["human"]
    row = next(r for r in human if r["actor"].startswith("OpenCV"))
    assert "no model call needed" in row["result"] and row["images"]
    text = json.dumps(human)
    for pattern in FORBIDDEN:
        assert not pattern.search(text), pattern.pattern


def test_a_person_approves_a_do_not_touch_change_from_the_page(client):
    out = client.post("/api/judge/human_approval").json()
    jid = out["job_id"]
    r = client.post(f"/api/jobs/{jid}/review", data={"approved": "true", "answer": "looked, it is fine"}).json()
    assert r["approved"] is True and r["job"]["perception"]["approved"] is True
    feed = client.get(f"/api/jobs/{jid}/feed").json()
    assert any("approved carrying on" in (m.get("text") or "") for m in feed["messages"])
    assert feed["composer"]["label"] == "Take a new photo"
    # nothing else is waiting for a person now
    assert client.post(f"/api/jobs/{jid}/review", data={"approved": "true"}).status_code == 200
    j2 = client.post("/api/judge/retake").json()["job_id"]
    assert client.post(f"/api/jobs/{j2}/review", data={"approved": "true"}).status_code == 409


def test_an_unknown_scenario_is_a_404(client):
    assert client.post("/api/judge/sideways").status_code == 404


# ------------------------------------------------------------------------ /api/inspect


def test_inspect_returns_the_report_and_pictures_without_a_model(client, model):
    ref = cv2.imread(str(START))
    files = {
        "reference": ("ref.jpg", _jpeg(ref), "image/jpeg"),
        "evidence": ("ev.jpg", _jpeg(synthetic.gaussian_blur(ref, 4)), "image/jpeg"),
    }
    body = client.post("/api/inspect", files=files).json()
    assert body["decision"] == "retake" and body["reason_code"] == "blurry"
    assert body["llm_called"] is False and model.calls == 0
    assert body["timings_ms"]["total"] > 0 and body["thresholds"]["SHARP_P90_MIN"]
    assert set(body["images"]) == {"quality"}
    assert client.get(body["images"]["quality"]).status_code == 200


def test_inspect_with_zones_calls_another_place_wrong(client):
    zones = json.dumps(SCENES["02"]["zones"])
    files = {
        "reference": ("ref.jpg", START.read_bytes(), "image/jpeg"),
        "evidence": ("ev.jpg", (ROOT / SCENES["04"]["file"]).read_bytes(), "image/jpeg"),
    }
    body = client.post("/api/inspect", files=files, data={"zones": zones}).json()
    assert body["decision"] == "wrong_place"
    assert set(body["images"]) == {"match", "quality"}


def test_inspect_rejects_bad_zones_and_keeps_no_uploads(client, isolated_data):
    files = {"evidence": ("ev.jpg", START.read_bytes(), "image/jpeg")}
    assert client.post("/api/inspect", files=files, data={"zones": "not json"}).status_code == 400
    ok = client.post("/api/inspect", files={"evidence": ("ev.jpg", START.read_bytes(), "image/jpeg")}).json()
    assert ok["decision"] == "ok" and ok["scene"]["status"] == "no_reference"
    left = [p.name for p in (isolated_data / "jobs" / "_inspect").rglob("*") if p.is_file()]
    assert all(name.startswith("inspect-") for name in left), left


def test_the_opencv_routes_share_the_photo_caps():
    assert bucket_for("POST", "/api/inspect") == PHOTOS
    assert bucket_for("POST", "/api/judge/retake") == PHOTOS
    assert bucket_for("GET", "/api/judge") is None


def test_picture_routes_refuse_anything_but_their_own_names(client):
    jid = client.post("/api/judge/retake").json()["job_id"]
    for bad in ("..%2F..%2Fstart", "step-01-try-01-match.jpg", "start", "step-1-try-1-match"):
        assert client.get(f"/api/jobs/{jid}/perception/{bad}").status_code == 404
    assert client.get("/api/inspect/zzzz/match").status_code == 404


# ------------------------------------------------------------------- the phone's path


def test_a_phone_photo_goes_through_opencv_before_the_model(client, model):
    created = client.post(
        "/api/jobs", data={"task": "fit the splitter"}, files={"photo": ("p.jpg", START.read_bytes(), "image/jpeg")}
    ).json()
    jid = created["job_id"]
    client.get(f"/api/jobs/{jid}/feed")  # draws the card, so the zones exist
    blurred = _jpeg(synthetic.gaussian_blur(cv2.imread(str(START)), 4))
    out = client.post(f"/api/jobs/{jid}/photo", files={"photo": ("b.jpg", blurred, "image/jpeg")}).json()
    assert model.calls == 0
    assert out["job"]["verdict"]["source"] == "opencv"
    assert out["job"]["perception"]["decision"] == "retake"
    assert out["job"]["llm_calls_saved"] == 1
    adv = client.post(f"/api/jobs/{jid}/advance").json()
    assert adv["blocked"] is True

    part = cv2.imread(str(ROOT / SCENES["04"]["file"]))
    h, w = part.shape[:2]
    part = part[int(0.38 * h) : int(0.80 * h), int(0.22 * w) : int(0.80 * w)]
    done = synthetic.perspective(
        synthetic.paste_patch(cv2.imread(str(START)), tuple(SCENES["02"]["zones"][0]["box"]), part, cover=0.6, seed=1),
        0.05,
        2,
    )
    out2 = client.post(f"/api/jobs/{jid}/photo", files={"photo": ("d.jpg", _jpeg(done), "image/jpeg")}).json()
    assert model.calls == 1 and out2["job"]["verdict"]["source"] == "llm"
    feed = client.get(f"/api/jobs/{jid}/feed").json()["messages"]
    cvs = [m for m in feed if m["kind"] == "perception"]
    assert [c["decision"] for c in cvs] == ["retake", "ok"]
    assert cvs[1]["llm_called"] is True and feed[-1]["kind"] == "verdict"
