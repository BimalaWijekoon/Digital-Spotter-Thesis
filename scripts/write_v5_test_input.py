#!/usr/bin/env python3
"""Run one frozen V5 fitted-median input on the Pi; export no live analysis."""

from __future__ import annotations

import argparse
import csv
import json
import os
import tempfile
from pathlib import Path

from digital_spotter.inference.v5_model import V5ModelRuntime
from digital_spotter.inference.v5_preprocessing import verify_copied_file


def calculate(package: Path) -> dict[str, object]:
    with (package / "COPY_MANIFEST.csv").open(newline="", encoding="utf-8") as handle:
        copied_paths = [row["destination_path"] for row in csv.DictReader(handle)]
    for relative_path in copied_paths:
        verify_copied_file(package, relative_path)

    runtime = V5ModelRuntime(package)
    metadata = json.loads(
        (package / "saved_models/preprocessing/final_preprocessing.json").read_text(encoding="utf-8")
    )
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
    prediction = runtime.predict_reference_only(phases, context)
    if not prediction.reference_only:
        raise RuntimeError("V5 test input must remain reference-only")
    return {
        "version": "v5_test_input_v1",
        "source": "frozen_fitted_medians",
        "live": False,
        "reference_only": True,
        "model_version": prediction.model_version,
        "raw_probability": prediction.raw_probability,
        "calibrated_probability": prediction.calibrated_probability,
        "threshold": prediction.threshold,
        "predicted_class": prediction.predicted_class,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = calculate(args.package)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=args.output.parent, prefix=".v5-test-input-",
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            json.dump(result, handle, sort_keys=True)
            handle.write("\n")
        os.replace(temporary, args.output)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    print(json.dumps({"model_version": result["model_version"], "source": result["source"],
                      "live": False, "output": str(args.output)}, sort_keys=True))


if __name__ == "__main__":
    main()
