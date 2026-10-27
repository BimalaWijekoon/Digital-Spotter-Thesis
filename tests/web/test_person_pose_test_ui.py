"""Focused contract checks for the local, summary-only person pose test."""

from __future__ import annotations

import json
import time
from http.server import ThreadingHTTPServer
from threading import Thread
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from scripts.run_person_pose_test_ui import PersonPoseTestController, make_handler


def _wait_for_completion(controller: PersonPoseTestController) -> dict:
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        state = controller.snapshot()
        if state["phase"] in ("complete", "failed"):
            return state
        time.sleep(0.01)
    raise AssertionError("person pose test did not complete")


def test_countdown_then_30_second_contract_saves_summary_only(tmp_path):
    calls = []

    def capture(duration_s, stop_event):
        calls.append(duration_s)
        assert not stop_event.is_set()
        return {
            "hardware_simulated": False,
            "frames_received": 12,
            "good_pose_frames": 8,
            "poses_not_found": 4,
            "poses_low_visibility": 0,
            "landmarks": [{"x": 0.5, "y": 0.5}],
            "video": "must-not-be-saved",
        }

    controller = PersonPoseTestController(
        capture=capture,
        result_dir=tmp_path,
        countdown_s=0.03,
        duration_s=30,
    )
    try:
        assert controller.start()["phase"] == "countdown"
        state = _wait_for_completion(controller)
        assert state["phase"] == "complete"
        assert calls == [30]
        assert state["result"]["good_pose_frames"] == 8
        saved = list(tmp_path.glob("*.json"))
        assert len(saved) == 1
        assert json.loads(saved[0].read_text()) == state["result"]
        assert "landmarks" not in saved[0].read_text()
        assert "video" not in saved[0].read_text()
    finally:
        controller.close()


def test_loopback_http_rejects_other_origins_and_parallel_starts(tmp_path):
    static_dir = tmp_path / "static"
    static_dir.mkdir()
    (static_dir / "index.html").write_text("test UI")
    controller = PersonPoseTestController(
        capture=lambda duration_s, stop_event: {"frames_received": 1, "good_pose_frames": 1},
        result_dir=tmp_path / "results",
        countdown_s=0.1,
        duration_s=30,
    )
    server = ThreadingHTTPServer(
        ("127.0.0.1", 0),
        make_handler(controller, static_dir, allowed_origin="http://127.0.0.1:4174"),
    )
    thread = Thread(target=server.serve_forever)
    thread.start()
    url = f"http://127.0.0.1:{server.server_port}/api/research/person-pose-test"

    def start(origin):
        return urlopen(Request(
            url,
            data=b"",
            method="POST",
            headers={"Origin": origin, "X-DS-Person-Test": "1"},
        ), timeout=2)

    try:
        with urlopen(f"http://127.0.0.1:{server.server_port}/index.html", timeout=2) as response:
            assert response.read() == b"test UI"
        try:
            start("https://unrelated.example")
        except HTTPError as error:
            assert error.code == 403
        else:
            raise AssertionError("cross-origin test start was accepted")
        with start("http://127.0.0.1:4174") as response:
            assert response.status == 202
            assert json.load(response)["phase"] == "countdown"
        try:
            start("http://127.0.0.1:4174")
        except HTTPError as error:
            assert error.code == 409
        else:
            raise AssertionError("parallel test start was accepted")
        assert _wait_for_completion(controller)["phase"] == "complete"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
        controller.close()
