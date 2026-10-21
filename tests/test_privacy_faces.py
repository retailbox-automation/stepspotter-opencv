"""Faces: found and blurred when the YuNet model is installed — and only claimed then.

The positive tests run only where the model file exists (fetched by
tools/fetch_models.sh, or by the container build); without it they are skipped and the
layer reports ``faces_checked=False`` (tested in test_perception.py). No network here.
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path

import cv2
import numpy as np
import pytest

from stepspotter import store
from stepspotter.guide import JobService
from stepspotter.models import Plan, Step, StepVerdict
from stepspotter.perception import fetch_yunet, imgio, privacy
from stepspotter.perception.inspect import inspect_evidence

ROOT = Path(__file__).resolve().parents[1]
FACE = ROOT / "tests" / "fixtures" / "faces" / "nasa-s69-31741-portrait.jpg"
needs_model = pytest.mark.skipif(
    privacy.model_path() is None, reason="YuNet not installed (tools/fetch_models.sh)"
)


def _face_box(img: np.ndarray) -> tuple[int, int, int, int]:
    det = cv2.FaceDetectorYN.create(str(privacy.model_path()), "", (img.shape[1], img.shape[0]), 0.8, 0.3, 5000)
    _n, faces = det.detect(img)
    assert faces is not None and len(faces) == 1
    return tuple(int(v) for v in faces[0][:4])  # type: ignore[return-value]


def _sharp(img: np.ndarray) -> float:
    return float(cv2.Laplacian(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY), cv2.CV_64F).var())


def test_the_fixture_is_recorded_with_its_licence():
    text = (ROOT / "tests" / "fixtures" / "ATTRIBUTION.md").read_text()
    assert FACE.name in text and "Public domain" in text
    assert "https://commons.wikimedia.org/wiki/File:Neil_Armstrong_pose.jpg" in text


def test_the_build_and_the_script_pin_the_same_file():
    script = (ROOT / "tools" / "fetch_models.sh").read_text()
    assert re.search(r'SHA256="([0-9a-f]{64})"', script).group(1) == fetch_yunet.SHA256
    assert re.search(r"SIZE=(\d+)", script).group(1) == str(fetch_yunet.SIZE)
    assert fetch_yunet.verify(b"not the model") is not None


@needs_model
def test_the_installed_model_is_the_pinned_one():
    assert fetch_yunet.verify(privacy.model_path().read_bytes()) is None


@needs_model
def test_a_real_face_is_found_and_blurred_and_nothing_else_moves():
    img = imgio.load(FACE)
    x, y, w, h = _face_box(img)
    out, rep = privacy.blur_faces(img)
    assert rep.faces_checked is True and rep.faces_blurred == 1
    assert _sharp(out[y : y + h, x : x + w]) < 0.05 * _sharp(img[y : y + h, x : x + w])
    pad = int(0.25 * max(w, h)) + 2
    mask = np.ones(img.shape[:2], bool)
    mask[max(0, y - pad) : y + h + pad, max(0, x - pad) : x + w + pad] = False
    assert np.array_equal(out[mask], img[mask])


@needs_model
def test_the_stored_photo_is_blurred_before_the_model_sees_it(tmp_path, monkeypatch):
    monkeypatch.setenv("STEPSPOTTER_PERCEPTION", "1")
    seen: list[float] = []
    original = imgio.load(FACE)
    x, y, w, h = _face_box(original)

    def model(step, photo_path, model_id=None, **kw) -> StepVerdict:
        seen.append(_sharp(imgio.load(photo_path)[y : y + h, x : x + w]))
        return StepVerdict(step_id=step.id, passed=False, reason="not the step")

    start = tmp_path / "start.jpg"
    shutil.copy(ROOT / "src" / "stepspotter" / "web" / "demo_photos" / "02-panel-inside.jpg", start)
    svc = JobService(
        plan_fn=lambda *a, **k: Plan(job_title="j", safety_class="diy_ok",
                                    steps=[Step(id=1, title="t", action="a", evidence_required="e")]),
        verify_fn=model,
        locate_fn=lambda *a, **k: [],
    )
    state = svc.start("check it", str(start))
    ev = tmp_path / "with-a-face.jpg"
    shutil.copy(FACE, ev)
    svc.verify(state, str(ev))
    assert seen and seen[0] < 0.05 * _sharp(original[y : y + h, x : x + w])
    assert _sharp(imgio.load(ev)[y : y + h, x : x + w]) == pytest.approx(seen[0])  # the file itself
    row = [r for r in store.read_trace(state.job_id) if r["event"] == "perception"][-1]
    assert row["faces_checked"] is True and row["faces_blurred"] == 1


@needs_model
def test_a_report_says_faces_were_checked_only_when_they_were(monkeypatch, tmp_path):
    rep = inspect_evidence(FACE)
    assert rep.privacy.faces_checked is True and rep.privacy.faces_blurred == 1
    monkeypatch.setenv(privacy.MODELS_ENV, str(tmp_path / "none"))
    rep2 = inspect_evidence(FACE)
    assert rep2.privacy.faces_checked is False and rep2.privacy.faces_blurred == 0
