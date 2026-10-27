#!/usr/bin/env python3
"""Verify the immutable R13-A vision/model characterization checkpoint.

This deliberately does not import the legacy TensorFlow/MediaPipe runtime and does
not claim production model readiness. It verifies source identity, the executable
compatibility manifest, and the deterministic non-real replay boundary.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path, PurePosixPath
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from digital_spotter.contracts import COMPATIBILITY_FEATURE_ORDER  # noqa: E402
from digital_spotter.contracts.model import validate_model_package  # noqa: E402
from digital_spotter.core.replay import (  # noqa: E402
    ReplayAdapter,
    load_replay_fixture,
)


BASELINE_PATH = ROOT / "docs/evidence/r13a-baseline-manifest.json"
EXPECTED_BLOCKERS = {
    "R13A-B01-live-frame-result-not-dispatched-to-session-manager",
    "R13A-B02-live-imu-selected-by-arrival-not-measurement-time",
    "R13A-B03-manual-api-and-session-feature-builders-diverge",
    "R13A-B04-missing-inputs-and-model-failures-can-become-zero-or-mock-results",
    "R13A-B05-camera-stop-restart-does-not-recreate-pose-owner",
    "R13A-B06-camera-capture-time-is-wall-clock-processing-time",
    "R13A-B07-current-model-is-compatibility-only-flex-and-unapproved",
    "R13A-B08-lower-back-imu-does-not-validate-bar-velocity-or-power-semantics",
    "R13A-B09-vision-and-model-dependencies-are-outside-the-canonical-lock",
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _project_file(relative: str) -> Path:
    candidate = PurePosixPath(relative)
    if candidate.is_absolute() or ".." in candidate.parts or "." in candidate.parts:
        raise ValueError(f"unsafe checkpoint path: {relative}")
    resolved = (ROOT / candidate).resolve()
    if not resolved.is_relative_to(ROOT):
        raise ValueError(f"checkpoint path escapes repository: {relative}")
    return resolved


def _expect(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


def validate() -> tuple[dict[str, Any], list[str]]:
    baseline = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    failures: list[str] = []

    _expect(baseline.get("schema_version") == 1, "unsupported baseline schema", failures)
    _expect(baseline.get("checkpoint") == "R13-A", "wrong checkpoint identity", failures)

    verified_files = 0
    for item in baseline.get("source_snapshot", []):
        path = _project_file(item["path"])
        _expect(path.is_file(), f"source missing: {item['path']}", failures)
        if path.is_file():
            _expect(
                _sha256(path) == item["sha256"],
                f"source hash mismatch: {item['path']}",
                failures,
            )
            verified_files += 1

    model_expected = baseline["model"]
    manifest_path = _project_file(model_expected["manifest_path"])
    _expect(
        _sha256(manifest_path) == model_expected["manifest_sha256"],
        "model manifest hash mismatch",
        failures,
    )
    model_result = validate_model_package(manifest_path, production=False)
    manifest = model_result.manifest
    _expect(manifest is not None, "model manifest did not load", failures)
    if manifest is not None:
        _expect(manifest.package_id == model_expected["package_id"], "package ID changed", failures)
        _expect(manifest.model_version == model_expected["model_version"], "model version changed", failures)
        _expect(
            manifest.feature_contract_version == model_expected["feature_contract_version"],
            "feature contract version changed",
            failures,
        )
        _expect(list(manifest.input.shape) == model_expected["input_shape"], "input shape changed", failures)
        _expect(manifest.output.bad_form_threshold == model_expected["threshold"], "threshold changed", failures)
        _expect(
            tuple(feature.name for feature in manifest.features) == COMPATIBILITY_FEATURE_ORDER,
            "feature order changed",
            failures,
        )
        _expect(manifest.release_status == "compatibility_only", "release status changed", failures)
        _expect(manifest.runtime.requires_flex_delegate, "Flex requirement changed", failures)
        _expect(not manifest.evaluation.approved_exercises, "unexpected approved exercise", failures)
    _expect(model_result.compatibility_ready, "compatibility package is invalid", failures)
    _expect(not model_result.production_ready, "compatibility model became production-ready", failures)

    replay_expected = baseline["replay"]
    fixture_path = _project_file(replay_expected["fixture_path"])
    video_path = _project_file(replay_expected["video_path"])
    _expect(_sha256(fixture_path) == replay_expected["fixture_sha256"], "replay fixture hash mismatch", failures)
    _expect(_sha256(video_path) == replay_expected["video_sha256"], "replay video hash mismatch", failures)
    fixture = load_replay_fixture(fixture_path)
    replay_result = ReplayAdapter(fixture).run(verify_expected=True)
    _expect(fixture.provenance.contains_person_data is False, "replay contains person data", failures)
    _expect(replay_result.is_real is False, "replay incorrectly marked real", failures)
    _expect(replay_result.persistence_allowed is False, "replay persistence allowed", failures)

    blockers = set(baseline.get("known_blockers", []))
    _expect(blockers == EXPECTED_BLOCKERS, "known blocker set is incomplete or changed", failures)

    report = {
        "checkpoint": "R13-A",
        "result": "FAIL" if failures else "PASS",
        "base_commit": baseline["base_commit"],
        "validation_level": baseline["scope"]["validation_level"],
        "evidence_environments": baseline["scope"]["evidence_environments"],
        "source_files_verified": verified_files,
        "model": model_result.safe_summary(),
        "replay": replay_result.model_dump(mode="json"),
        "known_blockers": sorted(blockers),
        "failures": failures,
    }
    return report, failures


def main() -> int:
    try:
        report, failures = validate()
    except Exception as exc:
        report = {"checkpoint": "R13-A", "result": "FAIL", "failures": [str(exc)]}
        failures = report["failures"]
    print(json.dumps(report, indent=2, sort_keys=True))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
