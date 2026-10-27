from __future__ import annotations

import os
import subprocess
from pathlib import Path


def test_core_launcher_leaves_exact_run_directory_for_core_to_create(tmp_path):
    fake_python = tmp_path / "fake-python"
    fake_python.write_text("#!/bin/sh\nprintf '%s\\n' \"$@\"\n", encoding="ascii")
    fake_python.chmod(0o755)
    state_root = tmp_path / "state"
    runtime_dir = tmp_path / "runtime"
    repository = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        ["/bin/sh", str(repository / "deploy/research-appliance/run-core.sh")],
        check=True,
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "DS_RELEASE_DIR": str(repository),
            "DS_CORE_PYTHON": str(fake_python),
            "DS_MODEL_PACKAGE": str(tmp_path / "model"),
            "DS_STATE_ROOT": str(state_root),
            "DS_RUNTIME_DIR": str(runtime_dir),
        },
    )
    arguments = result.stdout.splitlines()
    run_dir = Path(arguments[arguments.index("--run-dir") + 1])

    assert run_dir.parent.parent == state_root / "runs"
    assert not run_dir.exists()
    assert runtime_dir.is_dir()


def test_media_launcher_binds_ice_only_to_configured_tailnet_address(tmp_path):
    repository = Path(__file__).resolve().parents[2]
    fake_mediamtx = tmp_path / "fake-mediamtx"
    fake_mediamtx.write_text("#!/bin/sh\ncat \"$1\"\n", encoding="ascii")
    fake_mediamtx.chmod(0o755)
    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir()
    result = subprocess.run(
        ["/bin/sh", str(repository / "deploy/research-appliance/run-media.sh")],
        check=True,
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "DS_RELEASE_DIR": str(repository),
            "DS_MEDIAMTX_BIN": str(fake_mediamtx),
            "DS_RUNTIME_DIR": str(runtime_dir),
            "DS_POSE_PYTHON": "/usr/bin/python3",
            "DS_CAMERA_PYTHON": "/usr/bin/python3",
            "DS_TAILSCALE_IP": "100.64.12.34",
            "DS_ALLOWED_ORIGIN": "https://pidigitalspotter.example-tailnet.ts.net",
        },
        cwd=repository / "scripts",
    )
    assert "webrtcAddress: 127.0.0.1:8889" in result.stdout
    assert "webrtcLocalTCPAddress: 100.64.12.34:8189" in result.stdout
    assert "webrtcAdditionalHosts: [100.64.12.34]" in result.stdout
    assert "webrtcAllowOrigin: https://pidigitalspotter.example-tailnet.ts.net" in result.stdout


def test_tailscale_serve_setup_keeps_http_upstreams_on_loopback_and_leaves_ice_direct():
    repository = Path(__file__).resolve().parents[2]
    script = (repository / "deploy/research-appliance/configure-tailscale-serve.sh").read_text(
        encoding="ascii"
    )
    assert "--https=443" in script and "127.0.0.1:8766" in script
    assert "--https=8443" in script and "127.0.0.1:8889" in script
    assert "tailscale serve --yes --tcp=8189 off" in script
    assert "tcp://127.0.0.1:8189" not in script
    assert "tailscale funnel" not in script.lower()
