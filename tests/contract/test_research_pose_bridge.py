"""One bounded local HTTP contract check for the private research bridge."""

from __future__ import annotations

import json
import signal
import socket
import subprocess
import sys
import threading
import time
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer

from digital_spotter.api.research_telemetry import ResearchPoseHub, _handler_class


def test_loopback_bridge_serves_clock_and_pose_without_cross_origin_posts(tmp_path):
    hub = ResearchPoseHub()
    static_dir = tmp_path / "static"
    static_dir.mkdir()
    (static_dir / "research-preview.html").write_text("<!doctype html><title>test</title>")
    server = ThreadingHTTPServer(("127.0.0.1", 0), _handler_class(hub, static_dir))
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    connection = HTTPConnection("127.0.0.1", server.server_port, timeout=2)
    request = {"schema_version": 1, "message_type": "clock_sync_request",
               "request_id": "test-1", "client_sent_ms": 1_000.0}
    try:
        connection.request("GET", "/api/pose-events?after=0")
        response = connection.getresponse()
        assert response.status == 200
        assert json.loads(response.read()) == {"cursor": 0, "events": []}

        body = json.dumps(request)
        connection.request("POST", "/api/clock-sync", body=body,
                           headers={"Origin": "http://evil.test", "Content-Type": "application/json"})
        response = connection.getresponse()
        assert response.status == 403
        response.read()

        connection.request("POST", "/api/clock-sync", body=body,
                           headers={"Origin": f"http://127.0.0.1:{server.server_port}",
                                    "Content-Type": "application/json"})
        response = connection.getresponse()
        assert response.status == 200
        clock = json.loads(response.read())
        assert clock["request_id"] == "test-1"
        assert clock["client_sent_ms"] == 1_000.0
        assert clock["server_sent_monotonic_us"] >= clock["server_received_monotonic_us"]
    finally:
        connection.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_term_cleans_only_its_own_temporary_vision_socket(tmp_path):
    static_dir = tmp_path / "static"
    static_dir.mkdir()
    (static_dir / "research-preview.html").write_text("<!doctype html><title>test</title>")
    socket_path = tmp_path / "vision-events.sock"
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as reservation:
        reservation.bind(("127.0.0.1", 0))
        port = reservation.getsockname()[1]
    script = (
        "from pathlib import Path; "
        "from digital_spotter.api.research_telemetry import run_research_bridge; "
        f"run_research_bridge(static_dir=Path({str(static_dir)!r}), "
        f"socket_path=Path({str(socket_path)!r}), port={port})"
    )
    process = subprocess.Popen([sys.executable, "-c", script])
    try:
        deadline = time.monotonic() + 5
        while not socket_path.exists() and process.poll() is None and time.monotonic() < deadline:
            time.sleep(0.02)
        assert socket_path.exists(), "bridge did not start"
        process.send_signal(signal.SIGTERM)
        assert process.wait(timeout=3) == 0
        assert not socket_path.exists()
    finally:
        if process.poll() is None:
            process.terminate()
            process.wait(timeout=3)
