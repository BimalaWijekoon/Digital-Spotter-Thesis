from __future__ import annotations

import os
import socket
import struct
import threading
from pathlib import Path
from types import SimpleNamespace

import msgpack
import pytest

from digital_spotter.config import AdapterMode, ProductSettings, VisionPipeline
from digital_spotter.contracts import (
    EventEnvelope,
    HealthState,
    MonotonicNanoseconds,
    PoseLandmark,
    PoseSample,
    new_event_id,
)
from digital_spotter.core import load_replay_fixture
from digital_spotter.imu.uds import decode_event_frame
from digital_spotter.vision import (
    BoundedVisionEventPublisher,
    PoseEvaluation,
    ReplayFrameSource,
    ReplayPoseEvaluator,
    UnixVisionEventTransport,
    VisionWorker,
    VisionWorkerConfig,
)
from digital_spotter.vision import runtime as vision_runtime
from digital_spotter.vision.runtime import VisionAgentRuntime


FIXTURES = Path(__file__).parents[1] / "fixtures" / "replay" / "v1"


class _FakePublisher:
    def __init__(self) -> None:
        self.started = False
        self.closed_with: float | None = None

    def start(self) -> None:
        self.started = True

    def close(self, *, timeout_s: float = 1.0) -> None:
        self.closed_with = timeout_s


class _FakeWorker:
    def __init__(self, result=None, failure: Exception | None = None) -> None:
        self.result = result
        self.failure = failure
        self.run_calls = 0
        self.stop_calls = 0

    def run(self):
        self.run_calls += 1
        if self.failure is not None:
            raise self.failure
        return self.result

    def stop(self) -> None:
        self.stop_calls += 1


class _SequenceClock:
    def __init__(self, values: tuple[int, ...]) -> None:
        self._values = iter(values)

    def now_ns(self) -> MonotonicNanoseconds:
        return MonotonicNanoseconds(next(self._values))


def _event_ids():
    sequence = iter(range(300, 400))
    return lambda: new_event_id(
        unix_time_ms=1_750_000_000_000,
        random_bits=next(sequence),
    )


def _evaluations() -> tuple[PoseEvaluation, ...]:
    good = PoseEvaluation(
        found=True,
        landmarks=(PoseLandmark(x=0.5, y=0.5, z=0.0, visibility=0.95),),
        angles={},
        confidence=0.95,
    )
    missing = PoseEvaluation(found=False, landmarks=(), angles={}, confidence=0.0)
    low = PoseEvaluation(
        found=True,
        landmarks=(PoseLandmark(x=0.4, y=0.6, z=0.0, visibility=0.2),),
        angles={},
        confidence=0.2,
    )
    return good, missing, low


def _receive_exact(connection: socket.socket, size: int) -> bytes | None:
    data = bytearray()
    while len(data) < size:
        part = connection.recv(size - len(data))
        if not part:
            return None if not data else bytes(data)
        data.extend(part)
    return bytes(data)


def _collect_frames(server: socket.socket, frames: list[bytes]) -> None:
    connection, _ = server.accept()
    with connection:
        while True:
            prefix = _receive_exact(connection, 4)
            if prefix is None:
                return
            if len(prefix) != 4:
                raise AssertionError("runtime closed during a frame prefix")
            length = struct.unpack(">I", prefix)[0]
            payload = _receive_exact(connection, length)
            if payload is None or len(payload) != length:
                raise AssertionError("runtime closed during a frame payload")
            frames.append(prefix + payload)


def _summary():
    return SimpleNamespace(
        state=SimpleNamespace(value="stopped"),
        adapter_mode="fake-source",
        pose_evaluator_mode="fake-pose",
        is_simulated=False,
        frames_received=2,
        events_published=2,
        source_frames_dropped=0,
        poses_not_found=0,
        poses_low_visibility=0,
        read_timeouts=0,
        processing_failures=0,
        health_events_published=3,
        health_publish_failures=0,
        last_failure_reason=None,
    )


def test_runtime_owns_publisher_worker_and_bounded_cleanup():
    publisher = _FakePublisher()
    worker = _FakeWorker(result="done")
    runtime = VisionAgentRuntime(
        worker=worker,
        publisher=publisher,
        close_timeout_s=1.5,
    )

    assert runtime.run() == "done"
    assert publisher.started is True
    assert publisher.closed_with == 1.5
    assert worker.run_calls == 1
    runtime.stop()
    assert worker.stop_calls == 1

    with pytest.raises(RuntimeError, match="only once"):
        runtime.run()


def test_runtime_closes_publisher_without_masking_worker_failure():
    publisher = _FakePublisher()
    worker = _FakeWorker(failure=RuntimeError("injected worker failure"))
    runtime = VisionAgentRuntime(worker=worker, publisher=publisher)

    with pytest.raises(RuntimeError, match="injected worker failure"):
        runtime.run()

    assert publisher.closed_with == 2.0


def test_default_legacy_switch_cannot_start_canonical_agent(monkeypatch, capsys):
    monkeypatch.setattr(
        vision_runtime,
        "load_settings",
        lambda _path: ProductSettings(),
    )
    monkeypatch.setattr(
        vision_runtime,
        "build_real_vision_runtime",
        lambda **_kwargs: pytest.fail("canonical runtime must remain disabled"),
    )

    result = vision_runtime.main(
        ["--camera-id", "picam0", "--camera-python", "/usr/bin/python3"]
    )

    assert result == 3
    assert "legacy migration path remains active" in capsys.readouterr().err


def test_explicit_canonical_switch_assembles_and_runs_agent(monkeypatch, capsys):
    settings = ProductSettings(
        vision_pipeline=VisionPipeline.CANONICAL,
        vision_adapter=AdapterMode.REAL,
    )
    fake_runtime = _FakeWorker(result=_summary())
    captured = {}

    def build_runtime(*, settings, config):
        captured["settings"] = settings
        captured["config"] = config
        return fake_runtime

    monkeypatch.setattr(vision_runtime, "load_settings", lambda _path: settings)
    monkeypatch.setattr(vision_runtime, "build_real_vision_runtime", build_runtime)
    monkeypatch.setattr(vision_runtime, "_install_signal_handlers", lambda _runtime: None)

    result = vision_runtime.main(
        [
            "--camera-id",
            "picam0",
            "--camera-python",
            "/usr/bin/python3",
            "--core-uid",
            str(os.getuid()),
        ]
    )

    assert result == 0
    assert captured["settings"] is settings
    assert captured["config"].socket_path == Path("run/vision-events.sock")
    assert captured["config"].allowed_peer_uids == frozenset({os.getuid()})
    assert '"state": "stopped"' in capsys.readouterr().out


def test_canonical_runtime_uses_typed_video_publish_url(monkeypatch):
    settings = ProductSettings(
        vision_pipeline=VisionPipeline.CANONICAL,
        vision_adapter=AdapterMode.REAL,
        video_publish_url="rtsp://127.0.0.1:8554/picamera2",
    )
    fake_runtime = _FakeWorker(result=_summary())
    captured = {}

    def build_runtime(*, settings, config):
        captured["config"] = config
        return fake_runtime

    monkeypatch.setattr(vision_runtime, "load_settings", lambda _path: settings)
    monkeypatch.setattr(vision_runtime, "build_real_vision_runtime", build_runtime)
    monkeypatch.setattr(vision_runtime, "_install_signal_handlers", lambda _runtime: None)

    assert vision_runtime.main(
        ["--camera-id", "picam0", "--camera-python", "/usr/bin/python3"]
    ) == 0
    assert captured["config"].publish_url == settings.video_publish_url


def test_replay_worker_runtime_delivers_pose_and_health_before_bounded_close(tmp_path):
    socket_path = tmp_path / "vision-events.sock"
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(str(socket_path))
    os.chmod(socket_path, 0o600)
    server.listen(1)
    frames: list[bytes] = []
    collector = threading.Thread(
        target=_collect_frames,
        args=(server, frames),
        daemon=True,
    )
    collector.start()

    publisher = BoundedVisionEventPublisher(
        transport=UnixVisionEventTransport(
            socket_path,
            allowed_peer_uids=frozenset({os.getuid()}),
        ),
        queue_size=16,
        reconnect_backoff_s=(0.0,),
    )
    fixture = load_replay_fixture(FIXTURES / "synthetic_normal_rep.json")
    worker = VisionWorker(
        config=VisionWorkerConfig(camera_id="runtime-replay-camera"),
        source=ReplayFrameSource(
            video_path=FIXTURES / fixture.video.path,
            captured_monotonic_ns=tuple(fixture.video.captured_monotonic_ns),
        ),
        evaluator=ReplayPoseEvaluator(_evaluations()),
        sink=publisher,
        health_sink=publisher,
        clock=_SequenceClock(
            (900_000, 950_000, 1_020_000, 1_040_000, 1_060_000, 1_070_000)
        ),
        event_id_factory=_event_ids(),
    )
    runtime = VisionAgentRuntime(worker=worker, publisher=publisher)

    try:
        summary = runtime.run()
        collector.join(timeout=2.0)
    finally:
        server.close()

    assert collector.is_alive() is False
    event_types = [
        msgpack.unpackb(frame[4:], raw=False)["event_type"] for frame in frames
    ]
    assert event_types.count("pose_sample") == 3
    assert event_types.count("health_state") == 5
    pose_frames = [
        frame for frame, event_type in zip(frames, event_types)
        if event_type == "pose_sample"
    ]
    health_frames = [
        frame for frame, event_type in zip(frames, event_types)
        if event_type == "health_state"
    ]
    assert all(
        decode_event_frame(frame, EventEnvelope[PoseSample]).payload.camera_id
        == "runtime-replay-camera"
        for frame in pose_frames
    )
    assert decode_event_frame(
        health_frames[-1], EventEnvelope[HealthState]
    ).payload.state.value == "stopping"
    assert summary.events_published == 3
    assert publisher.counters().events_sent == 8
    assert publisher.counters().queue_drops == 0
    assert publisher.counters().transport_drops == 0
