"""The optional pose path must keep MediaMTX's single camera owner."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path


HOOK = Path(__file__).resolve().parents[2] / "scripts/research_camera_publisher.sh"


def test_on_demand_hook_uses_canonical_vision_agent_when_status_socket_is_set(tmp_path):
    env = os.environ.copy()
    env.update({
        "DS_RESEARCH_PYTHON": "/bin/false",
        "DS_RESEARCH_POSE_PYTHON": "/bin/echo",
        "DS_RESEARCH_VISION_SRC": str(tmp_path),
        "DS_RESEARCH_EXTRA_SITE_PACKAGES": str(tmp_path),
        "DS_RESEARCH_VISION_SOCKET": str(tmp_path / "vision-events.sock"),
        "DS_RESEARCH_CAMERA_PYTHON": "/usr/bin/python3",
        "DS_RESEARCH_CAMERA_ID": "pi-imx219",
        "DS_DEVICE_ID": "pi4-research",
        "RTSP_PORT": "8554",
        "MTX_PATH": "picamera2",
    })

    result = subprocess.run(["sh", str(HOOK)], env=env, text=True, capture_output=True, check=True)

    assert "-m digital_spotter.vision.runtime" in result.stdout
    assert f"--socket {tmp_path / 'vision-events.sock'}" in result.stdout
    assert "--publish-url rtsp://127.0.0.1:8554/picamera2" in result.stdout


def test_on_demand_hook_preserves_camera_only_mode(tmp_path):
    env = os.environ.copy()
    env.update({
        "DS_RESEARCH_PYTHON": "/bin/echo",
        "DS_RESEARCH_VISION_SRC": str(tmp_path),
        "DS_RESEARCH_EXTRA_SITE_PACKAGES": str(tmp_path),
        "RTSP_PORT": "8554",
        "MTX_PATH": "picamera2",
    })
    env.pop("DS_RESEARCH_VISION_SOCKET", None)

    result = subprocess.run(["sh", str(HOOK)], env=env, text=True, capture_output=True, check=True)

    assert "research_camera_publisher.py" in result.stdout
    assert "digital_spotter.vision.runtime" not in result.stdout


def test_pose_hook_requires_its_isolated_python(tmp_path):
    env = os.environ.copy()
    env.update({
        "DS_RESEARCH_PYTHON": "/bin/echo",
        "DS_RESEARCH_VISION_SRC": str(tmp_path),
        "DS_RESEARCH_EXTRA_SITE_PACKAGES": str(tmp_path),
        "DS_RESEARCH_VISION_SOCKET": str(tmp_path / "vision-events.sock"),
        "RTSP_PORT": "8554",
        "MTX_PATH": "picamera2",
    })
    env.pop("DS_RESEARCH_POSE_PYTHON", None)

    result = subprocess.run(["sh", str(HOOK)], env=env, text=True, capture_output=True)

    assert result.returncode != 0
    assert "DS_RESEARCH_POSE_PYTHON" in result.stderr
