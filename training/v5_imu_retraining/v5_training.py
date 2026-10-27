"""Final V5 architecture only: fresh grouped CV on an explicit synthetic revision.

Historical scripts and fitted states are never imported. TensorFlow is loaded
only for fitting; portable preprocessing and calibration use JSON, not pickle.
"""

from __future__ import annotations

import argparse
import csv
import gc
import hashlib
import importlib.metadata
import json
import math
import os
import platform
import time
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score, average_precision_score, balanced_accuracy_score, brier_score_loss,
    confusion_matrix, f1_score, matthews_corrcoef, precision_score, recall_score, roc_auc_score,
)
from sklearn.model_selection import GroupShuffleSplit, StratifiedGroupKFold
from sklearn.preprocessing import StandardScaler


ROOT = Path(__file__).resolve().parent
MODEL_VERSION = "digital_spotter_v5_imu_synthetic_r1"
REGISTRY = ROOT/"reference/v5_package/saved_models/preprocessing/temporal_feature_registry.csv"
with REGISTRY.open(newline="", encoding="utf-8") as _handle:
    _registry = list(csv.DictReader(_handle))
FEATURES = tuple(row["column"] for row in _registry)
if len(FEATURES) != 29 or [int(row["index"]) for row in _registry] != list(range(29)):
    raise ValueError("Final V5 temporal registry mismatch")
CONTEXT = ("Exercise_ID", "Load_kg")
IMU_FEATURES = tuple(name for name in FEATURES if name.startswith("IMU_"))
if len(IMU_FEATURES) != 7:
    raise ValueError("Expected six IMU axes and acceleration magnitude")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _hash_object(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False).encode()).hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False)+"\n", encoding="utf-8")
    temporary.replace(path)


def _number(row: dict[str, str], name: str) -> float:
    value = row[name]
    result = float(value) if value and value.lower() != "nan" else float("nan")
    if math.isinf(result): raise ValueError("Infinite feature: " + name)
    return result


def phase_features(row: dict[str, str]) -> np.ndarray:
    """Same six engineered formulas and exact Stage 8 order; allow training missingness."""
    values = {name: _number(row, name) for name in FEATURES if name in row}
    for joint, feature in (
        ("Hip_Flexion", "Hip_Flexion_Asymmetry"),
        ("Knee_Flexion", "Knee_Flexion_Asymmetry"),
        ("Ankle_Dorsiflexion", "Ankle_Dorsiflexion_Asymmetry"),
    ):
        values[feature] = abs(_number(row, "Angle_"+joint+"_L") - _number(row, "Angle_"+joint+"_R"))
    for side in ("L", "R"):
        values["Knee_Hip_Coupling_"+side] = _number(row, "Angle_Knee_Flexion_"+side) / (_number(row, "Angle_Hip_Flexion_"+side)+1e-6)
    values["IMU_Acc_Magnitude"] = math.sqrt(sum(_number(row, "IMU_Acc_"+axis)**2 for axis in "XYZ"))
    return np.array([values[name] for name in FEATURES], dtype=np.float64)


@dataclass
class Dataset:
    temporal: np.ndarray
    context: np.ndarray
    y: np.ndarray
    groups: np.ndarray
    identities: list[dict[str, Any]]
    master_sha256: str
    manifest_sha256: str
    label_disagreements: int


def load_dataset(directory: Path) -> Dataset:
    manifest_path = directory/"DATASET_MANIFEST.json"
    manifest = json.loads(manifest_path.read_text())
    if (manifest["provenance"] != "synthetic_unvalidated_motion_model"
            or manifest["real_world_calibrated"] is not False
            or manifest["protected_cells_changed"] != 0):
        raise ValueError("Expected a preserved, explicitly synthetic candidate")
    for name, record in manifest["outputs"].items():
        path = (directory/name).resolve()
        if not path.is_relative_to(directory.resolve()) or sha(path) != record["sha256"]:
            raise ValueError("Generated artifact mismatch: " + name)
    path = directory/"master_dataset.csv"
    with path.open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    grouped = defaultdict(list)
    for row in rows:
        grouped[(row["Session_ID"], int(row["Rep_ID"]), row["Subject_ID"])].append(row)
    temporal, context, labels, groups, identities = [], [], [], [], []
    disagreements = 0
    for (session, rep, subject), records in sorted(grouped.items()):
        records.sort(key=lambda row: int(row["Rep_Phase"]))
        if [int(row["Rep_Phase"]) for row in records] != [1, 2, 3]:
            raise ValueError("Malformed three-phase repetition")
        if len({(row["Exercise_ID"], row["Load_kg"]) for row in records}) != 1:
            raise ValueError("Context changes inside a repetition")
        phase_labels = [int(row["Class_Binary"]) for row in records]
        if not set(phase_labels).issubset({0, 1}): raise ValueError("Invalid target")
        disagreements += int(len(set(phase_labels)) > 1)
        temporal.append(np.stack([phase_features(row) for row in records]))
        context.append([_number(records[0], name) for name in CONTEXT])
        labels.append(phase_labels[2])
        groups.append(subject)
        identities.append({"Subject_ID": subject, "Session_ID": session, "Rep_ID": rep,
                           "Exercise_ID": int(records[0]["Exercise_ID"]), "y_true": phase_labels[2]})
    return Dataset(np.asarray(temporal), np.asarray(context), np.asarray(labels),
                   np.asarray(groups), identities, sha(path), sha(manifest_path), disagreements)


class Preprocessor:
    """Fresh 3-IQR winsorization, phase medians and scalers, fitted on training only."""

    def fit(self, temporal: np.ndarray, context: np.ndarray) -> "Preprocessor":
        x, c = self._validate(temporal, context)
        if np.isnan(x).all(axis=0).any() or np.isnan(c).all(axis=0).any():
            raise ValueError("A training feature/phase is wholly missing; no zero fallback")
        phase = np.nanmedian(x, axis=0)
        context_medians = np.nanmedian(c, axis=0)
        bounds = {}
        for name in IMU_FEATURES:
            q1, q3 = np.nanpercentile(x[:, :, FEATURES.index(name)], [25, 75])
            bounds[name] = [float(q1-3*(q3-q1)), float(q3+3*(q3-q1))]
        self.state = {
            "schema_version": 1, "model_version": MODEL_VERSION,
            "phase_order": [1, 2, 3], "temporal_feature_order": list(FEATURES),
            "context_feature_order": list(CONTEXT), "temporal_input_shape": [3, 29],
            "context_input_shape": [2], "fit_repetitions": len(x),
            "phase_medians": {name: phase[:, i].tolist() for i, name in enumerate(FEATURES)},
            "context_medians": dict(zip(CONTEXT, map(float, context_medians))),
            "winsor_bounds": bounds,
        }
        x, c = self._impute_clip(x, c)
        for name, values in (("temporal_scaler", x.reshape(-1, 29)), ("context_scaler", c)):
            scaler = StandardScaler().fit(values)
            self.state[name] = {"mean": scaler.mean_.tolist(), "scale": scaler.scale_.tolist(),
                                "var": scaler.var_.tolist(), "n_samples_seen": int(scaler.n_samples_seen_)}
        return self

    @classmethod
    def from_state(cls, state: dict[str, Any]) -> "Preprocessor":
        if (state["temporal_feature_order"] != list(FEATURES)
                or state["context_feature_order"] != list(CONTEXT)
                or state["phase_order"] != [1, 2, 3] or state["model_version"] != MODEL_VERSION):
            raise ValueError("Preprocessor contract mismatch")
        obj = cls()
        obj.state = state
        return obj

    @staticmethod
    def _validate(temporal: np.ndarray, context: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        x, c = np.array(temporal, dtype=np.float64, copy=True), np.array(context, dtype=np.float64, copy=True)
        if (x.ndim != 3 or x.shape[1:] != (3, 29) or c.shape != (len(x), 2)
                or not len(x) or np.isinf(x).any() or np.isinf(c).any()):
            raise ValueError("Expected finite-or-missing (N,3,29) and (N,2) inputs")
        return x, c

    def _impute_clip(self, x: np.ndarray, c: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        for i, name in enumerate(FEATURES):
            x[:, :, i] = np.where(np.isnan(x[:, :, i]), self.state["phase_medians"][name], x[:, :, i])
            if name in self.state["winsor_bounds"]:
                x[:, :, i] = np.clip(x[:, :, i], *self.state["winsor_bounds"][name])
        for i, name in enumerate(CONTEXT):
            c[:, i] = np.where(np.isnan(c[:, i]), self.state["context_medians"][name], c[:, i])
        return x, c

    def transform(self, temporal: np.ndarray, context: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        x, c = self._impute_clip(*self._validate(temporal, context))
        for name, values in (("temporal_scaler", x), ("context_scaler", c)):
            state = self.state[name]
            values -= np.asarray(state["mean"])
            values /= np.asarray(state["scale"])
        if not np.isfinite(x).all() or not np.isfinite(c).all():
            raise ValueError("Non-finite transformed input")
        return x.astype(np.float32), c.astype(np.float32)


def grouped_folds(y: np.ndarray, groups: np.ndarray) -> list[tuple[np.ndarray, np.ndarray, list]]:
    dummy = np.zeros((len(y), 1))
    result = []
    for outer, (development, test) in enumerate(StratifiedGroupKFold(5, shuffle=True, random_state=42).split(dummy, y, groups)):
        if set(groups[development]) & set(groups[test]): raise ValueError("Outer group leakage")
        inner = []
        for train_rel, valid_rel in StratifiedGroupKFold(4, shuffle=True, random_state=1000+outer).split(dummy[development], y[development], groups[development]):
            train, valid = development[train_rel], development[valid_rel]
            if set(groups[train]) & set(groups[valid]): raise ValueError("Inner group leakage")
            for indices in (train, valid, test):
                if len(np.unique(y[indices])) != 2: raise ValueError("A fold lacks a target class")
            inner.append((train, valid))
        result.append((development, test, inner))
    return result


def monitor_split(
    train: np.ndarray, y: np.ndarray, groups: np.ndarray, exercises: np.ndarray,
    outer: int, inner: int,
) -> tuple[np.ndarray, np.ndarray, int]:
    """Stage 8: 12 fit / 3 stopping profiles, leaving inner validation untouched."""
    if len(set(groups[train])) != 15:
        raise ValueError("Expected 15 inner-training synthetic profiles")
    for attempt in range(100):
        seed = 42 + 10*outer + inner + attempt
        splitter = GroupShuffleSplit(n_splits=1, test_size=3, random_state=seed)
        fit_rel, monitor_rel = next(splitter.split(train, y[train], groups[train]))
        fit, monitor = train[fit_rel], train[monitor_rel]
        if (len(set(groups[fit])) == 12 and len(set(groups[monitor])) == 3
                and len(set(y[fit])) == len(set(y[monitor])) == 2
                and len(set(exercises[fit])) == len(set(exercises[monitor])) == 2):
            return fit, monitor, seed
    raise ValueError("No balanced internal stopping monitor")


def _platt(y: np.ndarray, raw: np.ndarray) -> dict[str, Any]:
    model = LogisticRegression(solver="lbfgs", random_state=42).fit(raw.reshape(-1, 1), y)
    return {"kind": "platt", "input": "raw_probability", "coef": float(model.coef_[0, 0]),
            "intercept": float(model.intercept_[0]), "positive_class": 1}


def apply_calibration(raw: np.ndarray, policy: dict[str, Any]) -> np.ndarray:
    raw = np.asarray(raw, dtype=float)
    if policy["kind"] == "identity": return raw.copy()
    if policy["kind"] != "platt" or policy["input"] != "raw_probability":
        raise ValueError("Unknown calibration policy")
    z = np.clip(raw*policy["coef"] + policy["intercept"], -700, 700)
    return 1/(1+np.exp(-z))


def cross_calibrate(y: np.ndarray, raw: np.ndarray, folds: np.ndarray, groups: np.ndarray) -> dict[str, Any]:
    calibrated = np.full(len(y), np.nan)
    if sorted(set(folds)) != [0, 1, 2, 3]: raise ValueError("Four calibration folds required")
    for fold in range(4):
        train, validation = folds != fold, folds == fold
        if set(groups[train]) & set(groups[validation]): raise ValueError("Calibration group leakage")
        calibrated[validation] = apply_calibration(raw[validation], _platt(y[train], raw[train]))
    if not np.isfinite(calibrated).all(): raise ValueError("Incomplete cross-calibration")
    raw_brier, platt_brier = brier_score_loss(y, raw), brier_score_loss(y, calibrated)
    use_platt = raw_brier-platt_brier >= .001
    return {"decision_probability": calibrated if use_platt else raw.copy(), "subject_overlap": 0,
            "raw_brier": float(raw_brier), "cross_platt_brier": float(platt_brier),
            "selected_policy": "PLATT" if use_platt else "UNCALIBRATED",
            "deployment_policy": _platt(y, raw) if use_platt else {"kind": "identity"}}


def choose_threshold(y: np.ndarray, probability: np.ndarray) -> float:
    """Exact historical candidate/tie rule, vectorized rather than thousands of metric calls."""
    order = np.argsort(probability)
    p, labels = probability[order], y[order]
    thresholds = np.unique(np.concatenate(([0.], p, [1.])))
    indices = np.searchsorted(p, thresholds, side="left")
    prefix = np.concatenate(([0], np.cumsum(labels)))
    tp = labels.sum()-prefix[indices]
    predicted = len(y)-indices
    denominator = predicted+labels.sum()
    scores = np.divide(2*tp, denominator, out=np.zeros_like(denominator, dtype=float), where=denominator != 0)
    return float(thresholds[np.lexsort((thresholds, np.abs(thresholds-.5), -scores))[0]])


def metrics(y: np.ndarray, probability: np.ndarray, prediction: np.ndarray) -> dict[str, Any]:
    return {
        "sample_count": len(y), "accuracy": float(accuracy_score(y, prediction)),
        "balanced_accuracy": float(balanced_accuracy_score(y, prediction)),
        "precision": float(precision_score(y, prediction, zero_division=0)),
        "bad_form_recall": float(recall_score(y, prediction, zero_division=0)),
        "f1": float(f1_score(y, prediction, zero_division=0)),
        "mcc": float(matthews_corrcoef(y, prediction)), "roc_auc": float(roc_auc_score(y, probability)),
        "pr_auc": float(average_precision_score(y, probability)), "brier": float(brier_score_loss(y, probability)),
        "confusion_matrix": confusion_matrix(y, prediction, labels=[0, 1]).tolist(),
    }


def configure_tensorflow():
    os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")
    import tensorflow as tf
    tf.config.threading.set_intra_op_parallelism_threads(2)
    tf.config.threading.set_inter_op_parallelism_threads(1)
    tf.keras.utils.set_random_seed(42)
    tf.config.experimental.enable_op_determinism()
    return tf


def build_model(tf):
    """Exact final Stage 8 105,681-parameter architecture; no candidate branches."""
    keras, layers = tf.keras, tf.keras.layers
    temporal = keras.Input((3, 29), name="temporal_input")
    x = layers.Bidirectional(layers.LSTM(64, return_sequences=True), name="temporal_bilstm_64")(temporal)
    x = layers.BatchNormalization(name="temporal_batch_norm")(x)
    x = layers.Dropout(.25, name="temporal_dropout_1")(x)
    x = layers.Bidirectional(layers.LSTM(32, return_sequences=True), name="temporal_bilstm_32")(x)
    x = layers.Dropout(.20, name="temporal_dropout_2")(x)
    attended = layers.MultiHeadAttention(num_heads=2, key_dim=16, name="temporal_attention")(x, x)
    x = layers.Add(name="attention_residual")([x, attended])
    x = layers.LayerNormalization(name="attention_layer_norm")(x)
    pooled = layers.GlobalAveragePooling1D(name="temporal_pooling")(x)
    context = keras.Input((2,), name="context_input")
    branch = layers.Dense(16, activation="relu", name="context_dense_16")(context)
    fused = layers.Concatenate(name="fusion_concat")([pooled, branch])
    fused = layers.Dense(64, activation="relu", name="fusion_dense_64")(fused)
    fused = layers.Dropout(.25, name="fusion_dropout_1")(fused)
    fused = layers.Dense(32, activation="relu", name="fusion_dense_32")(fused)
    fused = layers.Dropout(.15, name="fusion_dropout_2")(fused)
    output = layers.Dense(1, activation="sigmoid", name="form_probability")(fused)
    model = keras.Model([temporal, context], output, name="V5_IMU_R1_SCOPE_FAITHFUL")
    model.compile(optimizer=keras.optimizers.Adam(learning_rate=3e-4), loss=keras.losses.BinaryCrossentropy(),
                  metrics=[keras.metrics.BinaryAccuracy(name="accuracy"), keras.metrics.AUC(name="auc")])
    if model.count_params() != 105681 or [tuple(x.shape[1:]) for x in model.inputs] != [(3, 29), (2,)]:
        raise ValueError("Final V5 architecture mismatch")
    return model


def _dataset(tf, x: tuple[np.ndarray, np.ndarray], y: np.ndarray):
    dataset = tf.data.Dataset.from_tensor_slices(((x[0], x[1]), y.astype(np.float32))).batch(32)
    options = tf.data.Options()
    options.threading.private_threadpool_size = 1
    options.threading.max_intra_op_parallelism = 1
    return dataset.with_options(options).prefetch(1)


def _predict(model, x: tuple[np.ndarray, np.ndarray]) -> np.ndarray:
    result = np.concatenate([model([x[0][start:start+256], x[1][start:start+256]], training=False).numpy().reshape(-1)
                             for start in range(0, len(x[0]), 256)])
    if not np.isfinite(result).all(): raise ValueError("Non-finite model probability")
    return result.astype(float)


def _fit(
    tf, data: Dataset, train: np.ndarray, validation: np.ndarray, directory: Path,
    config: dict[str, Any], run_hash: str, progress: Path, *, fixed_epochs: int | None = None,
    monitor: np.ndarray | None = None,
) -> dict[str, Any]:
    if fixed_epochs is None and (monitor is None or set(data.groups[monitor]) &
                                (set(data.groups[train]) | set(data.groups[validation]))):
        raise ValueError("Early stopping requires an independent grouped monitor")
    signature = _hash_object({"run_hash": run_hash, "train": train.tolist(), "validation": validation.tolist(),
                              "monitor": monitor.tolist() if monitor is not None else None,
                              "fixed_epochs": fixed_epochs})
    completed = directory/"COMPLETE.json"
    if completed.exists():
        record = json.loads(completed.read_text())
        if record["fit_signature"] != signature: raise ValueError("Checkpoint configuration mismatch")
        if any(sha(directory/name) != digest for name, digest in record["artifacts"].items()):
            raise ValueError("Checkpoint artifact hash mismatch")
        print("RESUME", directory.name, "complete", flush=True)
        return record
    if directory.exists():
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        preserved = directory.with_name(directory.name+".interrupted-"+stamp)
        directory.rename(preserved)
        print("PRESERVED interrupted fit:", preserved.name, flush=True)
    directory.mkdir(parents=True)
    processor = Preprocessor().fit(data.temporal[train], data.context[train])
    write_json(directory/"preprocessing.json", processor.state)
    train_x = processor.transform(data.temporal[train], data.context[train])
    validation_x = processor.transform(data.temporal[validation], data.context[validation])
    monitor_x = processor.transform(data.temporal[monitor], data.context[monitor]) if monitor is not None else None
    tf.keras.backend.clear_session()
    tf.keras.utils.set_random_seed(config["seed"])
    model = build_model(tf)
    epochs = config["max_epochs"] if fixed_epochs is None else fixed_epochs
    stopping = tf.keras.callbacks.EarlyStopping(
        monitor="val_loss", patience=config["early_stopping_patience"],
        min_delta=config["early_stopping_min_delta"], restore_best_weights=True,
    )

    class Progress(tf.keras.callbacks.Callback):
        def on_epoch_end(self, epoch, logs=None):
            write_json(progress, {"status": "TRAINING", "fit": directory.name, "epoch": epoch+1,
                                 "max_epochs": epochs, "logs": {k: float(v) for k, v in (logs or {}).items()},
                                 "model_version": MODEL_VERSION, "real_world_validated": False})
            if (epoch+1) % 10 == 0:
                print(f"  {directory.name}: epoch {epoch+1}/{epochs}", flush=True)

    callbacks = [tf.keras.callbacks.CSVLogger(str(directory/"history.csv")), Progress()]
    if fixed_epochs is None:
        callbacks.extend([stopping, tf.keras.callbacks.ModelCheckpoint(
            str(directory/"best.weights.h5"), monitor="val_loss", mode="min",
            save_best_only=True, save_weights_only=True, verbose=0,
        )])
    started = time.monotonic()
    history = model.fit(_dataset(tf, train_x, data.y[train]),
                        validation_data=_dataset(tf, monitor_x, data.y[monitor]) if fixed_epochs is None else None,
                        epochs=epochs, shuffle=False, callbacks=callbacks, verbose=0)
    if fixed_epochs is None:
        model.load_weights(directory/"best.weights.h5")
    probability = _predict(model, validation_x)
    model.save(directory/"model.keras")
    np.savez_compressed(directory/"predictions.npz", indices=validation, y_true=data.y[validation], raw_probability=probability)
    best_epoch = (int(np.argmin(history.history["val_loss"]))+1) if fixed_epochs is None else epochs
    record = {
        "fit_signature": signature, "model_version": MODEL_VERSION, "parameters": model.count_params(),
        "train_repetitions": len(train), "validation_repetitions": len(validation),
        "train_groups": sorted(set(data.groups[train])), "validation_groups": sorted(set(data.groups[validation])),
        "monitor_groups": sorted(set(data.groups[monitor])) if monitor is not None else [],
        "early_stopping_source": "independent internal monitor" if monitor is not None else "fixed epochs; no stopping labels",
        "epochs_observed": len(history.history["loss"]), "best_epoch": best_epoch,
        "fixed_epoch_fit": fixed_epochs is not None, "wall_seconds": time.monotonic()-started,
        "artifacts": {name: sha(directory/name) for name in ("model.keras", "preprocessing.json", "predictions.npz", "history.csv")},
    }
    write_json(completed, record)
    print(f"PASS {directory.name}: epochs={record['epochs_observed']} chosen={best_epoch} seconds={record['wall_seconds']:.1f}", flush=True)
    del model
    tf.keras.backend.clear_session()
    gc.collect()
    return record


def run_cv(data_dir: Path, output: Path, config: dict[str, Any], *, resume: bool = False) -> dict[str, Any]:
    data = load_dataset(data_dir)
    if len(data.y) != 2018 or len(set(data.groups)) != 25:
        raise ValueError("Expected preserved 2,018-repetition / 25 synthetic-profile baseline")
    if (config["outer_grouped_folds"] != 5 or config["inner_grouped_folds"] != 4
            or config["owner_selected_evaluation"] != "original_subject_grouped_cross_validation"
            or config["expected_parameter_count"] != 105681 or config["batch_size"] != 32
            or config["learning_rate"] != 3e-4 or config["loss"] != "BinaryCrossentropy"
            or config["shuffle"] is not False):
        raise ValueError("Unsupported final-V5 training plan")
    contract = {"data_sha256": data.master_sha256, "manifest_sha256": data.manifest_sha256,
                "config": config, "code_sha256": sha(Path(__file__)), "registry_sha256": sha(REGISTRY),
                "model_version": MODEL_VERSION, "temporal_features": list(FEATURES), "context": list(CONTEXT),
                "target": "unchanged historical phase-3 Class_Binary", "synthetic_data": True}
    run_hash = _hash_object(contract)
    if output.exists():
        if not resume or not (output/"RUN_CONTRACT.json").exists():
            raise FileExistsError("Output exists; use explicit --resume only for this exact run")
        previous = json.loads((output/"RUN_CONTRACT.json").read_text())
        if previous["run_hash"] != run_hash: raise ValueError("Resume contract differs")
    else:
        output.mkdir(parents=True)
        write_json(output/"RUN_CONTRACT.json", {"run_hash": run_hash, "contract": contract})
    import fcntl
    lock = (output/".training.lock").open("a")
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    status_path = output/"RUN_STATUS.json"
    write_json(output/"environment.json", {"python": platform.python_version(), "platform": platform.platform(),
               "versions": {name: importlib.metadata.version(name) for name in ("tensorflow", "keras", "numpy", "scikit-learn")}})
    try:
        folds = grouped_folds(data.y, data.groups)
        exercises = np.asarray([row["Exercise_ID"] for row in data.identities])
        rows = []
        for outer, (development, test, inner) in enumerate(folds):
            for role, indices in (("development", development), ("outer_test", test)):
                rows.extend({"outer_fold": outer, "role": role, "index": int(i), **data.identities[i]} for i in indices)
            for number, (train, valid) in enumerate(inner):
                for role, indices in (("inner_train", train), ("inner_validation", valid)):
                    rows.extend({"outer_fold": outer, "inner_fold": number, "role": role,
                                 "index": int(i), **data.identities[i]} for i in indices)
                fit, monitor, _ = monitor_split(train, data.y, data.groups, exercises, outer, number)
                for role, indices in (("inner_fit", fit), ("inner_monitor", monitor)):
                    rows.extend({"outer_fold": outer, "inner_fold": number, "role": role,
                                 "index": int(i), **data.identities[i]} for i in indices)
        with (output/"fold_manifest.csv").open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=["outer_fold", "inner_fold", "role", "index", *data.identities[0]])
            writer.writeheader(); writer.writerows(rows)
        write_json(status_path, {"status": "STARTING", "planned_lstm_fits": 26, "model_version": MODEL_VERSION})
        tf = configure_tensorflow()
        all_best_epochs, outer_metrics, outer_predictions = [], [], []
        raw_oof = np.full(len(data.y), np.nan)
        for outer, (development, test, inner) in enumerate(folds):
            print(f"OUTER {outer+1}/5 — final V5 architecture only", flush=True)
            raw_development = np.full(len(data.y), np.nan)
            calibration_fold = np.full(len(data.y), -1, dtype=int)
            best_epochs = []
            for number, (train, valid) in enumerate(inner):
                directory = output/"fits"/f"outer_{outer}_inner_{number}"
                fit, monitor, _ = monitor_split(train, data.y, data.groups, exercises, outer, number)
                record = _fit(tf, data, fit, valid, directory, config, run_hash, status_path, monitor=monitor)
                with np.load(directory/"predictions.npz") as saved:
                    raw_development[saved["indices"]] = saved["raw_probability"]
                    calibration_fold[saved["indices"]] = number
                best_epochs.append(record["best_epoch"])
            all_best_epochs.extend(best_epochs)
            if not np.isfinite(raw_development[development]).all(): raise ValueError("Incomplete inner OOF")
            calibration = cross_calibrate(data.y[development], raw_development[development],
                                          calibration_fold[development], data.groups[development])
            threshold = choose_threshold(data.y[development], calibration["decision_probability"])
            policy = {k: v for k, v in calibration.items() if k != "decision_probability"}
            epochs = max(1, int(math.floor(float(np.median(best_epochs))+.5)))
            policy.update(threshold=threshold, outer_epochs=epochs, best_inner_epochs=best_epochs)
            write_json(output/"policies"/f"outer_{outer}.json", policy)
            directory = output/"fits"/f"outer_{outer}_evaluation"
            _fit(tf, data, development, test, directory, config, run_hash, status_path, fixed_epochs=epochs)
            with np.load(directory/"predictions.npz") as saved:
                raw = saved["raw_probability"]
            raw_oof[test] = raw
            calibrated = apply_calibration(raw, policy["deployment_policy"])
            prediction = (calibrated >= threshold).astype(int)
            score = metrics(data.y[test], calibrated, prediction)
            score.update(outer_fold=outer, threshold=threshold, calibration=policy["selected_policy"])
            outer_metrics.append(score)
            outer_predictions.extend({"index": int(i), "outer_fold": outer, **data.identities[i],
                                      "raw_probability": float(r), "calibrated_probability": float(p),
                                      "threshold": threshold, "prediction": int(label)}
                                     for i, r, p, label in zip(test, raw, calibrated, prediction))
            write_json(output/"outer_metrics.json", outer_metrics)
            print(f"OUTER {outer+1}/5 complete: synthetic-only F1={score['f1']:.4f}", flush=True)
        if not np.isfinite(raw_oof).all(): raise ValueError("Incomplete outer OOF")
        outer_predictions.sort(key=lambda row: row["index"])
        with (output/"outer_oof_predictions.csv").open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(outer_predictions[0]))
            writer.writeheader(); writer.writerows(outer_predictions)
        pooled = metrics(data.y, np.array([row["calibrated_probability"] for row in outer_predictions]),
                         np.array([row["prediction"] for row in outer_predictions]))
        global_policy = _platt(data.y, raw_oof)
        global_probability = apply_calibration(raw_oof, global_policy)
        final_threshold = choose_threshold(data.y, global_probability)
        final_epochs = max(1, int(math.floor(float(np.median(all_best_epochs))+.5)))
        write_json(output/"final_policy.json", {"calibration": global_policy, "threshold": final_threshold,
                   "epochs": final_epochs, "inner_best_epochs": all_best_epochs,
                   "warning": "Global calibrator/threshold fit on OOF labels; fit statistics are not independent evaluation. Transfer to final all-data model is unverified."})
        all_indices = np.arange(len(data.y))
        _fit(tf, data, all_indices, all_indices, output/"fits/final", config, run_hash, status_path, fixed_epochs=final_epochs)
        final_dir = output/"fits/final"
        package = output/"package"
        package.mkdir(exist_ok=True)
        for name in ("model.keras", "preprocessing.json"):
            import shutil
            shutil.copyfile(final_dir/name, package/name)
        write_json(package/"calibration.json", global_policy)
        write_json(package/"threshold.json", {"threshold": final_threshold, "positive_class": 1})
        processor = Preprocessor.from_state(json.loads((package/"preprocessing.json").read_text()))
        fixture_indices = np.arange(min(64, len(data.y)))
        x, c = processor.transform(data.temporal[fixture_indices], data.context[fixture_indices])
        np.savez_compressed(package/"inference_fixture.npz", temporal=x, context=c,
                            raw_temporal=data.temporal[fixture_indices], raw_context=data.context[fixture_indices])
        write_json(package/"MODEL_MANIFEST.json", {
            "model_version": MODEL_VERSION, "run_hash": run_hash, "temporal_shape": [1, 3, 29],
            "context_shape": [1, 2], "temporal_features": list(FEATURES), "context_features": list(CONTEXT),
            "parameters": 105681, "synthetic_data": True, "live_scoring_enabled": False,
            "real_world_validated": False, "deployment_ready": False,
            "target": "historical phase-3 Class_Binary", "inherited_label_disagreements": data.label_disagreements,
            "sensor_frame": "assumed X-forward/Y-left/Z-up; physical mapping unverified",
            "source_dataset_sha256": data.master_sha256,
            "artifacts": {path.name: sha(path) for path in package.iterdir() if path.is_file()},
        })
        result = {"status": "TRAINING_COMPLETE_EXPORT_PENDING", "model_version": MODEL_VERSION,
                  "completed_lstm_fits": 26, "main_architecture_only": True,
                  "synthetic_grouped_cv": pooled, "outer_metrics": outer_metrics,
                  "final_epochs": final_epochs, "threshold": final_threshold,
                  "real_world_validated": False, "deployment_ready": False,
                  "dataset_sha256": data.master_sha256, "label_disagreements": data.label_disagreements}
        write_json(output/"TRAINING_RESULT.json", result)
        write_json(status_path, result)
        print("TRAINING COMPLETE — 26 fits of one architecture; synthetic evaluation only", flush=True)
        return result
    except BaseException as error:
        write_json(status_path, {"status": "FAILED_OR_INTERRUPTED", "error_type": type(error).__name__,
                                 "error": str(error), "model_version": MODEL_VERSION, "deployment_ready": False})
        raise
    finally:
        lock.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=ROOT/"data/generated/imu_r1_20261020")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--plan", type=Path, default=ROOT/"config/training_plan.json")
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    output = args.output.resolve()
    if not output.is_relative_to((ROOT/"outputs").resolve()): parser.error("Output must be under this training workspace's outputs/")
    if not args.data.resolve().is_relative_to((ROOT/"data/generated").resolve()): parser.error("Use a local generated data candidate")
    os.environ.setdefault("KERAS_HOME", str(output/"cache/keras"))
    os.environ.setdefault("MPLCONFIGDIR", str(output/"cache/matplotlib"))
    run_cv(args.data.resolve(), output, json.loads(args.plan.read_text()), resume=args.resume)


if __name__ == "__main__":
    main()
