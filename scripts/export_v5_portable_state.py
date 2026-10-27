"""Print portable V5 scaler/Platt parameters from the trusted Stage 8 copy.

This is an offline, operator-run export. Joblib is pickle-based: never run this
against a package that has not been independently approved and hash-checked.
It prints JSON to stdout; it does not modify the source or copied artifacts.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
import types
from pathlib import Path

import joblib
import numpy as np


PREPROCESSOR = "saved_models/preprocessing/final_preprocessor.joblib"
CALIBRATOR = "saved_models/calibration/final_calibrator.joblib"
METADATA = "saved_models/preprocessing/final_preprocessing.json"


def _hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _check_copy(package: Path, relative: str) -> str:
    with (package / "COPY_MANIFEST.csv").open(newline="") as handle:
        rows = {row["destination_path"]: row for row in csv.DictReader(handle)}
    row = rows[relative]
    actual = _hash(package / relative)
    if row["match"] != "true" or actual != row["source_sha256"]:
        raise ValueError(f"unverified V5 input: {relative}")
    return actual


def _load_preprocessor(path: Path):
    # The serialized class carries data only; avoid importing the training
    # pipeline, which imports TensorFlow and training-only dependencies.
    module = types.ModuleType("v5_stage1_6_pipeline")
    stub = type("FoldPreprocessor", (), {})
    stub.__module__ = module.__name__
    module.FoldPreprocessor = stub
    old = sys.modules.get(module.__name__)
    sys.modules[module.__name__] = module
    try:
        return joblib.load(path)
    finally:
        if old is None:
            del sys.modules[module.__name__]
        else:
            sys.modules[module.__name__] = old


def export(package: Path) -> dict:
    package = package.resolve()
    source_hashes = {name: _check_copy(package, name) for name in (PREPROCESSOR, CALIBRATOR, METADATA)}
    metadata = json.loads((package / METADATA).read_text(encoding="utf-8"))
    preprocessor = _load_preprocessor(package / PREPROCESSOR)
    calibrator = joblib.load(package / CALIBRATOR)

    temporal = tuple(metadata["temporal_feature_order"])
    context = tuple(metadata["context_feature_order"])
    if (
        preprocessor.family != "STAGE8_FINAL_SCOPE_FAITHFUL"
        or preprocessor.use_missingness
        or list(temporal) != list(preprocessor.dynamic_columns)
        or list(context) != list(preprocessor.context_columns)
        or preprocessor.fit_state_hash != metadata["state_hash"]
        or metadata["phase_order"] != [1, 2, 3]
        or len(temporal) != 29
        or context != ("Exercise_ID", "Load_kg")
    ):
        raise ValueError("V5 preprocessor contract mismatch")
    if type(calibrator).__name__ != "LogisticRegression" or list(calibrator.classes_) != [0, 1]:
        raise ValueError("unexpected V5 Platt calibrator")

    def scaler_state(scaler, size: int) -> dict[str, list[float]]:
        mean = np.asarray(scaler.mean_, dtype=np.float64)
        scale = np.asarray(scaler.scale_, dtype=np.float64)
        if mean.shape != (size,) or scale.shape != (size,):
            raise ValueError("V5 scaler shape mismatch")
        if not np.isfinite(mean).all() or not np.isfinite(scale).all() or (scale <= 0).any():
            raise ValueError("invalid V5 scaler state")
        return {"mean": mean.tolist(), "scale": scale.tolist()}

    coef = np.asarray(calibrator.coef_, dtype=np.float64)
    intercept = np.asarray(calibrator.intercept_, dtype=np.float64)
    if coef.shape != (1, 1) or intercept.shape != (1,):
        raise ValueError("V5 Platt shape mismatch")
    if not np.isfinite(coef).all() or not np.isfinite(intercept).all():
        raise ValueError("invalid V5 Platt state")

    return {
        "schema_version": 1,
        "model_version": "digital_spotter_v5_scope_faithful",
        "phase_order": [1, 2, 3],
        "temporal_feature_order": list(temporal),
        "context_feature_order": list(context),
        "temporal_scaler": scaler_state(preprocessor.temporal_scaler, 29),
        "context_scaler": scaler_state(preprocessor.context_scaler, 2),
        "platt": {"coefficient": float(coef[0, 0]), "intercept": float(intercept[0])},
        "source_sha256": source_hashes,
        "source_state_hash": metadata["state_hash"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package", type=Path, help="verified local V5 package directory")
    args = parser.parse_args()
    print(json.dumps(export(args.package), sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
