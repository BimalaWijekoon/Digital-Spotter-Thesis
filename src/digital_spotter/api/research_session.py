"""Loopback-only read endpoint for unscored research session status."""

from __future__ import annotations

import json
import threading
import time
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlsplit

from digital_spotter.core.research_status import (
    IMU_WINDOW_SAMPLES, IMU_WINDOW_VERSION, STATUS_VERSION, UNVERIFIED_V5_REASON,
)


class ResearchStatusHub:
    """Publish immutable snapshots across the core-loop and HTTP threads."""

    def __init__(self, *, clock_ns=time.monotonic_ns, max_age_ns: int = 3_000_000_000) -> None:
        if max_age_ns <= 0:
            raise ValueError("status max age must be positive")
        self._clock_ns = clock_ns
        self._max_age_ns = max_age_ns
        self._lock = threading.Lock()
        self._snapshot: bytes | None = None
        self._imu_snapshot: bytes | None = None
        self._published_ns: int | None = None
        self._imu_published_ns: int | None = None

    def publish(self, status: dict[str, object]) -> None:
        if set(status) != {"version", "session", "wearable", "camera", "analysis", "latest_rep"}:
            raise ValueError("research status has unsupported fields")
        if not isinstance(status.get("session"), dict) or set(status["session"]) != {
            "state", "rep_count",
        }:
            raise ValueError("research session status is invalid")
        for name in ("wearable", "camera"):
            if not isinstance(status.get(name), dict) or set(status[name]) != {"state"}:
                raise ValueError("research sensor status is invalid")
        latest_rep = status.get("latest_rep")
        if latest_rep is not None and (
            not isinstance(latest_rep, dict) or set(latest_rep) != {"number", "quality"}
        ):
            raise ValueError("research rep status is invalid")
        if status.get("version") != STATUS_VERSION or status.get("analysis") != {
            "state": "unavailable", "reason": UNVERIFIED_V5_REASON,
        }:
            raise ValueError("research status cannot publish a scored analysis")
        encoded = json.dumps(status, separators=(",", ":"), allow_nan=False).encode("utf-8")
        if len(encoded) > 4096:
            raise ValueError("research status is too large")
        with self._lock:
            self._snapshot = encoded
            self._published_ns = self._clock_ns()

    def snapshot(self) -> bytes | None:
        with self._lock:
            if self._published_ns is None:
                return None
            if self._clock_ns() - self._published_ns > self._max_age_ns:
                return None
            return self._snapshot

    def publish_imu_window(self, window: dict[str, object]) -> None:
        samples = window.get("samples")
        if (set(window) != {"version", "state", "samples"}
                or window.get("version") != IMU_WINDOW_VERSION
                or window.get("state") not in {"receiving", "degraded", "stale", "unavailable"}
                or not isinstance(samples, list) or len(samples) > IMU_WINDOW_SAMPLES):
            raise ValueError("invalid research IMU window")
        for sample in samples:
            if (not isinstance(sample, dict)
                    or set(sample) != {"sequence", "t_ms", "acceleration_m_s2", "angular_velocity_rad_s"}
                    or not isinstance(sample["sequence"], int)
                    or not isinstance(sample["t_ms"], (int, float))):
                raise ValueError("invalid research IMU sample")
            for field in ("acceleration_m_s2", "angular_velocity_rad_s"):
                vector = sample[field]
                if not isinstance(vector, list) or len(vector) != 3 or any(
                    not isinstance(value, (int, float)) for value in vector
                ):
                    raise ValueError("invalid research IMU vector")
        encoded = json.dumps(window, separators=(",", ":"), allow_nan=False).encode("utf-8")
        if len(encoded) > 20_000:
            raise ValueError("research IMU window is too large")
        with self._lock:
            self._imu_snapshot = encoded
            self._imu_published_ns = self._clock_ns()

    def imu_snapshot(self) -> bytes | None:
        with self._lock:
            if self._imu_published_ns is None or self._clock_ns() - self._imu_published_ns > self._max_age_ns:
                return None
            return self._imu_snapshot


def status_handler_class(hub: ResearchStatusHub, static_dir: Path):
    """Serve the existing UI and exactly one same-origin read-only API route."""
    static_dir = static_dir.resolve(strict=True)

    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(static_dir), **kwargs)

        def _json(self, status: HTTPStatus, encoded: bytes) -> None:
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def do_GET(self) -> None:
            path = urlsplit(self.path).path
            if path == "/api/research/session-status":
                status = hub.snapshot()
                if status is None:
                    self._json(HTTPStatus.SERVICE_UNAVAILABLE, b'{"error":"status_unavailable"}')
                else:
                    self._json(HTTPStatus.OK, status)
                return
            if path == "/api/research/imu-window":
                window = hub.imu_snapshot()
                if window is None:
                    self._json(HTTPStatus.SERVICE_UNAVAILABLE, b'{"error":"imu_unavailable"}')
                else:
                    self._json(HTTPStatus.OK, window)
                return
            if path.startswith("/api/"):
                self._json(HTTPStatus.NOT_FOUND, b'{"error":"not_found"}')
                return
            super().do_GET()

        def log_message(self, _format: str, *_args: object) -> None:
            # The browser polls once a second; routine status reads need no log line.
            return

    return Handler
