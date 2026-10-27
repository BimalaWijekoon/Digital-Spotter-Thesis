"""Portable, read-only Stage 8 V5 preprocessing for three phase aggregates."""

from __future__ import annotations

import csv
import hashlib
import json
from collections.abc import Mapping, Sequence
from pathlib import Path

import numpy as np


def verify_runtime_manifest(package: Path) -> dict:
    """Guard local derived state and the source-copy inventory against drift."""
    manifest = json.loads((package / "RUNTIME_MANIFEST.json").read_text(encoding="utf-8"))
    for filename, field in (
        ("COPY_MANIFEST.csv", "copy_manifest_sha256"),
        ("portable_state.json", "portable_state_sha256"),
    ):
        digest = hashlib.sha256((package / filename).read_bytes()).hexdigest()
        if digest != manifest[field]:
            raise ValueError(f"V5 local artifact hash mismatch: {filename}")
    if (manifest["schema_version"] != 1 or
            manifest["model_version"] != "digital_spotter_v5_scope_faithful" or
            manifest["live_scoring_enabled"] is not False):
        raise ValueError("V5 runtime manifest is invalid")
    return manifest


def verify_copied_file(package: Path, relative_path: str) -> str:
    """Verify a copied artifact against its frozen source hash, without source access."""
    with (package / "COPY_MANIFEST.csv").open(newline="", encoding="utf-8") as handle:
        rows = {row["destination_path"]: row for row in csv.DictReader(handle)}
    if relative_path not in rows or rows[relative_path]["match"] != "true":
        raise ValueError(f"V5 artifact is not in verified copy manifest: {relative_path}")
    path = package / relative_path
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != rows[relative_path]["source_sha256"]:
        raise ValueError(f"V5 artifact hash mismatch: {relative_path}")
    if path.stat().st_size != int(rows[relative_path]["size_bytes"]):
        raise ValueError(f"V5 artifact size mismatch: {relative_path}")
    return digest


class V5Preprocessor:
    """Implement the frozen source transform; never fit or load joblib at runtime."""

    def __init__(self, package: Path):
        self.package = Path(package)
        runtime_manifest = verify_runtime_manifest(self.package)
        metadata_rel = "saved_models/preprocessing/final_preprocessing.json"
        temporal_rel = "saved_models/preprocessing/temporal_feature_registry.csv"
        context_rel = "saved_models/preprocessing/context_feature_registry.csv"
        verify_copied_file(self.package, metadata_rel)
        verify_copied_file(self.package, temporal_rel)
        verify_copied_file(self.package, context_rel)
        metadata = json.loads((self.package / metadata_rel).read_text(encoding="utf-8"))
        state = json.loads((self.package / "portable_state.json").read_text(encoding="utf-8"))
        self.temporal_features = tuple(metadata["temporal_feature_order"])
        self.context_features = tuple(metadata["context_feature_order"])
        if (
            metadata["phase_order"] != [1, 2, 3]
            or metadata["temporal_input_shape"] != [3, 29]
            or metadata["context_input_shape"] != [2]
            or len(self.temporal_features) != 29
            or self.context_features != ("Exercise_ID", "Load_kg")
            or state["schema_version"] != 1
            or state["model_version"] != "digital_spotter_v5_scope_faithful"
            or state["phase_order"] != [1, 2, 3]
            or tuple(state["temporal_feature_order"]) != self.temporal_features
            or tuple(state["context_feature_order"]) != self.context_features
            or state["source_state_hash"] != metadata["state_hash"]
            or state["source_sha256"][metadata_rel] != verify_copied_file(self.package, metadata_rel)
            or runtime_manifest["context_feature_order"] != list(self.context_features)
            or runtime_manifest["temporal_input_shape"] != [1, 3, 29]
            or runtime_manifest["context_input_shape"] != [1, 2]
        ):
            raise ValueError("V5 preprocessing metadata/state mismatch")
        for registry, relative, features in (
            ("temporal", temporal_rel, self.temporal_features),
            ("context", context_rel, self.context_features),
        ):
            with (self.package / relative).open(newline="", encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))
            if tuple(row["column"] for row in rows) != features or tuple(int(row["index"]) for row in rows) != tuple(range(len(features))):
                raise ValueError(f"V5 {registry} registry order mismatch")
        self._phase_medians = metadata["phase_medians"]
        self._context_medians = metadata["context_medians"]
        self._winsor_bounds = metadata["winsor_bounds"]
        self._temporal_mean, self._temporal_scale = self._scaler(state["temporal_scaler"], 29)
        self._context_mean, self._context_scale = self._scaler(state["context_scaler"], 2)

    @classmethod
    def from_frozen_state(cls, state: dict, *, expected_features: tuple[str, ...]) -> "V5Preprocessor":
        """Use already verified candidate state without training imports or refitting."""
        if (state["schema_version"] != 1 or state["phase_order"] != [1, 2, 3]
                or state["temporal_input_shape"] != [3, 29]
                or state["context_input_shape"] != [2]
                or tuple(state["temporal_feature_order"]) != expected_features
                or len(expected_features) != 29
                or state["context_feature_order"] != ["Exercise_ID", "Load_kg"]):
            raise ValueError("V5 candidate preprocessing contract mismatch")
        obj = cls.__new__(cls)
        obj.temporal_features = expected_features
        obj.context_features = ("Exercise_ID", "Load_kg")
        obj._phase_medians = state["phase_medians"]
        obj._context_medians = state["context_medians"]
        obj._winsor_bounds = state["winsor_bounds"]
        if (set(obj._phase_medians) != set(expected_features)
                or set(obj._context_medians) != set(obj.context_features)
                or set(obj._winsor_bounds) != {name for name in expected_features if name.startswith("IMU_")}):
            raise ValueError("V5 candidate preprocessing fields mismatch")
        medians = np.asarray([obj._phase_medians[name] for name in expected_features], dtype=float)
        context = np.asarray([obj._context_medians[name] for name in obj.context_features], dtype=float)
        bounds = np.asarray(list(obj._winsor_bounds.values()), dtype=float)
        if (medians.shape != (29, 3) or context.shape != (2,) or bounds.shape != (7, 2)
                or not all(np.isfinite(values).all() for values in (medians, context, bounds))
                or (bounds[:, 0] > bounds[:, 1]).any()):
            raise ValueError("V5 candidate medians/bounds are invalid")
        obj._temporal_mean, obj._temporal_scale = cls._scaler(state["temporal_scaler"], 29)
        obj._context_mean, obj._context_scale = cls._scaler(state["context_scaler"], 2)
        return obj

    def reference_inputs(self) -> tuple[tuple[dict, ...], dict]:
        """Frozen fitted medians for an explicit non-live numerical reference."""
        phases = tuple({"phase": phase, **{
            name: self._phase_medians[name][phase-1] for name in self.temporal_features
        }} for phase in (1, 2, 3))
        return phases, dict(self._context_medians)

    @staticmethod
    def _scaler(state: dict, count: int) -> tuple[np.ndarray, np.ndarray]:
        mean = np.asarray(state["mean"], dtype=np.float64)
        scale = np.asarray(state["scale"], dtype=np.float64)
        if mean.shape != (count,) or scale.shape != (count,) or not np.isfinite(mean).all() or not np.isfinite(scale).all() or (scale <= 0).any():
            raise ValueError("V5 scaler state is invalid")
        return mean, scale

    @staticmethod
    def _value(value: object) -> float:
        if value is None:
            return float("nan")
        if isinstance(value, (bool, str, bytes)):
            raise ValueError("V5 feature must be numeric or missing")
        try:
            number = float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError("V5 feature must be numeric or missing") from exc
        if np.isinf(number):
            raise ValueError("V5 feature cannot be infinite")
        return number

    def transform(
        self,
        phases: Sequence[Mapping[str, object]],
        context: Mapping[str, object],
    ) -> tuple[np.ndarray, np.ndarray]:
        if len(phases) != 3:
            raise ValueError("V5 requires exactly three real phase records")
        expected_keys = set(self.temporal_features) | {"phase"}
        temporal = np.empty((3, 29), dtype=np.float64)
        for phase_index, record in enumerate(phases):
            if record.get("phase") != phase_index + 1:
                raise ValueError("V5 phase order must be 1, 2, 3")
            if set(record) != expected_keys:
                raise ValueError("V5 phase feature keys must match exact registry")
            temporal[phase_index] = [self._value(record[name]) for name in self.temporal_features]
        if set(context) != set(self.context_features):
            raise ValueError("V5 context feature keys must match exact registry")
        static = np.asarray([self._value(context[name]) for name in self.context_features], dtype=np.float64)

        # Match FoldPreprocessor._impute_clip_dynamic: phase medians first, then
        # clip the seven IMU fields, then StandardScaler on the flattened rows.
        for column, name in enumerate(self.temporal_features):
            for phase in range(3):
                if np.isnan(temporal[phase, column]):
                    temporal[phase, column] = self._phase_medians[name][phase]
            if name in self._winsor_bounds:
                lower, upper = self._winsor_bounds[name]
                temporal[:, column] = np.clip(temporal[:, column], lower, upper)
        for column, name in enumerate(self.context_features):
            if np.isnan(static[column]):
                static[column] = self._context_medians[name]
        temporal = ((temporal - self._temporal_mean) / self._temporal_scale).astype(np.float32)[None, :, :]
        static = ((static - self._context_mean) / self._context_scale).astype(np.float32)[None, :]
        if not np.isfinite(temporal).all() or not np.isfinite(static).all():
            raise ValueError("V5 preprocessing produced nonfinite input")
        return temporal, static
