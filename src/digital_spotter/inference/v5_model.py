"""Offline-capable V5 TFLite inference; not connected to live scoring yet."""

from __future__ import annotations

import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .v5_preprocessing import V5Preprocessor, verify_copied_file, verify_runtime_manifest


MODEL_VERSION = "digital_spotter_v5_scope_faithful"
FP32_MODEL = "saved_models/tflite/final_v5_fp32_builtins_frozen_batch1.tflite"


@dataclass(frozen=True)
class V5Prediction:
    raw_probability: float
    calibrated_probability: float
    predicted_class: int
    threshold: float
    model_version: str = MODEL_VERSION
    reference_only: bool = False


def _interpreter_type():
    try:
        from ai_edge_litert.interpreter import Interpreter
    except ImportError:
        try:
            from tflite_runtime.interpreter import Interpreter
        except ImportError as exc:
            raise RuntimeError("LiteRT/TFLite interpreter is unavailable") from exc
    return Interpreter


class V5ModelRuntime:
    """One batch-one, two-input V5 model with frozen Platt/threshold policy."""

    def __init__(self, package: Path):
        self.package = Path(package)
        self.model_version = MODEL_VERSION
        runtime_manifest = verify_runtime_manifest(self.package)
        self.preprocessor = V5Preprocessor(self.package)
        model_hash = verify_copied_file(self.package, FP32_MODEL)
        if runtime_manifest["selected_model"] != FP32_MODEL or runtime_manifest["selected_model_sha256"] != model_hash:
            raise ValueError("V5 selected model mismatch")
        calibration_rel = "saved_models/calibration/final_calibration_policy.json"
        threshold_rel = "saved_models/threshold/final_threshold.json"
        verify_copied_file(self.package, calibration_rel)
        verify_copied_file(self.package, threshold_rel)
        calibration = json.loads((self.package / calibration_rel).read_text(encoding="utf-8"))
        threshold = json.loads((self.package / threshold_rel).read_text(encoding="utf-8"))
        state = json.loads((self.package / "portable_state.json").read_text(encoding="utf-8"))
        if calibration["policy"] != "PLATT" or threshold["calibration_policy"] != "PLATT":
            raise ValueError("V5 calibration policy mismatch")
        if state["source_sha256"]["saved_models/calibration/final_calibrator.joblib"] != verify_copied_file(
            self.package, "saved_models/calibration/final_calibrator.joblib"
        ):
            raise ValueError("V5 Platt source hash mismatch")
        self.threshold = float(threshold["threshold"])
        if self.threshold != runtime_manifest["threshold"]:
            raise ValueError("V5 threshold mismatch")
        self._coefficient = float(state["platt"]["coefficient"])
        self._intercept = float(state["platt"]["intercept"])
        if not (0 < self.threshold < 1) or not math.isfinite(self._coefficient) or not math.isfinite(self._intercept):
            raise ValueError("V5 decision state is invalid")

        self._initialize_interpreter(self.package / FP32_MODEL)

    def _initialize_interpreter(self, model_path: Path) -> None:
        """Shared strict TFLite signature validation for versioned packages."""
        interpreter = _interpreter_type()(model_path=str(model_path), num_threads=1)
        interpreter.allocate_tensors()
        inputs = interpreter.get_input_details()
        outputs = interpreter.get_output_details()
        if len(inputs) != 2 or len(outputs) != 1:
            raise ValueError("V5 TFLite signature must have two inputs and one output")
        self._input_indices: dict[tuple[int, ...], int] = {}
        for item in inputs:
            shape = tuple(int(value) for value in item["shape"])
            if shape not in ((1, 3, 29), (1, 2)) or item["dtype"] != np.float32:
                raise ValueError("V5 TFLite input shape/dtype mismatch")
            self._input_indices[shape] = int(item["index"])
        if set(self._input_indices) != {(1, 3, 29), (1, 2)}:
            raise ValueError("V5 TFLite input signature is incomplete")
        output = outputs[0]
        if tuple(int(value) for value in output["shape"]) != (1, 1) or output["dtype"] != np.float32:
            raise ValueError("V5 TFLite output shape/dtype mismatch")
        self._output_index = int(output["index"])
        self._interpreter = interpreter

    def predict(
        self,
        phases: Sequence[Mapping[str, object]],
        context: Mapping[str, object],
    ) -> V5Prediction:
        # Preprocessing supports frozen median imputation for numerical parity,
        # but a live model result must not conceal absent IMU or user context.
        for record in phases:
            for name in ("IMU_Acc_X", "IMU_Acc_Y", "IMU_Acc_Z", "IMU_Gyro_X", "IMU_Gyro_Y", "IMU_Gyro_Z", "IMU_Acc_Magnitude"):
                value = record.get(name)
                if value is None or (isinstance(value, (float, np.floating)) and math.isnan(value)):
                    raise ValueError(f"V5 required IMU feature is missing: {name}")
        for name in ("Exercise_ID", "Load_kg"):
            value = context.get(name)
            if value is None or (isinstance(value, (float, np.floating)) and math.isnan(value)):
                raise ValueError(f"V5 required context is missing: {name}")
        if context["Exercise_ID"] not in (0, 1) or float(context["Load_kg"]) < 0:
            raise ValueError("V5 exercise/load context is invalid")
        return self._infer(*self.preprocessor.transform(phases, context), reference_only=False)

    def predict_reference_only(
        self,
        phases: Sequence[Mapping[str, object]],
        context: Mapping[str, object],
    ) -> V5Prediction:
        """Reproduce Stage 8 missing-value behavior; never use for live feedback."""
        return self._infer(*self.preprocessor.transform(phases, context), reference_only=True)

    def _infer(self, temporal: np.ndarray, static: np.ndarray, *, reference_only: bool) -> V5Prediction:
        self._interpreter.set_tensor(self._input_indices[(1, 3, 29)], temporal)
        self._interpreter.set_tensor(self._input_indices[(1, 2)], static)
        self._interpreter.invoke()
        raw = float(self._interpreter.get_tensor(self._output_index)[0, 0])
        if not math.isfinite(raw) or not 0 <= raw <= 1:
            raise ValueError("V5 model returned invalid probability")
        calibrated = 1.0 / (1.0 + math.exp(-(self._coefficient * raw + self._intercept)))
        return V5Prediction(
            raw_probability=raw,
            calibrated_probability=calibrated,
            predicted_class=int(calibrated >= self.threshold),
            threshold=self.threshold,
            model_version=self.model_version,
            reference_only=reference_only,
        )
