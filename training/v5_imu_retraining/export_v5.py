"""Export the completed local research run; never activate it in the runtime.

One FP32, built-in-operator TFLite export follows the previously successful
fixed-batch-one, frozen-weight conversion. No quantization or model search.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import shutil
import time
from pathlib import Path

import numpy as np

from .v5_training import (
    CONTEXT, FEATURES, MODEL_VERSION, ROOT, Preprocessor, _predict,
    apply_calibration, configure_tensorflow, load_dataset, sha, write_json,
)


def export_run(run: Path, data_dir: Path) -> dict:
    result = json.loads((run/"TRAINING_RESULT.json").read_text())
    if result["completed_lstm_fits"] != 26 or result["model_version"] != MODEL_VERSION:
        raise ValueError("Expected the completed main-model-only training run")
    run_contract = json.loads((run/"RUN_CONTRACT.json").read_text())
    if sha(ROOT/"v5_training.py") != run_contract["contract"]["code_sha256"]:
        raise ValueError("Training source changed during/after this run; inspect before exporting")
    package = run/"package"
    manifest_path = package/"MODEL_MANIFEST.json"
    manifest = json.loads(manifest_path.read_text())
    if manifest["deployment_ready"] is not False or manifest["real_world_validated"] is not False:
        raise ValueError("Synthetic export must not claim live validation")
    for name, digest in manifest["artifacts"].items():
        if sha(package/name) != digest:
            raise ValueError("Package artifact hash mismatch: " + name)
    if (package/"EXPORT_RESULT.json").exists():
        raise FileExistsError("Export already recorded; preserve it, do not overwrite")
    data = load_dataset(data_dir)
    if data.master_sha256 != result["dataset_sha256"]:
        raise ValueError("Export dataset differs from training")
    processor = Preprocessor.from_state(json.loads((package/"preprocessing.json").read_text()))
    temporal, context = processor.transform(data.temporal, data.context)
    with np.load(package/"inference_fixture.npz") as fixture:
        rebuilt = processor.transform(fixture["raw_temporal"], fixture["raw_context"])
        np.testing.assert_array_equal(rebuilt[0], fixture["temporal"])
        np.testing.assert_array_equal(rebuilt[1], fixture["context"])
    tf = configure_tensorflow()
    model = tf.keras.models.load_model(package/"model.keras", compile=False)
    if model.count_params() != 105681 or [tuple(x.shape[1:]) for x in model.inputs] != [(3, 29), (2,)]:
        raise ValueError("Reloaded model architecture mismatch")
    reloaded = _predict(model, (temporal, context))
    with np.load(run/"fits/final/predictions.npz") as expected:
        np.testing.assert_array_equal(expected["indices"], np.arange(len(data.y)))
        reload_error = float(np.max(np.abs(reloaded-expected["raw_probability"])))
        if reload_error > 1e-6:
            raise ValueError("Saved/reloaded Keras prediction drift")

    @tf.function(input_signature=[
        tf.TensorSpec([1, 3, 29], tf.float32, name="temporal_input"),
        tf.TensorSpec([1, 2], tf.float32, name="context_input"),
    ])
    def infer(temporal_input, context_input):
        return model([temporal_input, context_input], training=False)

    from tensorflow.python.framework.convert_to_constants import convert_variables_to_constants_v2
    with tf.device("/CPU:0"):
        frozen = convert_variables_to_constants_v2(infer.get_concrete_function())
    if len(frozen.inputs) != 2:
        raise ValueError("Frozen graph must have only the two model inputs")
    converter = tf.lite.TFLiteConverter.from_concrete_functions([frozen])
    converter.target_spec.supported_ops = [tf.lite.OpsSet.TFLITE_BUILTINS]
    started = time.monotonic()
    payload = converter.convert()
    conversion_seconds = time.monotonic()-started
    artifact = package/"model_fp32_builtins_batch1.tflite"
    if artifact.exists():
        raise FileExistsError("Preserve existing conversion evidence")
    artifact.write_bytes(payload)
    from tensorflow.lite.python import schema_py_generated as schema
    flat = schema.Model.GetRootAsModel(payload, 0)
    names = {value: name for name, value in vars(schema.BuiltinOperator).items() if isinstance(value, int)}
    ops = []
    for index in range(flat.OperatorCodesLength()):
        code = flat.OperatorCodes(index)
        builtin = max(code.BuiltinCode(), code.DeprecatedBuiltinCode())
        if builtin == schema.BuiltinOperator.CUSTOM or code.CustomCode():
            raise ValueError("TFLite contains custom/Flex operators")
        ops.append(names[builtin])
    interpreter = tf.lite.Interpreter(model_content=payload, num_threads=2)
    interpreter.allocate_tensors()
    inputs = {tuple(item["shape"]): item for item in interpreter.get_input_details()}
    outputs = interpreter.get_output_details()
    if set(inputs) != {(1, 3, 29), (1, 2)} or len(outputs) != 1 or tuple(outputs[0]["shape"]) != (1, 1):
        raise ValueError("TFLite input/output signature mismatch")
    if any(item["dtype"] != np.float32 for item in [*inputs.values(), *outputs]):
        raise ValueError("Expected FP32 TFLite inputs and output")
    # Across all profiles/exercises; purely numerical export parity, not accuracy.
    indices = np.linspace(0, len(data.y)-1, 64, dtype=int)
    actual, milliseconds = [], []
    for index in indices:
        interpreter.set_tensor(inputs[(1, 3, 29)]["index"], temporal[index:index+1])
        interpreter.set_tensor(inputs[(1, 2)]["index"], context[index:index+1])
        started = time.perf_counter()
        interpreter.invoke()
        milliseconds.append(1000*(time.perf_counter()-started))
        actual.append(float(interpreter.get_tensor(outputs[0]["index"])[0, 0]))
    actual = np.asarray(actual)
    keras_raw = reloaded[indices]
    calibration = json.loads((package/"calibration.json").read_text())
    threshold = json.loads((package/"threshold.json").read_text())["threshold"]
    keras_probability = apply_calibration(keras_raw, calibration)
    lite_probability = apply_calibration(actual, calibration)
    error = float(np.max(np.abs(keras_raw-actual)))
    calibrated_error = float(np.max(np.abs(keras_probability-lite_probability)))
    mismatches = int(np.count_nonzero((keras_probability >= threshold) != (lite_probability >= threshold)))
    if error > 1e-4 or calibrated_error > 1e-4 or mismatches:
        raise ValueError(f"Export parity failed: raw={error}, calibrated={calibrated_error}, classes={mismatches}")
    np.savez_compressed(package/"export_parity.npz", indices=indices, keras_raw=keras_raw,
                        tflite_raw=actual, keras_calibrated=keras_probability,
                        tflite_calibrated=lite_probability, invocation_ms=milliseconds)
    exported = {
        "status": "PASS_OFFLINE_NUMERICAL_EXPORT", "model_version": MODEL_VERSION,
        "artifact": artifact.name, "artifact_sha256": sha(artifact), "artifact_bytes": len(payload),
        "conversion_seconds": conversion_seconds, "builtin_ops": sorted(ops), "flex_required": False,
        "keras_reload_samples": len(data.y), "keras_reload_max_abs_error": reload_error,
        "preprocessing_fixture_exact": True, "tflite_parity_samples": len(indices),
        "raw_max_abs_error": error, "calibrated_max_abs_error": calibrated_error,
        "class_mismatches": mismatches, "threshold": threshold,
        "host_invocation_median_ms": float(np.median(milliseconds)),
        "host_invocation_max_ms": float(np.max(milliseconds)),
        "pi_benchmark_performed": False, "real_world_validated": False,
        "deployment_ready": False, "synthetic_data": True,
    }
    write_json(package/"EXPORT_RESULT.json", exported)
    write_json(package/"TRAINING_METADATA.json", {
        "run_contract": run_contract,
        "epoch_calibration_threshold_policy": json.loads((run/"final_policy.json").read_text()),
        "environment": json.loads((run/"environment.json").read_text()),
        "synthetic_grouped_cv": result["synthetic_grouped_cv"],
        "outer_fold_metrics": result["outer_metrics"],
        "model_training_fits": 26, "other_architectures_trained": False,
    })
    for name in ("imu_simulation.json", "IMU_GENERATION_SPEC.md"):
        shutil.copyfile(data_dir/name, package/name)
    snapshot = run/"source_snapshot"
    snapshot.mkdir(exist_ok=True)
    for name in ("v5_training.py", "export_v5.py", "imu_generator.py", "requirements-training.txt"):
        shutil.copyfile(ROOT/name, snapshot/name)
    _package_docs(package, result, exported)
    manifest.update(selected_runtime_artifact=artifact.name, flex_required=False,
                    accel_unit="m/s^2 specific force, gravity retained", gyro_unit="rad/s",
                    acquisition_hz=50, phase_reducer="median of pose-associated samples per phase",
                    inference_preprocessing="preprocessing.json; no runtime refitting",
                    calibration="calibration.json on raw sigmoid probability",
                    threshold="threshold.json; class 1 if calibrated probability >= threshold",
                    evaluation={"provenance": "synthetic profiles only; not real-world accuracy",
                                "outer_grouped_cv": result["synthetic_grouped_cv"]},
                    export_status=exported["status"], export_code_sha256=sha(Path(__file__)))
    manifest["artifacts"] = {path.name: sha(path) for path in package.iterdir()
                              if path.is_file() and path.name != manifest_path.name}
    write_json(manifest_path, manifest)
    with (package/"SHA256SUMS.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["path", "size_bytes", "sha256"])
        writer.writeheader()
        for path in sorted(package.iterdir()):
            if path.is_file() and path.name != "SHA256SUMS.csv":
                writer.writerow({"path": path.name, "size_bytes": path.stat().st_size, "sha256": sha(path)})
    write_json(run/"RUN_STATUS.json", {**result, "status": "COMPLETE_OFFLINE_SYNTHETIC_CANDIDATE",
                                       "export": exported, "live_scoring_enabled": False})
    print(json.dumps(exported, indent=2), flush=True)
    return exported


def _package_docs(package: Path, training: dict, exported: dict) -> None:
    score = training["synthetic_grouped_cv"]
    text = f"""# V5 IMU synthetic R1 — offline research candidate

Version: `{MODEL_VERSION}`. Not activated in the Pi or local runtime.

BiLSTM 64/32 + 2-head attention, 105,681 parameters; temporal `(1,3,29)`,
context `(1,2)` ordered Exercise_ID, Load_kg. Exact features are in
MODEL_MANIFEST.json and preprocessing.json. No delta, bar proxies or RF.

Training: 20 inner fits, five outer evaluation fits, one all-data fit. Inner
profiles are disjoint 12 fitting / 3 early-stopping monitor / 5 validation.
Preprocessing is fitted on fitting profiles only. Final weights, preprocessing,
Platt calibration and threshold are new, not reused from the historical model.

## Synthetic evaluation only

Held-out-profile outer OOF: accuracy {score['accuracy']:.6f}, F1 {score['f1']:.6f},
ROC AUC {score['roc_auc']:.6f}, bad-form recall {score['bad_form_recall']:.6f}.
The 25 profile IDs are synthetic, not measured people. Target is the historical
phase-3 Class_Binary; 374 phase-inconsistent repetitions are retained. These
numbers are not estimates of accuracy on real exercises or clinical validity.
Global calibration/threshold fit on outer OOF is a finalization policy, not a
second independent evaluation. Its transfer to the all-data model is unverified.

## Numerical export

FP32 built-in TFLite, no Flex; {exported['artifact_bytes']} bytes.
Keras reload compared on 2,018 repetitions. TFLite compared on 64 fixed,
evenly spaced repetitions: maximum raw probability difference
{exported['raw_max_abs_error']:.9g}, zero class mismatches. Preprocessing fixture
round-trip is exact. This is a host check, not a Pi benchmark.

## Simulation contract and deployment gate

Acceleration: m/s² specific force, gravity retained. Gyroscope: rad/s.
Assumed X-forward/Y-left/Z-up virtual sensor frame, 50 Hz acquisition, phase
medians of pose-associated samples. Physical PCB-to-body mounting and motion/
noise parameters are unmeasured assumptions. Original vision, labels, context
and metadata were preserved; only the IMU generation changed.

Before activation, verify the actual mounted frame/units, synchronized live
phase features, model adapter compatibility and Pi numerical/runtime behavior.
Then evaluate real independently labelled repetitions. Do not interpret a
successful training/export as validated real-world form accuracy.

Use the JSON preprocessing/calibration/threshold alongside the TFLite model.
Do not use historical scalers/thresholds or silently fall back to them.
"""
    (package/"README.md").write_text(text, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", required=True, type=Path)
    parser.add_argument("--data", type=Path, default=ROOT/"data/generated/imu_r1_20261020")
    args = parser.parse_args()
    run = args.run.resolve()
    if not run.is_relative_to((ROOT/"outputs").resolve()):
        parser.error("Use a local training output directory")
    os.environ.setdefault("KERAS_HOME", str(run/"cache/keras"))
    os.environ.setdefault("MPLCONFIGDIR", str(run/"cache/matplotlib"))
    os.environ.setdefault("CUDA_VISIBLE_DEVICES", "-1")
    export_run(run, args.data.resolve())


if __name__ == "__main__":
    main()
