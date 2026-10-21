"""The perception eval harness: builds deterministically, splits by scene, caps the model.

Built into a tmp dir (STEPSPOTTER_EVAL_CASES) so the test never writes into the repo, and
run on a handful of cases so it stays fast. No model is ever called here: the model
configs are exercised with --max-llm-calls 0 and --dry-run only.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _load(name: str):
    spec = importlib.util.spec_from_file_location(f"eval_{name}", ROOT / "eval" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    cases_dir = tmp_path_factory.mktemp("eval-cases")
    mp = pytest.MonkeyPatch()
    mp.setenv("STEPSPOTTER_EVAL_CASES", str(cases_dir))
    build = _load("build_set")
    assert build.main() == 0
    manifest = json.loads((cases_dir / "manifest.json").read_text())
    yield cases_dir, manifest
    mp.undo()


def test_every_case_carries_its_group_split_and_provenance(built):
    _dir, manifest = built
    cases = manifest["cases"]
    assert len(cases) == manifest["counts"]["cases"] >= 90
    for c in cases:
        assert c["group"] and c["scene"] and c["split"] in ("calibration", "test")
        assert c["provenance"]["kind"] in ("real", "synthetic")
        assert len(c["evidence_sha256"]) == 64
        if c["provenance"]["kind"] == "synthetic":
            assert "params" in c["provenance"] and c["provenance"]["generator"]


def test_the_split_is_by_scene_and_no_case_mixes_the_halves(built):
    _dir, manifest = built
    scenes = json.loads((ROOT / "fixtures" / "perception" / "scenes.json").read_text())
    by_scene = {}
    for c in manifest["cases"]:
        by_scene.setdefault(c["scene"], set()).add(c["split"])
        files = [c["reference"], c["evidence"]] + [e["path"] for e in c["earlier"]]
        halves = set()
        for pid, meta in scenes["photos"].items():
            if any(meta["file"] in f for f in files):
                halves.add("calibration" if meta["scene"] in scenes["split"]["calibration"] else "test")
        assert halves <= {c["split"]}, c["id"]
    assert all(len(s) == 1 for s in by_scene.values()), by_scene


def test_a_rebuild_is_byte_identical(built, tmp_path, monkeypatch):
    _dir, first = built
    monkeypatch.setenv("STEPSPOTTER_EVAL_CASES", str(tmp_path))
    build = _load("build_set")
    build.main()
    again = json.loads((tmp_path / "manifest.json").read_text())
    assert [c["evidence_sha256"] for c in again["cases"]] == [c["evidence_sha256"] for c in first["cases"]]


def test_the_opencv_config_scores_a_few_cases(built, monkeypatch):
    cases_dir, manifest = built
    monkeypatch.setenv("STEPSPOTTER_EVAL_CASES", str(cases_dir))
    run = _load("run")
    ids = [c["id"] for c in manifest["cases"] if c["group"] == "02" and c["class"] in ("good_rotate", "blur_gaussian", "touched_avoid")]
    res = run.run("opencv", 0, False, "all", only=ids)
    by = {r["class"]: r for r in res["rows"]}
    assert by["good_rotate"]["outcome"] == "accepted"
    assert by["blur_gaussian"]["outcome"] == "caught" and by["blur_gaussian"]["decision"] == "retake"
    assert by["touched_avoid"]["decision"] == "touched_avoid"
    assert res["llm_calls_made"] == 0
    assert "| touched_avoid | bad |" in run.markdown(res)


def test_the_model_configs_spend_nothing_at_cap_zero_and_in_a_dry_run(built, monkeypatch):
    cases_dir, manifest = built
    monkeypatch.setenv("STEPSPOTTER_EVAL_CASES", str(cases_dir))
    monkeypatch.setitem(sys.modules, "stepspotter.verifier", None)  # importing it would now fail
    run = _load("run")
    ids = [c["id"] for c in manifest["cases"] if c["group"] == "01"][:5]
    capped = run.run("llm", 0, False, "all", only=ids)
    assert capped["llm_calls_made"] == 0
    assert {r["llm"]["status"] for r in capped["rows"]} == {"skipped_cap"}
    assert {r["outcome"] for r in capped["rows"]} == {"not_run"}
    dry = run.run("combined", 120, True, "all", only=ids)
    assert dry["llm_calls_made"] == 0 and dry["would_call"]
    assert all(w["evidence"] for w in dry["would_call"])
