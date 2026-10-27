"""Offline V5 contract checks; these are not live-sensor or accuracy evidence."""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

from digital_spotter.inference.v5_model import V5ModelRuntime
from digital_spotter.inference.v5_preprocessing import V5Preprocessor
from scripts.export_v5_portable_state import _load_preprocessor


PACKAGE = Path(__file__).resolve().parents[1] / "models" / "digital_spotter_v5"
EXPECTED_TEMPORAL = (
    "Vis_L_Shoulder_X", "Vis_L_Shoulder_Y", "Vis_R_Shoulder_X", "Vis_R_Shoulder_Y",
    "Vis_L_Hip_X", "Vis_L_Hip_Y", "Vis_R_Hip_X", "Vis_R_Hip_Y",
    "Vis_L_Knee_X", "Vis_L_Knee_Y", "Vis_R_Knee_X", "Vis_R_Knee_Y",
    "Vis_L_Ankle_X", "Vis_L_Ankle_Y", "Vis_R_Ankle_X", "Vis_R_Ankle_Y",
    "Angle_Trunk_Inclination", "Hip_Flexion_Asymmetry",
    "Knee_Flexion_Asymmetry", "Ankle_Dorsiflexion_Asymmetry",
    "Knee_Hip_Coupling_L", "Knee_Hip_Coupling_R",
    "IMU_Acc_X", "IMU_Acc_Y", "IMU_Acc_Z",
    "IMU_Gyro_X", "IMU_Gyro_Y", "IMU_Gyro_Z", "IMU_Acc_Magnitude",
)
FORBIDDEN = {
    "V_Bar_Velocity_Vertical", "P_Bar_Power_Watts", "Smoothness_Jerk",
    "Velocity_Decel_Ratio", "Subject_Height_cm", "Subject_Weight_kg",
    "Femur_Tibia_Ratio", "BMI",
}


def _source_derived_inputs():
    metadata = json.loads((PACKAGE / "saved_models/preprocessing/final_preprocessing.json").read_text())
    phases = [
        {"phase": phase, **{name: metadata["phase_medians"][name][phase - 1] for name in EXPECTED_TEMPORAL}}
        for phase in (1, 2, 3)
    ]
    context = dict(metadata["context_medians"])
    return phases, context


def test_copied_artifacts_match_source_manifest():
    with (PACKAGE / "COPY_MANIFEST.csv").open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert rows
    assert len(rows) == 24
    copied_paths = {path.relative_to(PACKAGE).as_posix() for path in PACKAGE.rglob("*") if path.is_file()}
    assert {row["destination_path"] for row in rows} == copied_paths - {"COPY_MANIFEST.csv", "portable_state.json", "RUNTIME_MANIFEST.json"}
    for row in rows:
        destination = PACKAGE / row["destination_path"]
        assert destination.stat().st_size == int(row["size_bytes"])
        digest = hashlib.sha256(destination.read_bytes()).hexdigest()
        assert digest == row["source_sha256"] == row["copied_sha256"]
        assert row["match"] == "true"


def test_exact_stage8_order_and_shapes():
    preprocessor = V5Preprocessor(PACKAGE)
    assert preprocessor.temporal_features == EXPECTED_TEMPORAL
    assert preprocessor.context_features == ("Exercise_ID", "Load_kg")
    assert not FORBIDDEN.intersection(preprocessor.temporal_features)
    phases, context = _source_derived_inputs()
    temporal, static = preprocessor.transform(phases, context)
    assert temporal.shape == (1, 3, 29)
    assert static.shape == (1, 2)
    assert temporal.dtype == static.dtype == np.float32
    assert np.isfinite(temporal).all() and np.isfinite(static).all()


def test_invalid_phase_and_v4_proxy_fail_closed():
    preprocessor = V5Preprocessor(PACKAGE)
    phases, context = _source_derived_inputs()
    with pytest.raises(ValueError, match="phase order"):
        preprocessor.transform((phases[1], phases[0], phases[2]), context)
    with pytest.raises(ValueError, match="exactly three"):
        preprocessor.transform(phases + [phases[2]], context)
    phases[0]["V_Bar_Velocity_Vertical"] = 0.0
    with pytest.raises(ValueError, match="feature keys"):
        preprocessor.transform(phases, context)


def test_model_load_infer_calibrate_and_threshold():
    phases, context = _source_derived_inputs()
    result = V5ModelRuntime(PACKAGE).predict(phases, context)
    assert 0.0 <= result.raw_probability <= 1.0
    assert 0.0 <= result.calibrated_probability <= 1.0
    assert result.threshold == pytest.approx(0.20549274582373653)
    assert result.predicted_class == int(result.calibrated_probability >= result.threshold)
    assert result.model_version == "digital_spotter_v5_scope_faithful"
    assert result.reference_only is False


def test_missing_imu_is_reference_only():
    phases, context = _source_derived_inputs()
    phases[0]["IMU_Acc_X"] = None
    runtime = V5ModelRuntime(PACKAGE)
    with pytest.raises(ValueError, match="required IMU"):
        runtime.predict(phases, context)
    assert runtime.predict_reference_only(phases, context).reference_only is True


def test_portable_preprocessing_matches_trusted_fitted_scalers():
    """Compare portable numeric transform to the hash-verified Stage 8 joblib state."""
    phases, context = _source_derived_inputs()
    phases[0]["IMU_Acc_X"] = None
    phases[1]["IMU_Acc_Y"] = 1_000_000.0
    context["Load_kg"] = None
    portable_temporal, portable_context = V5Preprocessor(PACKAGE).transform(phases, context)
    trusted = _load_preprocessor(PACKAGE / "saved_models/preprocessing/final_preprocessor.joblib")
    raw_temporal = np.asarray(
        [[record[name] for name in EXPECTED_TEMPORAL] for record in phases], dtype=np.float64
    )
    for column, name in enumerate(EXPECTED_TEMPORAL):
        for phase_index in range(3):
            if np.isnan(raw_temporal[phase_index, column]):
                raw_temporal[phase_index, column] = trusted.phase_medians[name][phase_index]
        if name in trusted.winsor_bounds:
            raw_temporal[:, column] = np.clip(raw_temporal[:, column], *trusted.winsor_bounds[name])
    raw_context = np.asarray(
        [context[name] if context[name] is not None else trusted.context_medians[name]
         for name in ("Exercise_ID", "Load_kg")], dtype=np.float64
    )
    expected_temporal = trusted.temporal_scaler.transform(raw_temporal).astype(np.float32)[None, :, :]
    expected_context = trusted.context_scaler.transform(raw_context[None, :]).astype(np.float32)
    np.testing.assert_allclose(portable_temporal, expected_temporal, rtol=1e-6, atol=1e-6)
    np.testing.assert_allclose(portable_context, expected_context, rtol=1e-6, atol=1e-6)
