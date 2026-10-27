#!/usr/bin/env python3
"""Bounded E3 camera-loss/recovery gate for the canonical vision agent.

The harness retains event metadata and process logs only. It never stores camera
frames, installs a service, or starts the legacy dashboard camera owner.
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import socket
import struct
import subprocess
import tempfile
import threading
import time
from pathlib import Path

import msgpack


MAX_EVENT_BYTES = 64 * 1024


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--python", default=os.sys.executable)
    parser.add_argument("--camera-python", default="/usr/bin/python3")
    parser.add_argument("--extra-site-packages", type=Path)
    parser.add_argument("--camera-id", default="picamera2-imx219")
    parser.add_argument("--initial-timeout", type=float, default=40.0)
    parser.add_argument("--failure-timeout", type=float, default=15.0)
    parser.add_argument("--recovery-timeout", type=float, default=40.0)
    parser.add_argument("--evidence-dir", type=Path, required=True)
    return parser


def _receive_exact(connection: socket.socket, size: int) -> bytes | None:
    data = bytearray()
    while len(data) < size:
        try:
            part = connection.recv(size - len(data))
        except socket.timeout:
            continue
        if not part:
            return None
        data.extend(part)
    return bytes(data)


def _event_summary(payload: bytes) -> dict[str, object]:
    unpacked = msgpack.unpackb(payload, raw=False)
    event_type = unpacked.get("event_type")
    event_payload = unpacked.get("payload", {})
    summary: dict[str, object] = {"event_type": event_type}
    if event_type == "health_state":
        summary.update(
            state=event_payload.get("state"),
            reason_codes=event_payload.get("reason_codes", []),
            is_simulated=event_payload.get("is_simulated"),
        )
    elif event_type == "pose_sample":
        summary.update(
            camera_id=event_payload.get("camera_id"),
            quality=unpacked.get("quality"),
            reason_code=unpacked.get("reason_code"),
            landmark_count=len(event_payload.get("landmarks", [])),
        )
    return summary


class EventCollector:
    def __init__(self, socket_path: Path) -> None:
        self.socket_path = socket_path
        self.events: list[dict[str, object]] = []
        self.errors: list[str] = []
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._server: socket.socket | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        server.bind(str(self.socket_path))
        os.chmod(self.socket_path, 0o600)
        server.listen(2)
        server.settimeout(0.2)
        self._server = server
        self._thread = threading.Thread(
            target=self._run,
            name="vision-step7-event-collector",
            daemon=True,
        )
        self._thread.start()

    def _run(self) -> None:
        assert self._server is not None
        while not self._stop.is_set():
            try:
                connection, _ = self._server.accept()
            except socket.timeout:
                continue
            except OSError:
                return
            with connection:
                connection.settimeout(0.2)
                while not self._stop.is_set():
                    prefix = _receive_exact(connection, 4)
                    if prefix is None:
                        break
                    length = struct.unpack(">I", prefix)[0]
                    if length < 1 or length > MAX_EVENT_BYTES:
                        with self._lock:
                            self.errors.append(f"invalid event length: {length}")
                        break
                    payload = _receive_exact(connection, length)
                    if payload is None:
                        with self._lock:
                            self.errors.append("connection closed during event payload")
                        break
                    try:
                        summary = _event_summary(payload)
                    except Exception as exc:
                        with self._lock:
                            self.errors.append(f"event decode failed: {exc}")
                        continue
                    with self._lock:
                        self.events.append(summary)

    def snapshot(self) -> list[dict[str, object]]:
        with self._lock:
            return list(self.events)

    def close(self) -> None:
        self._stop.set()
        if self._server is not None:
            self._server.close()
        if self._thread is not None:
            self._thread.join(timeout=2.0)


def _wait_until(predicate, timeout_s: float, description: str) -> None:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.05)
    raise TimeoutError(f"timed out waiting for {description}")


def _child_camera_helper(agent_pid: int, timeout_s: float) -> int:
    children_path = Path(f"/proc/{agent_pid}/task/{agent_pid}/children")

    def find() -> int | None:
        try:
            child_ids = children_path.read_text(encoding="ascii").split()
        except OSError:
            return None
        for raw_pid in child_ids:
            try:
                command = Path(f"/proc/{raw_pid}/cmdline").read_bytes().replace(b"\0", b" ")
            except OSError:
                continue
            if b"picamera2_helper.py" in command:
                return int(raw_pid)
        return None

    found: list[int] = []

    def capture() -> bool:
        pid = find()
        if pid is None:
            return False
        found.append(pid)
        return True

    _wait_until(capture, timeout_s, "the agent-owned Picamera2 helper")
    return found[0]


def _agent_command(args: argparse.Namespace, socket_path: Path) -> list[str]:
    runtime_args = [
        "--camera-id",
        args.camera_id,
        "--camera-python",
        args.camera_python,
        "--socket",
        str(socket_path),
        "--core-uid",
        str(os.getuid()),
        "--close-timeout",
        "3.0",
    ]
    if args.extra_site_packages is None:
        return [args.python, "-m", "digital_spotter.vision.runtime", *runtime_args]
    wrapper = (
        "import site,sys; "
        "site.addsitedir(sys.argv[1]); "
        "from digital_spotter.vision.runtime import main; "
        "raise SystemExit(main(sys.argv[2:]))"
    )
    return [
        args.python,
        "-c",
        wrapper,
        str(args.extra_site_packages),
        *runtime_args,
    ]


def _start_agent(args: argparse.Namespace, socket_path: Path) -> subprocess.Popen[str]:
    environment = os.environ.copy()
    source_path = str((args.project_root / "src").resolve())
    existing_pythonpath = environment.get("PYTHONPATH")
    environment["PYTHONPATH"] = (
        f"{source_path}{os.pathsep}{existing_pythonpath}"
        if existing_pythonpath
        else source_path
    )
    environment["DS_PROFILE"] = "development"
    environment["DS_VISION_PIPELINE"] = "canonical"
    environment["DS_VISION_ADAPTER"] = "real"
    return subprocess.Popen(
        _agent_command(args, socket_path),
        cwd=args.project_root,
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def _finish_agent(
    process: subprocess.Popen[str],
    *,
    timeout_s: float,
) -> tuple[int, str, str]:
    stdout, stderr = process.communicate(timeout=timeout_s)
    return process.returncode, stdout, stderr


def _health_seen(
    events: list[dict[str, object]],
    *,
    state: str,
    reason: str | None = None,
) -> bool:
    for event in events:
        if event.get("event_type") != "health_state" or event.get("state") != state:
            continue
        if reason is None or reason in event.get("reason_codes", []):
            return True
    return False


def _pose_count(events: list[dict[str, object]]) -> int:
    return sum(event.get("event_type") == "pose_sample" for event in events)


def _read_command(command: list[str]) -> str | None:
    try:
        result = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=3.0,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    output = result.stdout.strip()
    return output or None


def _terminate_if_running(process: subprocess.Popen[str] | None) -> None:
    if process is None or process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=5.0)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5.0)


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    project_root = args.project_root.resolve()
    if not (project_root / "src/digital_spotter/vision/runtime.py").is_file():
        raise ValueError("project root does not contain the canonical vision runtime")
    for value, name in (
        (args.initial_timeout, "initial timeout"),
        (args.failure_timeout, "failure timeout"),
        (args.recovery_timeout, "recovery timeout"),
    ):
        if value <= 0 or value > 120:
            raise ValueError(f"{name} must be between zero and 120 seconds")

    evidence_dir = args.evidence_dir.resolve()
    evidence_dir.mkdir(parents=True, exist_ok=True)
    started_at = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    result: dict[str, object] = {
        "evidence_environment": "E3_pi_camera_loss_recovery",
        "hardware_simulated": False,
        "frames_retained": False,
        "started_at": started_at,
        "throttled_before": _read_command(["vcgencmd", "get_throttled"]),
        "temperature_before": _read_command(["vcgencmd", "measure_temp"]),
    }

    first_agent: subprocess.Popen[str] | None = None
    recovery_agent: subprocess.Popen[str] | None = None
    with tempfile.TemporaryDirectory(prefix="ds-vision-step7-") as temporary:
        socket_path = Path(temporary) / "vision-events.sock"
        collector = EventCollector(socket_path)
        collector.start()
        try:
            first_agent = _start_agent(args, socket_path)
            first_helper = _child_camera_helper(first_agent.pid, args.initial_timeout)
            _wait_until(
                lambda: _pose_count(collector.snapshot()) >= 1,
                args.initial_timeout,
                "an initial real-camera pose event",
            )
            before_loss = len(collector.snapshot())
            os.kill(first_helper, signal.SIGTERM)
            first_code, first_stdout, first_stderr = _finish_agent(
                first_agent,
                timeout_s=args.failure_timeout,
            )
            first_agent = None
            _wait_until(
                lambda: _health_seen(
                    collector.snapshot()[before_loss:],
                    state="degraded",
                    reason="camera_unavailable",
                ),
                3.0,
                "camera_unavailable health",
            )
            failure_events = collector.snapshot()

            recovery_start = len(failure_events)
            recovery_agent = _start_agent(args, socket_path)
            recovery_helper = _child_camera_helper(
                recovery_agent.pid,
                args.recovery_timeout,
            )
            _wait_until(
                lambda: _pose_count(collector.snapshot()[recovery_start:]) >= 1,
                args.recovery_timeout,
                "a real-camera event after fresh-owner recovery",
            )
            recovery_agent.send_signal(signal.SIGINT)
            recovery_code, recovery_stdout, recovery_stderr = _finish_agent(
                recovery_agent,
                timeout_s=10.0,
            )
            recovery_agent = None
            time.sleep(0.3)
            all_events = collector.snapshot()
            recovery_events = all_events[recovery_start:]
            helpers_reaped = (
                not Path(f"/proc/{first_helper}").exists()
                and not Path(f"/proc/{recovery_helper}").exists()
            )

            failure_pass = (
                first_code == 2
                and _pose_count(failure_events) >= 1
                and _health_seen(
                    failure_events[before_loss:],
                    state="degraded",
                    reason="camera_unavailable",
                )
                and _health_seen(
                    failure_events[before_loss:],
                    state="stopping",
                    reason="camera_unavailable",
                )
            )
            recovery_pass = (
                recovery_code == 0
                and _pose_count(recovery_events) >= 1
                and _health_seen(recovery_events, state="starting")
                and _health_seen(recovery_events, state="ready")
                and _health_seen(recovery_events, state="stopping")
                and helpers_reaped
            )
            result.update(
                failure_injection="SIGTERM to agent-owned picamera2_helper.py",
                initial_helper_pid=first_helper,
                recovery_helper_pid=recovery_helper,
                initial_pose_events=_pose_count(failure_events),
                recovery_pose_events=_pose_count(recovery_events),
                initial_agent_exit_code=first_code,
                recovery_agent_exit_code=recovery_code,
                camera_unavailable_health_seen=_health_seen(
                    failure_events[before_loss:],
                    state="degraded",
                    reason="camera_unavailable",
                ),
                camera_unavailable_stopping_seen=_health_seen(
                    failure_events[before_loss:],
                    state="stopping",
                    reason="camera_unavailable",
                ),
                recovery_starting_seen=_health_seen(recovery_events, state="starting"),
                recovery_ready_seen=_health_seen(recovery_events, state="ready"),
                recovery_stopping_seen=_health_seen(recovery_events, state="stopping"),
                camera_helpers_reaped=helpers_reaped,
                event_decode_errors=collector.errors,
                failure_pass=failure_pass,
                recovery_pass=recovery_pass,
                test_pass=failure_pass and recovery_pass and not collector.errors,
            )
            (evidence_dir / "failure-agent.stdout.log").write_text(
                first_stdout,
                encoding="utf-8",
            )
            (evidence_dir / "failure-agent.stderr.log").write_text(
                first_stderr,
                encoding="utf-8",
            )
            (evidence_dir / "recovery-agent.stdout.log").write_text(
                recovery_stdout,
                encoding="utf-8",
            )
            (evidence_dir / "recovery-agent.stderr.log").write_text(
                recovery_stderr,
                encoding="utf-8",
            )
        finally:
            _terminate_if_running(first_agent)
            _terminate_if_running(recovery_agent)
            collector.close()

    result["throttled_after"] = _read_command(["vcgencmd", "get_throttled"])
    result["temperature_after"] = _read_command(["vcgencmd", "measure_temp"])
    output_path = evidence_dir / "camera-loss-recovery.json"
    output_path.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result.get("test_pass") is True else 2


if __name__ == "__main__":
    raise SystemExit(main())
