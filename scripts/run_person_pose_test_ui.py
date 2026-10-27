#!/usr/bin/env python3
"""Loopback-only UI for one timed, summary-only real-person pose check.

This is a research diagnostic, not a workout/session or scored-analysis service.
It never saves frames or landmarks.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import signal
import site
import tempfile
import threading
import time
from datetime import datetime, timezone
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Callable
from urllib.parse import urlsplit
from uuid import uuid4


_CAPTURE_SUMMARY_FIELDS = (
    "hardware_simulated",
    "camera",
    "pose_evaluator",
    "duration_observed_s",
    "frames_received",
    "good_pose_frames",
    "poses_not_found",
    "poses_low_visibility",
    "processing_failures",
    "read_timeouts",
    "source_frames_dropped",
    "capture_timestamps_strictly_monotonic",
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class PersonPoseTestController:
    """Own one countdown/capture at a time; retain only aggregate JSON results."""

    def __init__(
        self,
        *,
        capture: Callable[[int, threading.Event], dict],
        result_dir: Path,
        countdown_s: float = 20,
        duration_s: int = 30,
    ) -> None:
        if countdown_s < 0 or duration_s <= 0:
            raise ValueError("countdown and duration must be non-negative/positive")
        self._capture = capture
        self._result_dir = Path(result_dir)
        self._countdown_s = countdown_s
        self._duration_s = duration_s
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._phase = "idle"
        self._deadline: float | None = None
        self._run_id: str | None = None
        self._result: dict | None = None
        self._error: str | None = None

    def snapshot(self) -> dict:
        with self._lock:
            remaining = (
                max(0, math.ceil(self._deadline - time.monotonic()))
                if self._deadline is not None and self._phase in ("countdown", "running")
                else 0
            )
            return {
                "phase": self._phase,
                "run_id": self._run_id,
                "remaining_s": remaining,
                "countdown_s": self._countdown_s,
                "duration_s": self._duration_s,
                "result": self._result,
                "error": self._error,
            }

    def start(self) -> dict:
        with self._lock:
            if self._phase in ("countdown", "running"):
                raise RuntimeError("a person pose test is already running")
            self._stop = threading.Event()
            self._phase = "countdown"
            self._deadline = time.monotonic() + self._countdown_s
            self._run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:8]
            self._result = None
            self._error = None
            self._thread = threading.Thread(target=self._run, args=(self._run_id, self._stop), daemon=True)
            self._thread.start()
        return self.snapshot()

    def _run(self, run_id: str, stop: threading.Event) -> None:
        if stop.wait(self._countdown_s):
            return
        with self._lock:
            self._phase = "running"
            self._deadline = time.monotonic() + self._duration_s
        started_utc = _utc_now()
        try:
            capture_result = self._capture(self._duration_s, stop)
            if stop.is_set():
                return
            result = {
                "schema_version": 1,
                "kind": "person_pose_quality_research",
                "run_id": run_id,
                "status": "complete",
                "started_utc": started_utc,
                "completed_utc": _utc_now(),
                "duration_requested_s": self._duration_s,
                **{
                    field: capture_result[field]
                    for field in _CAPTURE_SUMMARY_FIELDS
                    if field in capture_result
                },
            }
        except Exception as exc:
            result = {
                "schema_version": 1,
                "kind": "person_pose_quality_research",
                "run_id": run_id,
                "status": "failed",
                "started_utc": started_utc,
                "completed_utc": _utc_now(),
                "duration_requested_s": self._duration_s,
                "error": type(exc).__name__,
            }
        try:
            self._save(result)
        except OSError:
            with self._lock:
                self._phase = "failed"
                self._deadline = None
                self._error = "result_save_failed"
            return
        with self._lock:
            self._phase = result["status"]
            self._deadline = None
            self._result = result
            self._error = result.get("error")

    def _save(self, result: dict) -> None:
        self._result_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        payload = (json.dumps(result, indent=2, sort_keys=True) + "\n").encode("utf-8")
        temporary_name: str | None = None
        try:
            with tempfile.NamedTemporaryFile(dir=self._result_dir, prefix=".person-test-", delete=False) as temporary:
                temporary_name = temporary.name
                temporary.write(payload)
                temporary.flush()
                os.fsync(temporary.fileno())
            os.replace(temporary_name, self._result_dir / f"{result['run_id']}.json")
        finally:
            if temporary_name is not None and os.path.exists(temporary_name):
                os.unlink(temporary_name)

    def latest(self) -> dict | None:
        paths = sorted(self._result_dir.glob("*.json")) if self._result_dir.is_dir() else []
        if not paths:
            return None
        return json.loads(paths[-1].read_text(encoding="utf-8"))

    def close(self) -> None:
        self._stop.set()
        thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=5)


def make_handler(controller: PersonPoseTestController, static_dir: Path, *, allowed_origin: str):
    """Serve the existing UI plus a narrow, same-origin research test endpoint."""

    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(static_dir), **kwargs)

        def _send_json(self, status: int, payload: dict) -> None:
            data = json.dumps(payload, separators=(",", ":")).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self) -> None:
            route = urlsplit(self.path).path
            if route == "/api/research/person-pose-test":
                self._send_json(200, controller.snapshot())
            elif route == "/api/research/person-pose-test/latest":
                latest = controller.latest()
                self._send_json(200 if latest is not None else 404, latest or {"error": "no_result"})
            else:
                super().do_GET()

        def do_POST(self) -> None:
            if urlsplit(self.path).path != "/api/research/person-pose-test":
                self._send_json(404, {"error": "not_found"})
                return
            if (
                self.headers.get("Origin") != allowed_origin
                or self.headers.get("X-DS-Person-Test") != "1"
            ):
                self._send_json(403, {"error": "origin_denied"})
                return
            if self.headers.get("Content-Length", "0") != "0":
                self._send_json(400, {"error": "body_not_allowed"})
                return
            try:
                state = controller.start()
            except RuntimeError:
                self._send_json(409, {"error": "test_already_running"})
                return
            self._send_json(202, state)

    return Handler


def capture_real_pose(duration_s: int, stop_event: threading.Event, *, extra_site_packages: str) -> dict:
    """Use the canonical real Picamera2/MediaPipe worker; retain counters only."""
    site.addsitedir(extra_site_packages)
    from digital_spotter.contracts import MonotonicNanoseconds, new_event_id
    from digital_spotter.vision import (
        MediaPipePoseAdapter,
        MediaPipePoseConfig,
        Picamera2FrameSource,
        Picamera2SourceConfig,
        VisionWorker,
        VisionWorkerConfig,
    )

    class Clock:
        def now_ns(self) -> MonotonicNanoseconds:
            return MonotonicNanoseconds(time.monotonic_ns())

    class TimedSource:
        mode = "picamera2"
        is_real = True
        is_simulated = False

        def __init__(self) -> None:
            self.source = Picamera2FrameSource(Picamera2SourceConfig(encode_h264=False))
            self.started: float | None = None
            self.ended: float | None = None

        @property
        def exhausted(self) -> bool:
            return stop_event.is_set() or (
                self.started is not None and time.monotonic() - self.started >= duration_s
            )

        def start(self) -> None:
            self.source.start()
            self.started = time.monotonic()

        def read(self, timeout_s: float):
            if self.exhausted:
                return None
            assert self.started is not None
            remaining = duration_s - (time.monotonic() - self.started)
            return self.source.read(min(timeout_s, max(0.05, remaining)))

        def stop(self) -> None:
            self.ended = time.monotonic()
            self.source.stop()

    class CounterSink:
        def __init__(self) -> None:
            self.good = 0
            self.last_capture_ns: int | None = None
            self.capture_timestamps_strictly_monotonic = True

        def publish(self, event) -> None:
            if event.quality.value == "good":
                self.good += 1
            capture_ns = int(event.payload.captured_monotonic_ns)
            if self.last_capture_ns is not None and capture_ns <= self.last_capture_ns:
                self.capture_timestamps_strictly_monotonic = False
            self.last_capture_ns = capture_ns

    source = TimedSource()
    sink = CounterSink()
    worker = VisionWorker(
        config=VisionWorkerConfig(camera_id="picamera2-imx219", minimum_confidence=0.7),
        source=source,
        evaluator=MediaPipePoseAdapter(MediaPipePoseConfig(model_complexity=1)),
        sink=sink,
        clock=Clock(),
        event_id_factory=new_event_id,
    )
    summary = worker.run()
    return {
        "hardware_simulated": False,
        "camera": "imx219",
        "pose_evaluator": "mediapipe",
        "duration_observed_s": round((source.ended or time.monotonic()) - (source.started or time.monotonic()), 3),
        "frames_received": summary.frames_received,
        "good_pose_frames": sink.good,
        "poses_not_found": summary.poses_not_found,
        "poses_low_visibility": summary.poses_low_visibility,
        "processing_failures": summary.processing_failures,
        "read_timeouts": summary.read_timeouts,
        "source_frames_dropped": summary.source_frames_dropped,
        "capture_timestamps_strictly_monotonic": sink.capture_timestamps_strictly_monotonic,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8766)
    parser.add_argument("--allowed-origin", default="http://127.0.0.1:4174")
    parser.add_argument("--extra-site-packages", default="/usr/lib/python3/dist-packages")
    parser.add_argument("--result-dir", type=Path, required=True)
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("port must be 1..65535")
    if not args.allowed_origin.startswith("http://127.0.0.1:"):
        parser.error("allowed origin must be a loopback HTTP origin")
    static_dir = Path(__file__).resolve().parents[1] / "src/digital_spotter/web/static"
    if not (static_dir / "ui-preview/index.html").is_file():
        parser.error("research UI assets are missing")
    controller = PersonPoseTestController(
        capture=partial(capture_real_pose, extra_site_packages=args.extra_site_packages),
        result_dir=args.result_dir,
    )
    server = ThreadingHTTPServer(
        ("127.0.0.1", args.port),
        make_handler(controller, static_dir, allowed_origin=args.allowed_origin),
    )
    stop = threading.Event()
    for signum in (signal.SIGINT, signal.SIGTERM):
        signal.signal(signum, lambda _signum, _frame: stop.set())
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    print(f"Person pose test UI: http://127.0.0.1:{args.port}/ui-preview/", flush=True)
    try:
        stop.wait()
    finally:
        server.shutdown()
        server.server_close()
        controller.close()
        thread.join(timeout=2)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
