"""Compare local V5 inference with archived Stage 8 Keras reference outputs.

Reads the immutable training archive in memory; prints aggregate numerical
parity only. This is not held-out accuracy or live-hardware evidence.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import numpy as np

from digital_spotter.inference.v5_model import V5ModelRuntime


def _number(value: str) -> float:
    return float(value) if value.strip() else float("nan")


def _phase(raw: dict[str, str], order: tuple[str, ...]) -> dict[str, object]:
    values = {name: _number(raw[name]) for name in order if name in raw}
    values["Hip_Flexion_Asymmetry"] = abs(_number(raw["Angle_Hip_Flexion_L"]) - _number(raw["Angle_Hip_Flexion_R"]))
    values["Knee_Flexion_Asymmetry"] = abs(_number(raw["Angle_Knee_Flexion_L"]) - _number(raw["Angle_Knee_Flexion_R"]))
    values["Ankle_Dorsiflexion_Asymmetry"] = abs(_number(raw["Angle_Ankle_Dorsiflexion_L"]) - _number(raw["Angle_Ankle_Dorsiflexion_R"]))
    acceleration = [_number(raw[f"IMU_Acc_{axis}"]) for axis in "XYZ"]
    values["IMU_Acc_Magnitude"] = float(np.sqrt(sum(value * value for value in acceleration)))
    values["Knee_Hip_Coupling_L"] = _number(raw["Angle_Knee_Flexion_L"]) / (_number(raw["Angle_Hip_Flexion_L"]) + 1e-6)
    values["Knee_Hip_Coupling_R"] = _number(raw["Angle_Knee_Flexion_R"]) / (_number(raw["Angle_Hip_Flexion_R"]) + 1e-6)
    # The training sequence store cast every engineered phase value to float32
    # before the fitted preprocessor received it.
    return {"phase": int(raw["Rep_Phase"]), **{name: np.float32(values[name]) for name in order}}


def validate(package: Path, master_csv: Path, reference_csv: Path) -> dict[str, float | int | bool]:
    runtime = V5ModelRuntime(package)
    with reference_csv.open(newline="", encoding="utf-8") as handle:
        reference = list(csv.DictReader(handle))
    if len(reference) != 64 or not all(row["parity_only_not_generalisation"] == "True" for row in reference):
        raise ValueError("expected exactly 64 Stage 8 parity-only references")
    keys = {(row["Session_ID"], row["Rep_ID"]) for row in reference}
    grouped: dict[tuple[str, str], list[dict[str, str]]] = {key: [] for key in keys}
    with master_csv.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            key = (row["Session_ID"], row["Rep_ID"])
            if key in grouped:
                grouped[key].append(row)
    raw_errors: list[float] = []
    calibrated_errors: list[float] = []
    label_agreements = 0
    for row in reference:
        raw_phases = sorted(grouped[(row["Session_ID"], row["Rep_ID"])], key=lambda item: int(item["Rep_Phase"]))
        if len(raw_phases) != 3:
            raise ValueError("reference repetition does not have three phases")
        phases = [_phase(item, runtime.preprocessor.temporal_features) for item in raw_phases]
        context = {
            "Exercise_ID": float(np.float32(_number(raw_phases[0]["Exercise_ID"]))),
            "Load_kg": float(np.float32(_number(raw_phases[0]["Load_kg"]))),
        }
        result = runtime.predict_reference_only(phases, context)
        raw_errors.append(abs(result.raw_probability - float(row["keras_raw_probability"])))
        calibrated_errors.append(abs(result.calibrated_probability - float(row["keras_calibrated_probability"])))
        label_agreements += result.predicted_class == int(row["keras_y_pred"])
        if result.threshold != float(row["deployment_threshold"]):
            raise ValueError("reference deployment threshold mismatch")
    return {
        "sample_count": len(reference),
        "max_raw_difference": max(raw_errors),
        "mean_raw_difference": float(np.mean(raw_errors)),
        "max_calibrated_difference": max(calibrated_errors),
        "label_agreement_count": label_agreements,
        "parity_only_not_generalisation": True,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--master-csv", type=Path, required=True)
    parser.add_argument("--reference-csv", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(validate(args.package, args.master_csv, args.reference_csv), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
