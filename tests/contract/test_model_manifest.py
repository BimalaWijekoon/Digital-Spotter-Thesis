from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from digital_spotter.config import load_settings
from config.constants import FEATURE_ORDER
from digital_spotter.cli import main
from digital_spotter.contracts.model import (
    COMPATIBILITY_FEATURE_ORDER,
    load_model_manifest,
    validate_model_package,
)
from digital_spotter.core import StartupValidationError, require_model_package


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
MANIFEST = REPOSITORY_ROOT / "models" / "manifest.json"


def _copy_package(tmp_path: Path) -> Path:
    package = tmp_path / "model-package"
    package.mkdir()
    manifest = load_model_manifest(MANIFEST)
    shutil.copy2(MANIFEST, package / "manifest.json")
    for artifact in manifest.artifacts:
        source = MANIFEST.parent / artifact.path
        if source.exists():
            shutil.copy2(source, package / artifact.path)
    return package / "manifest.json"


def test_manifest_hashes_and_compatibility_contract_pass():
    result = validate_model_package(MANIFEST)

    assert result.compatibility_ready is True
    assert result.artifacts_valid is True
    assert result.feature_order_valid is True
    assert result.production_ready is False
    assert "model package is unsigned" in result.warnings


def test_manifest_feature_order_matches_export_and_legacy_code_exactly():
    manifest = load_model_manifest(MANIFEST)
    manifest_order = tuple(feature.name for feature in manifest.features)

    assert manifest_order == COMPATIBILITY_FEATURE_ORDER
    assert manifest_order == tuple(FEATURE_ORDER)
    assert manifest.input.shape == (1, 4, 40)
    assert manifest.output.bad_form_threshold == 0.35947465896606445


def test_artifact_tampering_fails_readiness(tmp_path):
    manifest_path = _copy_package(tmp_path)
    with (manifest_path.parent / "model_quantized.tflite").open("ab") as model:
        model.write(b"tampered")

    result = validate_model_package(manifest_path)

    assert result.compatibility_ready is False
    assert result.artifacts_valid is False
    assert any("model_quantized.tflite" in error for error in result.errors)


def test_missing_required_artifact_fails_readiness(tmp_path):
    manifest_path = _copy_package(tmp_path)
    (manifest_path.parent / "scaler.save").unlink()

    result = validate_model_package(manifest_path)

    assert result.compatibility_ready is False
    assert "artifact missing: scaler.save" in result.errors


def test_feature_order_mismatch_fails_readiness(tmp_path):
    manifest_path = _copy_package(tmp_path)
    parsed = json.loads(manifest_path.read_text(encoding="utf-8"))
    parsed["features"][0], parsed["features"][1] = parsed["features"][1], parsed["features"][0]
    manifest_path.write_text(json.dumps(parsed), encoding="utf-8")

    result = validate_model_package(manifest_path)

    assert result.compatibility_ready is False
    assert result.feature_order_valid is False


def test_production_readiness_fails_closed_for_compatibility_package():
    result = validate_model_package(MANIFEST, production=True)

    assert result.production_ready is False
    assert any(error.startswith("production blocked:") for error in result.errors)


def test_installed_cli_reports_compatibility_and_production_states(capsys):
    assert main(["model", "check", "--manifest", str(MANIFEST)]) == 0
    compatibility = json.loads(capsys.readouterr().out)
    assert compatibility["compatibility_ready"] is True
    assert compatibility["production_ready"] is False

    assert main(["model", "check", "--manifest", str(MANIFEST), "--production"]) == 3
    production = json.loads(capsys.readouterr().out)
    assert production["production_ready"] is False


def test_startup_gate_accepts_compatibility_only_outside_production():
    settings = load_settings(environ={"DS_MODEL_MANIFEST_PATH": str(MANIFEST)})

    loaded = require_model_package(settings)

    assert loaded.package_id == "digital-spotter-v4-compat"


def test_startup_gate_rejects_current_package_in_production(tmp_path):
    for name in ("device.key", "local.crt", "local.key"):
        (tmp_path / name).write_text("test-only\n", encoding="utf-8")
    data_dir = tmp_path / "data"
    run_dir = tmp_path / "run"
    data_dir.mkdir()
    run_dir.mkdir()
    settings = load_settings(
        environ={
            "DS_PROFILE": "production",
            "DS_DEVICE_ID": "device-test-001",
            "DS_ALLOWED_ORIGINS": "https://spotter.test",
            "DS_DATA_DIR": str(data_dir),
            "DS_RUNTIME_DIR": str(run_dir),
            "DS_DATABASE_PATH": str(data_dir / "spotter.sqlite3"),
            "DS_MODEL_MANIFEST_PATH": str(MANIFEST),
            "DS_DEVICE_IDENTITY_KEY_PATH": str(tmp_path / "device.key"),
            "DS_LOCAL_TLS_CERT_PATH": str(tmp_path / "local.crt"),
            "DS_LOCAL_TLS_KEY_PATH": str(tmp_path / "local.key"),
            "DS_VISION_PIPELINE": "canonical",
            "DS_VISION_ADAPTER": "real",
            "DS_IMU_ADAPTER": "real",
        }
    )

    with pytest.raises(StartupValidationError, match="production blocked"):
        require_model_package(settings)
