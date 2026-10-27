"""Offline candidate boundary checks, not real-world model validation."""

import shutil
import sys
from pathlib import Path

import numpy as np
import pytest

from digital_spotter.inference.v5_candidate import CANDIDATE_VERSION, V5CandidateRuntime
from scripts.run_workout import load_model_runtime, model_reference


PACKAGE = Path(__file__).resolve().parents[1] / "models/digital_spotter_v5_imu_synthetic_r1"


@pytest.fixture(scope="module")
def runtime():
    if not PACKAGE.is_dir():
        pytest.skip("Frozen research candidate package is not installed")
    return V5CandidateRuntime(PACKAGE)


def test_frozen_preprocessing_and_one_litert_inference_match_export(runtime):
    with np.load(PACKAGE / "inference_fixture.npz") as fixture:
        raw = fixture["raw_temporal"][0]
        phases = [
            {"phase": i + 1, **dict(zip(runtime.preprocessor.temporal_features, values))}
            for i, values in enumerate(raw)
        ]
        context = dict(zip(runtime.preprocessor.context_features, fixture["raw_context"][0]))
        temporal, static = runtime.preprocessor.transform(phases, context)
        np.testing.assert_array_equal(temporal, fixture["temporal"][:1])
        np.testing.assert_array_equal(static, fixture["context"][:1])
    result = runtime.predict_reference_only(phases, context)
    with np.load(PACKAGE / "export_parity.npz") as expected:
        assert expected["indices"][0] == 0
        assert result.raw_probability == pytest.approx(float(expected["keras_raw"][0]), abs=1e-4)
        assert result.calibrated_probability == pytest.approx(float(expected["keras_calibrated"][0]), abs=1e-4)
    assert result.model_version == CANDIDATE_VERSION
    assert result.threshold == 0.3976007923801824
    assert result.predicted_class == int(result.calibrated_probability >= result.threshold)
    assert result.reference_only is True
    with pytest.raises(ValueError, match="reference-only"):
        runtime.predict(phases, context)
    assert "tensorflow" not in sys.modules


def test_candidate_rejects_modified_fitted_state(tmp_path, runtime):
    copy = tmp_path / "candidate"
    shutil.copytree(PACKAGE, copy)
    with (copy / "preprocessing.json").open("a") as handle:
        handle.write("\n")
    with pytest.raises(ValueError, match="hash mismatch"):
        V5CandidateRuntime(copy)


def test_launcher_selects_candidate_explicitly_and_keeps_reference_only(runtime):
    loaded = load_model_runtime(PACKAGE, CANDIDATE_VERSION)
    reference = model_reference(loaded, PACKAGE)
    assert reference["model_version"] == CANDIDATE_VERSION
    assert reference["reference_only"] is True
    assert reference["live"] is False
    with pytest.raises(ValueError, match="model version"):
        load_model_runtime(PACKAGE, "unknown-model")
