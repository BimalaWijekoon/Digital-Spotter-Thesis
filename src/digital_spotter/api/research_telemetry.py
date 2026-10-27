"""Temporary loopback-only pose/clock bridge for the M3-04 research viewer.

This is not the authenticated product API. It accepts the canonical vision
worker's bounded Unix frames and publishes only a browser-safe projection.
"""

from __future__ import annotations

import json
import os
import signal
import socket
import stat
import struct
import threading
import time
from collections import deque
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from pydantic import ValidationError

from digital_spotter.api.video import (
    BrowserClockRequest,
    browser_clock_response,
    pose_event_for_browser,
)
from digital_spotter.contracts import EventEnvelope, MAX_EVENT_BYTES, PoseSample
from digital_spotter.imu.uds import UDSFrameError, decode_event_frame


class ResearchPoseHub:
    """Drop old telemetry before it can create browser-side lag."""

    def __init__(self, *, capacity: int = 120) -> None:
        if not 1 <= capacity <= 120:
            raise ValueError("research pose capacity must be 1..120")
        self._events: deque[tuple[int, dict]] = deque(maxlen=capacity)
        self._cursor = 0
        self._lock = threading.Lock()

    def ingest_frame(self, frame: bytes) -> bool:
        """Ignore non-pose health frames; reject malformed or simulated claims."""
        try:
            event = decode_event_frame(frame, EventEnvelope[PoseSample])
            projected = pose_event_for_browser(event).model_dump(mode="json")
        except (UDSFrameError, ValueError):
            return False
        with self._lock:
            self._cursor += 1
            self._events.append((self._cursor, projected))
        return True

    def snapshot(self, *, after: int) -> dict[str, object]:
        if type(after) is not int or after < 0:
            raise ValueError("pose cursor must be a non-negative integer")
        with self._lock:
            return {
                "cursor": self._cursor,
                "events": [event for cursor, event in self._events if cursor > after],
            }


def _handler_class(hub: ResearchPoseHub, static_dir: Path):
    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(static_dir), **kwargs)

        def _json(self, status: HTTPStatus, payload: dict) -> None:
            encoded = json.dumps(payload, separators=(",", ":")).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(encoded)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(encoded)

        def do_GET(self) -> None:
            parsed = urlsplit(self.path)
            if parsed.path == "/api/pose-events":
                try:
                    params = parse_qs(parsed.query, strict_parsing=True)
                    if set(params) != {"after"} or len(params["after"]) != 1:
                        raise ValueError("invalid cursor query")
                    cursor = int(params["after"][0])
                    self._json(HTTPStatus.OK, hub.snapshot(after=cursor))
                except (ValueError, OverflowError):
                    self._json(HTTPStatus.BAD_REQUEST, {"error": "invalid_cursor"})
                return
            if parsed.path.startswith("/api/"):
                self._json(HTTPStatus.NOT_FOUND, {"error": "not_found"})
                return
            super().do_GET()

        def do_POST(self) -> None:
            if urlsplit(self.path).path != "/api/clock-sync":
                self._json(HTTPStatus.NOT_FOUND, {"error": "not_found"})
                return
            expected_origin = f"http://127.0.0.1:{self.server.server_port}"
            if self.headers.get("Origin") != expected_origin:
                self._json(HTTPStatus.FORBIDDEN, {"error": "invalid_origin"})
                return
            received_ns = time.monotonic_ns()
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 1 <= length <= 1024:
                    raise ValueError("invalid request length")
                request = BrowserClockRequest.model_validate_json(self.rfile.read(length))
                response = browser_clock_response(
                    request,
                    server_received_monotonic_ns=received_ns,
                    server_sent_monotonic_ns=time.monotonic_ns(),
                )
            except (ValueError, ValidationError):
                self._json(HTTPStatus.BAD_REQUEST, {"error": "invalid_clock_request"})
                return
            self._json(HTTPStatus.OK, response.model_dump(mode="json"))

    return Handler


def _read_exact(connection: socket.socket, count: int, stop: threading.Event) -> bytes | None:
    chunks = bytearray()
    while len(chunks) < count and not stop.is_set():
        try:
            chunk = connection.recv(count - len(chunks))
        except socket.timeout:
            continue
        if not chunk:
            return None
        chunks.extend(chunk)
    return bytes(chunks) if len(chunks) == count else None


def _receive_vision(listener: socket.socket, hub: ResearchPoseHub, stop: threading.Event) -> None:
    listener.settimeout(0.2)
    while not stop.is_set():
        try:
            connection, _ = listener.accept()
        except socket.timeout:
            continue
        with connection:
            connection.settimeout(0.2)
            while not stop.is_set():
                prefix = _read_exact(connection, 4, stop)
                if prefix is None:
                    break
                length = struct.unpack(">I", prefix)[0]
                if not 1 <= length <= MAX_EVENT_BYTES:
                    break
                payload = _read_exact(connection, length, stop)
                if payload is None:
                    break
                hub.ingest_frame(prefix + payload)


def run_research_bridge(*, static_dir: Path, socket_path: Path, port: int = 8765) -> None:
    """Serve one bounded diagnostic run; never bind beyond Pi loopback."""
    static_dir = static_dir.resolve(strict=True)
    if not static_dir.is_dir() or not (static_dir / "research-preview.html").is_file():
        raise ValueError("research static directory is invalid")
    if not 1 <= port <= 65535:
        raise ValueError("research HTTP port is invalid")
    socket_path = socket_path.resolve(strict=False)
    if socket_path.exists() or socket_path.is_symlink():
        raise FileExistsError("research vision socket already exists")
    if not socket_path.parent.is_dir():
        raise ValueError("research vision socket parent must exist")
    hub = ResearchPoseHub()
    stop = threading.Event()
    def _stop_on_term(_signum, _frame):
        raise KeyboardInterrupt

    previous_term = signal.signal(signal.SIGTERM, _stop_on_term)
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as listener:
            listener.bind(str(socket_path))
            os.chmod(socket_path, 0o600)
            owned_inode = socket_path.stat().st_ino
            try:
                listener.listen(1)
                receiver = threading.Thread(
                    target=_receive_vision, args=(listener, hub, stop), daemon=True,
                    name="research-pose-uds",
                )
                receiver.start()
                with ThreadingHTTPServer(("127.0.0.1", port), _handler_class(hub, static_dir)) as server:
                    server.daemon_threads = True
                    try:
                        server.serve_forever(poll_interval=0.2)
                    finally:
                        stop.set()
                        receiver.join(timeout=1.0)
            finally:
                stop.set()
                metadata = socket_path.lstat() if socket_path.exists() else None
                if metadata and stat.S_ISSOCK(metadata.st_mode) and metadata.st_ino == owned_inode:
                    socket_path.unlink()
    except KeyboardInterrupt:
        pass
    finally:
        signal.signal(signal.SIGTERM, previous_term)
