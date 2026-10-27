"""Bounded fixed-input V5 backend check; not a live-scoring or accuracy test."""

from __future__ import annotations

import argparse
import csv
import json
import platform
import resource
import statistics
import time
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

import numpy as np

from digital_spotter.inference.v5_model import FP32_MODEL, V5ModelRuntime
from digital_spotter.inference.v5_preprocessing import verify_copied_file


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", type=Path, required=True)
    args = parser.parse_args()

    with (args.package / "COPY_MANIFEST.csv").open(newline="", encoding="utf-8") as handle:
        copied_paths = [row["destination_path"] for row in csv.DictReader(handle)]
    for relative_path in copied_paths:
        verify_copied_file(args.package, relative_path)
    runtime = V5ModelRuntime(args.package)
    metadata = json.loads(
        (args.package / "saved_models/preprocessing/final_preprocessing.json").read_text(
            encoding="utf-8"
        )
    )
    # Frozen fitted medians are a deterministic compatibility fixture, not a
    # person, sensor measurement, held-out sample, or model accuracy check.
    phases = tuple(
        {
            "phase": phase,
            **{
                name: metadata["phase_medians"][name][phase - 1]
                for name in runtime.preprocessor.temporal_features
            },
        }
        for phase in (1, 2, 3)
    )
    context = dict(metadata["context_medians"])
    temporal, static = runtime.preprocessor.transform(phases, context)
    for _ in range(3):
        runtime.predict_reference_only(phases, context)
    elapsed_ms = []
    for _ in range(20):
        start = time.perf_counter_ns()
        result = runtime.predict_reference_only(phases, context)
        elapsed_ms.append((time.perf_counter_ns() - start) / 1_000_000)
    try:
        backend_version = version("ai-edge-litert")
        backend_name = "ai-edge-litert"
    except PackageNotFoundError:
        backend_version = version("tflite-runtime")
        backend_name = "tflite-runtime"
    print(json.dumps({
        "fixture": "frozen_stage8_phase_and_context_medians",
        "fixture_is_live_data": False,
        "platform": platform.machine(),
        "python": platform.python_version(),
        "numpy": np.__version__,
        "backend": backend_name,
        "backend_version": backend_version,
        "model_sha256": verify_copied_file(args.package, FP32_MODEL),
        "verified_copied_files": len(copied_paths),
        "temporal_shape": list(temporal.shape),
        "context_shape": list(static.shape),
        "raw_probability": result.raw_probability,
        "calibrated_probability": result.calibrated_probability,
        "threshold": result.threshold,
        "predicted_class": result.predicted_class,
        "model_version": result.model_version,
        "reference_only": result.reference_only,
        "timed_inferences": len(elapsed_ms),
        "adapter_latency_ms_p95": sorted(elapsed_ms)[18],
        "adapter_latency_ms_median": statistics.median(elapsed_ms),
        "peak_process_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
    }, sort_keys=True))


if __name__ == "__main__":
    main()
