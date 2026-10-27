"""One synthetic-fixture candidate check on a host/Pi; no live scoring."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import sys
import time
from importlib.metadata import version
from pathlib import Path

import numpy as np

from digital_spotter.inference.v5_candidate import CANDIDATE_MODEL, V5CandidateRuntime


def validate(package: Path) -> dict:
    runtime = V5CandidateRuntime(package)  # Verifies the full artifact inventory.
    with np.load(package / "inference_fixture.npz") as fixture:
        phases = tuple({"phase": index + 1, **dict(zip(runtime.preprocessor.temporal_features, row))}
                       for index, row in enumerate(fixture["raw_temporal"][0]))
        context = dict(zip(runtime.preprocessor.context_features, fixture["raw_context"][0]))
        temporal, static = runtime.preprocessor.transform(phases, context)
        np.testing.assert_allclose(temporal, fixture["temporal"][:1], rtol=1e-6, atol=1e-6)
        np.testing.assert_allclose(static, fixture["context"][:1], rtol=1e-6, atol=1e-6)
    started = time.perf_counter_ns()
    prediction = runtime.predict_reference_only(phases, context)
    elapsed_ms = (time.perf_counter_ns() - started) / 1e6
    with np.load(package / "export_parity.npz") as expected:
        if expected["indices"][0] != 0:
            raise ValueError("Expected source fixture index zero")
        raw_error = abs(prediction.raw_probability - float(expected["keras_raw"][0]))
        calibrated_error = abs(prediction.calibrated_probability - float(expected["keras_calibrated"][0]))
        expected_class = int(expected["keras_calibrated"][0] >= prediction.threshold)
    if (raw_error > 1e-4 or calibrated_error > 1e-4 or prediction.predicted_class != expected_class
            or not prediction.reference_only or "tensorflow" in sys.modules):
        raise ValueError("Candidate numerical/reference-only boundary check failed")
    backend = "ai-edge-litert" if "ai_edge_litert.interpreter" in sys.modules else "tflite-runtime"
    return {
        "status": "PASS_REFERENCE_INFERENCE", "model_version": prediction.model_version,
        "model_sha256": hashlib.sha256((package / CANDIDATE_MODEL).read_bytes()).hexdigest(),
        "machine": platform.machine(), "python": platform.python_version(),
        "numpy": np.__version__, "backend": backend, "backend_version": version(backend),
        "fixture": "provided_synthetic_repetition_zero", "fixture_is_live_data": False,
        "temporal_shape": list(temporal.shape), "context_shape": list(static.shape),
        "raw_probability": prediction.raw_probability,
        "calibrated_probability": prediction.calibrated_probability,
        "threshold": prediction.threshold, "predicted_class": prediction.predicted_class,
        "raw_abs_error_vs_keras": raw_error, "calibrated_abs_error_vs_keras": calibrated_error,
        "reference_only": prediction.reference_only, "tensorflow_imported": False,
        "model_invocations": 1, "single_adapter_call_ms": elapsed_ms,
        "latency_benchmark": False, "live_scoring_enabled": False,
        "real_world_validated": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(validate(args.package), sort_keys=True))


if __name__ == "__main__":
    main()
