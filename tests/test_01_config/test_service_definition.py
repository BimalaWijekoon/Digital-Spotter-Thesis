"""Regression checks for the temporary Pi migration service definition."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
UNIT = (ROOT / "scripts" / "digital-spotter.service").read_text()
INSTALLER = (ROOT / "scripts" / "install_service.sh").read_text()


def test_service_matches_verified_pi_migration_layout():
    """The checked-in M0 unit must match the actual installed Pi identity."""
    assert "User=pibimalawijekoon" in UNIT
    assert "WorkingDirectory=/home/pibimalawijekoon/Digital-Spotter" in UNIT
    assert "/.pyenv/versions/3.12.0/bin/python3" in UNIT
    assert "DS_API_PORT=8000" in UNIT


def test_installer_uses_existing_unit_name_and_dynamic_address():
    """Installation must update the existing unit without a stale fixed IP."""
    assert 'SERVICE_NAME="digitalspotter"' in INSTALLER
    assert "192.168.1.8" not in INSTALLER
    assert "tailscale ip -4" in INSTALLER
