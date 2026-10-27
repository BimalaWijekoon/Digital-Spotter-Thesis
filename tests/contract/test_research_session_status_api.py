"""The research HTTP boundary serves only local, unscored session status."""

from __future__ import annotations

import json
import threading
from http.server import ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import urlopen

from digital_spotter.api.research_session import ResearchStatusHub, status_handler_class


def test_status_route_fails_closed_then_serves_unscored_projection(tmp_path):
    (tmp_path / "index.html").write_text("<!doctype html><title>Research</title>")
    clock = [1_000_000_000]
    hub = ResearchStatusHub(clock_ns=lambda: clock[0])
    server = ThreadingHTTPServer(("127.0.0.1", 0), status_handler_class(hub, tmp_path))
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    url = f"http://127.0.0.1:{server.server_port}/api/research/session-status"
    imu_url = f"http://127.0.0.1:{server.server_port}/api/research/imu-window"
    try:
        try:
            urlopen(url, timeout=2)
        except HTTPError as exc:
            assert exc.code == 503
            assert json.load(exc)["error"] == "status_unavailable"
        else:
            raise AssertionError("missing status must not return a success")

        try:
            urlopen(imu_url, timeout=2)
        except HTTPError as exc:
            assert exc.code == 503
        else:
            raise AssertionError("missing IMU window must not return a success")

        hub.publish({
            "version": "research_status_v1",
            "session": {"state": "active", "rep_count": 1},
            "wearable": {"state": "degraded"},
            "camera": {"state": "receiving"},
            "analysis": {
                "state": "unavailable",
                "reason": "v5_live_feature_contract_unverified",
            },
            "latest_rep": {"number": 1, "quality": "unavailable"},
        })
        with urlopen(url, timeout=2) as response:
            assert response.headers["Cache-Control"] == "no-store"
            status = json.load(response)
        assert status["session"]["rep_count"] == 1
        assert status["analysis"]["state"] == "unavailable"
        assert "probability" not in str(status)

        hub.publish_imu_window({
            "version": "research_imu_window_v1", "state": "degraded",
            "samples": [{
                "sequence": 1, "t_ms": 0.0,
                "acceleration_m_s2": [1.0, 2.0, 3.0],
                "angular_velocity_rad_s": [0.1, 0.2, 0.3],
            }],
        })
        with urlopen(imu_url, timeout=2) as response:
            assert response.headers["Cache-Control"] == "no-store"
            assert json.load(response)["samples"][0]["acceleration_m_s2"] == [1.0, 2.0, 3.0]

        unsafe = dict(status, raw_probability=0.9)
        try:
            hub.publish(unsafe)
        except ValueError:
            pass
        else:
            raise AssertionError("a probability must not enter research status")

        clock[0] += 3_000_000_001
        try:
            urlopen(url, timeout=2)
        except HTTPError as exc:
            assert exc.code == 503
        else:
            raise AssertionError("stale status must not be displayed as live")

        try:
            urlopen(f"http://127.0.0.1:{server.server_port}/api/other", timeout=2)
        except HTTPError as exc:
            assert exc.code == 404
        else:
            raise AssertionError("unknown research API route must not be served")
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=2)
