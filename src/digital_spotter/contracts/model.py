"""Model-package manifest schema and hash/readiness validation."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import Enum
from pathlib import Path, PurePosixPath
from typing import Any, Sequence

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


MAX_MANIFEST_BYTES = 1024 * 1024
COMPATIBILITY_FEATURE_ORDER = (
    "Subject_Height_cm", "Subject_Weight_kg", "Exercise_ID", "Rep_Phase", "Load_kg",
    "Vis_L_Shoulder_X", "Vis_L_Shoulder_Y", "Vis_R_Shoulder_X", "Vis_R_Shoulder_Y",
    "Vis_L_Hip_X", "Vis_L_Hip_Y", "Vis_R_Hip_X", "Vis_R_Hip_Y",
    "Vis_L_Knee_X", "Vis_L_Knee_Y", "Vis_R_Knee_X", "Vis_R_Knee_Y",
    "Vis_L_Ankle_X", "Vis_L_Ankle_Y", "Vis_R_Ankle_X", "Vis_R_Ankle_Y",
    "Angle_Trunk_Inclination", "IMU_Acc_X", "IMU_Acc_Y", "IMU_Acc_Z",
    "IMU_Gyro_X", "IMU_Gyro_Y", "IMU_Gyro_Z", "V_Bar_Velocity_Vertical",
    "P_Bar_Power_Watts", "Smoothness_Jerk", "Hip_Flexion_Asymmetry",
    "Knee_Flexion_Asymmetry", "Ankle_Dorsiflexion_Asymmetry", "IMU_Acc_Magnitude",
    "Knee_Hip_Coupling_L", "Knee_Hip_Coupling_R", "Velocity_Decel_Ratio",
    "Femur_Tibia_Ratio", "BMI",
)


class ManifestError(ValueError):
    """Raised when the manifest file itself cannot be safely parsed."""


class UnitStatus(str, Enum):
    KNOWN = "known"
    INFERRED = "inferred"
    UNKNOWN = "unknown"
    CATEGORICAL = "categorical"


class ManifestModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        allow_inf_nan=False,
        protected_namespaces=(),
    )


class ArtifactSpec(ManifestModel):
    path: str = Field(min_length=1, max_length=255)
    purpose: str = Field(min_length=1, max_length=64)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    size_bytes: int = Field(ge=0, le=2 * 1024 * 1024 * 1024)
    required: bool

    @field_validator("path")
    @classmethod
    def path_must_be_safe_relative_posix(cls, value: str) -> str:
        path = PurePosixPath(value)
        if path.is_absolute() or ".." in path.parts or "." in path.parts:
            raise ValueError("artifact path must be safe and relative")
        return value


class TensorSpec(ManifestModel):
    name: str = Field(min_length=1, max_length=255)
    shape: tuple[int, ...] = Field(min_length=1, max_length=8)
    shape_signature: tuple[int, ...] = Field(min_length=1, max_length=8)
    dtype: str = Field(min_length=1, max_length=32)
    quantization_scale: float
    quantization_zero_point: int


class OutputSpec(TensorSpec):
    meaning: str = Field(min_length=1, max_length=255)
    good_form_label: str = Field(min_length=1, max_length=128)
    bad_form_label: str = Field(min_length=1, max_length=128)
    bad_form_threshold: float = Field(ge=0.0, le=1.0)


class SequenceContract(ManifestModel):
    phase_rows: tuple[str, ...] = Field(min_length=3, max_length=3)
    fourth_row: str = Field(min_length=1, max_length=128)
    velocity_decel_ratio_delta_override: bool


class FeatureSpec(ManifestModel):
    name: str = Field(min_length=1, max_length=128)
    unit: str = Field(min_length=1, max_length=64)
    unit_status: UnitStatus
    source: str = Field(min_length=1, max_length=64)
    note: str | None = Field(default=None, max_length=512)


class PreprocessingStep(ManifestModel):
    order: int = Field(ge=1, le=32)
    operation: str = Field(min_length=1, max_length=64)
    artifact: str | None = Field(default=None, max_length=255)
    detail: str = Field(min_length=1, max_length=512)


class MissingDataPolicy(ManifestModel):
    artifact_policy: str = Field(min_length=1, max_length=512)
    prototype_behavior: str = Field(min_length=1, max_length=512)
    product_policy: str = Field(min_length=1, max_length=512)


class RuntimeSpec(ManifestModel):
    validated_platform: str = Field(min_length=1, max_length=255)
    validated_ai_edge_litert: str = Field(min_length=1, max_length=64)
    validated_tensorflow_preload: str | None = Field(default=None, max_length=64)
    requires_flex_delegate: bool
    observed_delegates: tuple[str, ...] = Field(max_length=16)
    operators: tuple[str, ...] = Field(min_length=1, max_length=256)


class TrainingProvenance(ManifestModel):
    status: str = Field(min_length=1, max_length=32)
    artifact_commit: str = Field(pattern=r"^[0-9a-f]{7,40}$")
    claimed_source: str = Field(min_length=1, max_length=255)
    training_notebook: str | None = None
    dataset_manifest: str | None = None
    split_manifest: str | None = None
    scaler_samples_seen: int = Field(ge=0)


class EvaluationSpec(ManifestModel):
    status: str = Field(min_length=1, max_length=32)
    metrics: dict[str, float] = Field(max_length=128)
    threshold_rationale: str | None = Field(default=None, max_length=2048)
    approved_exercises: tuple[str, ...] = Field(max_length=64)


class SignatureSpec(ManifestModel):
    status: str = Field(pattern=r"^(unsigned|verified)$")
    required_for_production: bool
    algorithm: str | None = Field(default=None, max_length=64)
    key_id: str | None = Field(default=None, max_length=128)
    signature_file: str | None = Field(default=None, max_length=255)


class ModelManifest(ManifestModel):
    schema_version: int = Field(ge=1, le=1)
    package_id: str = Field(min_length=1, max_length=128)
    model_version: str = Field(min_length=1, max_length=64)
    feature_contract_version: str = Field(min_length=1, max_length=64)
    release_status: str = Field(pattern=r"^(compatibility_only|approved)$")
    artifacts: tuple[ArtifactSpec, ...] = Field(min_length=1, max_length=64)
    input: TensorSpec
    output: OutputSpec
    sequence_contract: SequenceContract
    features: tuple[FeatureSpec, ...] = Field(min_length=1, max_length=512)
    preprocessing: tuple[PreprocessingStep, ...] = Field(min_length=1, max_length=32)
    missing_data_policy: MissingDataPolicy
    runtime: RuntimeSpec
    training_provenance: TrainingProvenance
    evaluation: EvaluationSpec
    limitations: tuple[str, ...] = Field(min_length=1, max_length=128)
    signature: SignatureSpec

    @model_validator(mode="after")
    def validate_contract_consistency(self) -> "ModelManifest":
        artifact_paths = [artifact.path for artifact in self.artifacts]
        if len(artifact_paths) != len(set(artifact_paths)):
            raise ValueError("artifact paths must be unique")
        purposes = [artifact.purpose for artifact in self.artifacts]
        if len(purposes) != len(set(purposes)):
            raise ValueError("artifact purposes must be unique")
        if "primary_model" not in purposes:
            raise ValueError("manifest requires one primary_model artifact")

        feature_names = [feature.name for feature in self.features]
        if len(feature_names) != len(set(feature_names)):
            raise ValueError("feature names must be unique")
        if self.input.shape != (1, 4, len(feature_names)):
            raise ValueError("input shape must match batch, sequence, and feature count")
        if self.input.shape_signature != (-1, 4, len(feature_names)):
            raise ValueError("input shape signature must match feature contract")
        if self.output.shape != (1, 1) or self.output.shape_signature != (-1, 1):
            raise ValueError("compatibility output must be one scalar per batch")
        if self.input.dtype != "float32" or self.output.dtype != "float32":
            raise ValueError("compatibility tensors must be float32")

        orders = [step.order for step in self.preprocessing]
        if orders != list(range(1, len(orders) + 1)):
            raise ValueError("preprocessing order must be contiguous and ordered")
        artifact_set = set(artifact_paths)
        for step in self.preprocessing:
            if step.artifact is not None and step.artifact not in artifact_set:
                raise ValueError("preprocessing references an unlisted artifact")
        return self


@dataclass(frozen=True)
class ModelPackageValidation:
    manifest: ModelManifest | None
    errors: tuple[str, ...]
    warnings: tuple[str, ...]
    artifacts_valid: bool
    feature_order_valid: bool
    production_ready: bool

    @property
    def compatibility_ready(self) -> bool:
        return self.manifest is not None and not self.errors and self.artifacts_valid

    def safe_summary(self) -> dict[str, Any]:
        return {
            "package_id": self.manifest.package_id if self.manifest else None,
            "model_version": self.manifest.model_version if self.manifest else None,
            "compatibility_ready": self.compatibility_ready,
            "production_ready": self.production_ready,
            "artifacts_valid": self.artifacts_valid,
            "feature_order_valid": self.feature_order_valid,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
        }


def load_model_manifest(path: Path) -> ModelManifest:
    try:
        if not path.is_file():
            raise ManifestError(f"manifest not found: {path}")
        if path.stat().st_size > MAX_MANIFEST_BYTES:
            raise ManifestError(f"manifest exceeds {MAX_MANIFEST_BYTES} bytes")
        parsed = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(parsed, dict):
            raise ManifestError("manifest root must be an object")
        return ModelManifest.model_validate(parsed)
    except ManifestError:
        raise
    except Exception as exc:
        raise ManifestError(f"invalid model manifest: {exc}") from exc


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def validate_model_package(
    manifest_path: Path,
    *,
    production: bool = False,
    expected_feature_order: Sequence[str] = COMPATIBILITY_FEATURE_ORDER,
) -> ModelPackageValidation:
    errors: list[str] = []
    warnings: list[str] = []
    try:
        manifest = load_model_manifest(manifest_path)
    except ManifestError as exc:
        return ModelPackageValidation(None, (str(exc),), (), False, False, False)

    package_root = manifest_path.parent.resolve()
    artifacts_valid = True
    for artifact in manifest.artifacts:
        artifact_path = (package_root / artifact.path).resolve()
        if not artifact_path.is_relative_to(package_root):
            errors.append(f"artifact escapes package root: {artifact.path}")
            artifacts_valid = False
            continue
        if not artifact_path.is_file():
            message = f"artifact missing: {artifact.path}"
            if artifact.required:
                errors.append(message)
                artifacts_valid = False
            else:
                warnings.append(message)
            continue
        actual_size = artifact_path.stat().st_size
        if actual_size != artifact.size_bytes:
            errors.append(f"artifact size mismatch: {artifact.path}")
            artifacts_valid = False
            continue
        if _sha256(artifact_path) != artifact.sha256:
            errors.append(f"artifact hash mismatch: {artifact.path}")
            artifacts_valid = False

    actual_order = tuple(feature.name for feature in manifest.features)
    feature_order_valid = actual_order == tuple(expected_feature_order)
    if not feature_order_valid:
        errors.append("feature order does not match canonical compatibility contract")

    if manifest.signature.status != "verified":
        warnings.append("model package is unsigned")
    if manifest.release_status != "approved":
        warnings.append("model package is compatibility-only")
    if manifest.training_provenance.status != "complete":
        warnings.append("training provenance is incomplete")
    if manifest.evaluation.status != "complete":
        warnings.append("release evaluation is unavailable")
    if any(feature.unit_status is UnitStatus.UNKNOWN for feature in manifest.features):
        warnings.append("one or more feature units are unknown")
    if manifest.runtime.requires_flex_delegate:
        warnings.append("model requires TensorFlow Flex operators")

    if production:
        for warning in tuple(warnings):
            errors.append(f"production blocked: {warning}")

    production_ready = (
        not errors
        and artifacts_valid
        and feature_order_valid
        and manifest.signature.status == "verified"
        and manifest.release_status == "approved"
        and manifest.training_provenance.status == "complete"
        and manifest.evaluation.status == "complete"
        and not manifest.runtime.requires_flex_delegate
    )
    return ModelPackageValidation(
        manifest,
        tuple(errors),
        tuple(warnings),
        artifacts_valid,
        feature_order_valid,
        production_ready,
    )
