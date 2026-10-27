"""Opt-in, reference-only runtime for the separately trained synthetic revision."""

from __future__ import annotations

import csv
import hashlib
import json
import math
from pathlib import Path

from .v5_model import V5ModelRuntime
from .v5_preprocessing import V5Preprocessor


CANDIDATE_VERSION = "digital_spotter_v5_imu_synthetic_r1"
CANDIDATE_MODEL = "model_fp32_builtins_batch1.tflite"


def verify_candidate_package(package: Path) -> dict:
    """Detect local artifact drift; this is integrity checking, not signing."""
    package = package.resolve()
    with (package / "SHA256SUMS.csv").open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    listed = {}
    for row in rows:
        name = row["path"]
        path = (package / name).resolve()
        if name in listed or not path.is_relative_to(package) or path.parent != package:
            raise ValueError("V5 candidate artifact path is invalid")
        if (path.stat().st_size != int(row["size_bytes"])
                or hashlib.sha256(path.read_bytes()).hexdigest() != row["sha256"]):
            raise ValueError(f"V5 candidate artifact hash mismatch: {name}")
        listed[name] = row["sha256"]
    if "MODEL_MANIFEST.json" not in listed:
        raise ValueError("V5 candidate manifest is missing from integrity inventory")
    manifest = json.loads((package / "MODEL_MANIFEST.json").read_text(encoding="utf-8"))
    required = {CANDIDATE_MODEL, "preprocessing.json", "calibration.json", "threshold.json", "EXPORT_RESULT.json"}
    if (not required.issubset(manifest["artifacts"])
            or set(listed) != set(manifest["artifacts"]) | {"MODEL_MANIFEST.json"}
            or any(listed[name] != digest for name, digest in manifest["artifacts"].items())):
        raise ValueError("V5 candidate integrity inventories disagree")
    # Use the existing canonical feature order, not a second registry.
    from .v5_features import V5_TEMPORAL_FEATURES
    if (manifest["model_version"] != CANDIDATE_VERSION
            or manifest["selected_runtime_artifact"] != CANDIDATE_MODEL
            or tuple(manifest["temporal_features"]) != V5_TEMPORAL_FEATURES
            or manifest["context_features"] != ["Exercise_ID", "Load_kg"]
            or manifest["temporal_shape"] != [1, 3, 29] or manifest["context_shape"] != [1, 2]
            or manifest["parameters"] != 105681 or manifest["flex_required"] is not False
            or manifest["synthetic_data"] is not True
            or manifest["live_scoring_enabled"] is not False
            or manifest["deployment_ready"] is not False
            or manifest["real_world_validated"] is not False
            or manifest["gyro_unit"] != "rad/s"
            or manifest["accel_unit"] != "m/s^2 specific force, gravity retained"
            or manifest["acquisition_hz"] != 50
            or manifest["phase_reducer"] != "median of pose-associated samples per phase"
            or manifest["export_status"] != "PASS_OFFLINE_NUMERICAL_EXPORT"):
        raise ValueError("V5 candidate model contract mismatch")
    export = json.loads((package / "EXPORT_RESULT.json").read_text(encoding="utf-8"))
    if (export["artifact_sha256"] != listed[CANDIDATE_MODEL] or export["flex_required"] is not False
            or export["status"] != "PASS_OFFLINE_NUMERICAL_EXPORT"
            or export["class_mismatches"] != 0):
        raise ValueError("V5 candidate export evidence mismatch")
    return manifest


class V5CandidateRuntime(V5ModelRuntime):
    """Share preprocessing/inference mechanics while denying live scoring."""

    def __init__(self, package: Path):
        self.package = Path(package)
        manifest = verify_candidate_package(self.package)
        self.model_version = CANDIDATE_VERSION
        read = lambda name: json.loads((self.package / name).read_text(encoding="utf-8"))
        state, calibration, threshold = read("preprocessing.json"), read("calibration.json"), read("threshold.json")
        if (state["model_version"] != self.model_version or calibration["kind"] != "platt"
                or calibration["input"] != "raw_probability"
                or calibration["positive_class"] != 1 or threshold["positive_class"] != 1):
            raise ValueError("V5 candidate fitted decision state mismatch")
        self.preprocessor = V5Preprocessor.from_frozen_state(
            state, expected_features=tuple(manifest["temporal_features"]),
        )
        self.threshold = float(threshold["threshold"])
        self._coefficient = float(calibration["coef"])
        self._intercept = float(calibration["intercept"])
        if not (0 < self.threshold < 1) or not all(map(math.isfinite, (self._coefficient, self._intercept))):
            raise ValueError("V5 candidate decision state is invalid")
        self._initialize_interpreter(self.package / CANDIDATE_MODEL)

    def predict(self, phases, context):
        raise ValueError("V5 synthetic candidate is reference-only; live mounting/feature verification is pending")
