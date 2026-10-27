from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from digital_spotter.cli import main
from digital_spotter.config import (
    AdapterMode,
    RuntimeProfile,
    SettingsLoadError,
    VisionPipeline,
    load_settings,
)


def _production_config(tmp_path: Path) -> Path:
    for name in ("manifest.json", "device.key", "local.crt", "local.key"):
        (tmp_path / name).write_text("test-only\n", encoding="utf-8")
    data_dir = tmp_path / "data"
    run_dir = tmp_path / "run"
    data_dir.mkdir()
    run_dir.mkdir()
    config = tmp_path / "config.toml"
    config.write_text(
        f"""
schema_version = 1
profile = "production"
device_id = "device-test-001"

[api]
host = "0.0.0.0"
port = 8443
allowed_origins = ["https://spotter.test"]

[paths]
data_dir = "{data_dir}"
runtime_dir = "{run_dir}"
database = "{data_dir / 'digital-spotter.sqlite3'}"
model_manifest = "{tmp_path / 'manifest.json'}"
device_identity_key = "{tmp_path / 'device.key'}"
local_tls_cert = "{tmp_path / 'local.crt'}"
local_tls_key = "{tmp_path / 'local.key'}"

[adapters]
vision_pipeline = "canonical"
vision = "real"
imu = "real"

[video]
publish_url = "rtsp://127.0.0.1:8554/picamera2"

[security]
model_signature_required = true
""".strip(),
        encoding="utf-8",
    )
    return config


def test_development_defaults_are_explicitly_simulated():
    settings = load_settings(environ={})

    assert settings.profile is RuntimeProfile.DEVELOPMENT
    assert settings.vision_pipeline is VisionPipeline.LEGACY
    assert settings.vision_adapter is AdapterMode.SIMULATED
    assert settings.imu_adapter is AdapterMode.SIMULATED
    assert settings.api_host == "127.0.0.1"
    assert settings.video_publish_url is None


def test_production_rejects_missing_mandatory_configuration():
    with pytest.raises(ValidationError, match="production requires provisioned"):
        load_settings(environ={"DS_PROFILE": "production"})


def test_production_configuration_accepts_provisioned_real_adapters(tmp_path):
    settings = load_settings(_production_config(tmp_path), environ={})

    assert settings.profile is RuntimeProfile.PRODUCTION
    assert settings.vision_pipeline is VisionPipeline.CANONICAL
    assert settings.device_id == "device-test-001"
    assert settings.vision_adapter is AdapterMode.REAL
    assert settings.imu_adapter is AdapterMode.REAL
    assert settings.allowed_origins == ("https://spotter.test",)
    assert settings.video_publish_url == "rtsp://127.0.0.1:8554/picamera2"


def test_video_publication_requires_a_loopback_rtsp_url(tmp_path):
    config = tmp_path / "config.toml"
    config.write_text(
        '[video]\npublish_url = "rtsp://192.0.2.10:8554/picamera2"\n',
        encoding="utf-8",
    )

    with pytest.raises(ValidationError, match="loopback RTSP"):
        load_settings(config, environ={})


def test_production_rejects_legacy_vision_pipeline(tmp_path):
    config = _production_config(tmp_path)
    text = config.read_text(encoding="utf-8").replace(
        'vision_pipeline = "canonical"', 'vision_pipeline = "legacy"'
    )
    config.write_text(text, encoding="utf-8")

    with pytest.raises(ValidationError, match="canonical vision pipeline"):
        load_settings(config, environ={})


def test_environment_has_precedence_over_toml(tmp_path):
    config = tmp_path / "config.toml"
    config.write_text('[api]\nport = 8000\n', encoding="utf-8")

    settings = load_settings(config, environ={"DS_API_PORT": "8123"})

    assert settings.api_port == 8123


def test_vision_pipeline_switch_is_explicit_and_strict():
    settings = load_settings(environ={"DS_VISION_PIPELINE": "canonical"})

    assert settings.vision_pipeline is VisionPipeline.CANONICAL

    with pytest.raises(ValidationError, match="vision_pipeline"):
        load_settings(environ={"DS_VISION_PIPELINE": "unknown"})


def test_production_rejects_wildcard_origin(tmp_path):
    config = _production_config(tmp_path)
    text = config.read_text(encoding="utf-8").replace(
        'allowed_origins = ["https://spotter.test"]', 'allowed_origins = ["*"]'
    )
    config.write_text(text, encoding="utf-8")

    with pytest.raises(ValidationError, match="explicit HTTPS origins"):
        load_settings(config, environ={})


def test_unknown_toml_key_fails_closed(tmp_path):
    config = tmp_path / "config.toml"
    config.write_text("surprise = true\n", encoding="utf-8")

    with pytest.raises(SettingsLoadError, match="unknown configuration keys"):
        load_settings(config, environ={})


def test_cli_prints_only_safe_configuration_summary(tmp_path, capsys):
    config = _production_config(tmp_path)

    assert main(["config", "check", "--config", str(config)]) == 0
    output = json.loads(capsys.readouterr().out)

    assert output["profile"] == "production"
    assert output["device_identity_configured"] is True
    assert "device.key" not in json.dumps(output)
