"""Typed, fail-closed configuration for the canonical edge package."""

from __future__ import annotations

import os
import re
import tomllib
from enum import Enum
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, model_validator


class SettingsLoadError(ValueError):
    """Raised when a configuration source is malformed or unsupported."""


class RuntimeProfile(str, Enum):
    DEVELOPMENT = "development"
    TEST = "test"
    PRODUCTION = "production"


class AdapterMode(str, Enum):
    REAL = "real"
    SIMULATED = "simulated"
    REPLAY = "replay"


class VisionPipeline(str, Enum):
    LEGACY = "legacy"
    CANONICAL = "canonical"


class ProductSettings(BaseModel):
    """Validated non-secret settings shared by future edge services.

    Production rejects simulated adapters, wildcard/non-TLS browser origins,
    relative mutable paths, and missing identity/model/TLS artifacts. The model
    manifest's contents and signature are validated by M1-03; this layer proves the
    mandatory path is present and readable.
    """

    model_config = ConfigDict(extra="forbid", frozen=True, protected_namespaces=())

    schema_version: int = Field(default=1, ge=1, le=1)
    profile: RuntimeProfile = RuntimeProfile.DEVELOPMENT
    device_id: str | None = Field(default=None, max_length=64)
    api_host: str = Field(default="127.0.0.1", min_length=1, max_length=255)
    api_port: int = Field(default=8000, ge=1, le=65535)
    allowed_origins: tuple[str, ...] = ()
    data_dir: Path = Path("data")
    runtime_dir: Path = Path("run")
    database_path: Path = Path("data/digital-spotter.sqlite3")
    model_manifest_path: Path | None = None
    device_identity_key_path: Path | None = None
    local_tls_cert_path: Path | None = None
    local_tls_key_path: Path | None = None
    video_publish_url: str | None = None
    vision_pipeline: VisionPipeline = VisionPipeline.LEGACY
    vision_adapter: AdapterMode = AdapterMode.SIMULATED
    imu_adapter: AdapterMode = AdapterMode.SIMULATED
    model_signature_required: bool = True

    @model_validator(mode="after")
    def validate_profile_contract(self) -> "ProductSettings":
        if self.device_id is not None and not re.fullmatch(
            r"[A-Za-z0-9][A-Za-z0-9._-]{2,63}", self.device_id
        ):
            raise ValueError("device_id must be 3-64 safe identifier characters")

        if self.video_publish_url is not None:
            parsed_publish_url = urlsplit(self.video_publish_url)
            try:
                publish_port = parsed_publish_url.port
            except ValueError as exc:
                raise ValueError(
                    "video publication requires a valid loopback RTSP URL"
                ) from exc
            if (
                parsed_publish_url.scheme != "rtsp"
                or parsed_publish_url.hostname not in {"127.0.0.1", "localhost"}
                or publish_port is None
                or not parsed_publish_url.path.strip("/")
                or parsed_publish_url.username is not None
                or parsed_publish_url.password is not None
                or parsed_publish_url.query
                or parsed_publish_url.fragment
            ):
                raise ValueError("video publication requires a loopback RTSP URL")

        if self.profile is not RuntimeProfile.PRODUCTION:
            return self

        missing: list[str] = []
        if self.device_id is None:
            missing.append("device_id")
        required_files = {
            "model_manifest_path": self.model_manifest_path,
            "device_identity_key_path": self.device_identity_key_path,
            "local_tls_cert_path": self.local_tls_cert_path,
            "local_tls_key_path": self.local_tls_key_path,
        }
        for name, path in required_files.items():
            if path is None or not path.is_absolute() or not path.is_file():
                missing.append(name)
        if missing:
            raise ValueError(
                "production requires provisioned fields/files: "
                + ", ".join(sorted(missing))
            )

        mutable_paths = {
            "data_dir": self.data_dir,
            "runtime_dir": self.runtime_dir,
            "database_path": self.database_path,
        }
        relative = sorted(name for name, path in mutable_paths.items() if not path.is_absolute())
        if relative:
            raise ValueError(
                "production mutable paths must be absolute: " + ", ".join(relative)
            )

        if self.vision_adapter is not AdapterMode.REAL or self.imu_adapter is not AdapterMode.REAL:
            raise ValueError("production requires real vision and IMU adapters")
        if self.vision_pipeline is not VisionPipeline.CANONICAL:
            raise ValueError("production requires the canonical vision pipeline")
        if not self.model_signature_required:
            raise ValueError("production requires model signature verification")
        if not self.allowed_origins:
            raise ValueError("production requires at least one explicit allowed origin")
        for origin in self.allowed_origins:
            parsed = urlsplit(origin)
            if origin == "*" or parsed.scheme != "https" or not parsed.netloc:
                raise ValueError("production origins must be explicit HTTPS origins")
            if parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
                raise ValueError("allowed origins cannot include paths, queries, or fragments")
        return self

    def safe_summary(self) -> dict[str, Any]:
        """Return diagnostics that contain no key material or secret contents."""
        return {
            "schema_version": self.schema_version,
            "profile": self.profile.value,
            "device_id_configured": self.device_id is not None,
            "api_host": self.api_host,
            "api_port": self.api_port,
            "allowed_origins_count": len(self.allowed_origins),
            "vision_pipeline": self.vision_pipeline.value,
            "vision_adapter": self.vision_adapter.value,
            "imu_adapter": self.imu_adapter.value,
            "model_manifest_configured": self.model_manifest_path is not None,
            "device_identity_configured": self.device_identity_key_path is not None,
            "local_tls_configured": (
                self.local_tls_cert_path is not None and self.local_tls_key_path is not None
            ),
            "video_publication_configured": self.video_publish_url is not None,
            "model_signature_required": self.model_signature_required,
        }


_TOP_LEVEL_KEYS = {
    "schema_version",
    "profile",
    "device_id",
    "api",
    "paths",
    "adapters",
    "video",
    "security",
}
_SECTION_FIELDS: dict[str, dict[str, str]] = {
    "api": {
        "host": "api_host",
        "port": "api_port",
        "allowed_origins": "allowed_origins",
    },
    "paths": {
        "data_dir": "data_dir",
        "runtime_dir": "runtime_dir",
        "database": "database_path",
        "model_manifest": "model_manifest_path",
        "device_identity_key": "device_identity_key_path",
        "local_tls_cert": "local_tls_cert_path",
        "local_tls_key": "local_tls_key_path",
    },
    "adapters": {
        "vision_pipeline": "vision_pipeline",
        "vision": "vision_adapter",
        "imu": "imu_adapter",
    },
    "video": {"publish_url": "video_publish_url"},
    "security": {"model_signature_required": "model_signature_required"},
}
_ENV_FIELDS = {
    "DS_PROFILE": "profile",
    "DS_DEVICE_ID": "device_id",
    "DS_API_HOST": "api_host",
    "DS_API_PORT": "api_port",
    "DS_ALLOWED_ORIGINS": "allowed_origins",
    "DS_DATA_DIR": "data_dir",
    "DS_RUNTIME_DIR": "runtime_dir",
    "DS_DATABASE_PATH": "database_path",
    "DS_MODEL_MANIFEST_PATH": "model_manifest_path",
    "DS_DEVICE_IDENTITY_KEY_PATH": "device_identity_key_path",
    "DS_LOCAL_TLS_CERT_PATH": "local_tls_cert_path",
    "DS_LOCAL_TLS_KEY_PATH": "local_tls_key_path",
    "DS_VISION_PIPELINE": "vision_pipeline",
    "DS_VISION_ADAPTER": "vision_adapter",
    "DS_IMU_ADAPTER": "imu_adapter",
    "DS_VIDEO_PUBLISH_URL": "video_publish_url",
    "DS_MODEL_SIGNATURE_REQUIRED": "model_signature_required",
}


def _read_toml(path: Path) -> dict[str, Any]:
    try:
        parsed = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, tomllib.TOMLDecodeError) as exc:
        raise SettingsLoadError(f"cannot read configuration {path}: {exc}") from exc

    unknown_top = sorted(set(parsed) - _TOP_LEVEL_KEYS)
    if unknown_top:
        raise SettingsLoadError("unknown configuration keys: " + ", ".join(unknown_top))

    values: dict[str, Any] = {}
    for key in ("schema_version", "profile", "device_id"):
        if key in parsed:
            values[key] = parsed[key]
    for section, mapping in _SECTION_FIELDS.items():
        section_values = parsed.get(section, {})
        if not isinstance(section_values, dict):
            raise SettingsLoadError(f"configuration section {section} must be a table")
        unknown = sorted(set(section_values) - set(mapping))
        if unknown:
            raise SettingsLoadError(
                f"unknown {section} configuration keys: " + ", ".join(unknown)
            )
        for source_name, target_name in mapping.items():
            if source_name in section_values:
                values[target_name] = section_values[source_name]
    return values


def _environment_values(environ: Mapping[str, str]) -> dict[str, Any]:
    values: dict[str, Any] = {}
    for variable, field_name in _ENV_FIELDS.items():
        if variable not in environ:
            continue
        value: Any = environ[variable]
        if field_name == "allowed_origins":
            value = tuple(item.strip() for item in value.split(",") if item.strip())
        elif field_name == "model_signature_required":
            lowered = value.strip().lower()
            if lowered not in {"true", "false"}:
                raise SettingsLoadError(f"{variable} must be true or false")
            value = lowered == "true"
        values[field_name] = value
    return values


def load_settings(
    config_path: Path | None = None,
    *,
    environ: Mapping[str, str] | None = None,
) -> ProductSettings:
    """Load optional TOML then apply explicit environment overrides."""
    values = _read_toml(config_path) if config_path is not None else {}
    values.update(_environment_values(os.environ if environ is None else environ))
    return ProductSettings.model_validate(values)
