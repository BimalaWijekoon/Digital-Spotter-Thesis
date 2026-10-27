from __future__ import annotations

import socket
import tempfile
from types import SimpleNamespace

import pytest

from digital_spotter.contracts import ReasonCode
from digital_spotter.vision import (
    CameraFrame,
    CameraProtocolError,
    CameraUnavailableError,
    CaptureTimestamp,
    CaptureTimestampSource,
    MediaPipePoseAdapter,
    MediaPipePoseConfig,
    Picamera2FrameSource,
    Picamera2SourceConfig,
    PoseProcessingError,
    VisionWorker,
    VisionWorkerConfig,
    VisionWorkerState,
)
from digital_spotter.vision.adapters import LocalPicamera2HelperSession
from digital_spotter.vision.picamera2_helper import FRAME_HEADER, FRAME_MAGIC


def _frame(sequence: int = 1) -> CameraFrame:
    return CameraFrame(
        sequence=sequence,
        received_monotonic_ns=20_000,
        width=640,
        height=360,
        timestamp=CaptureTimestamp(
            captured_monotonic_ns=10_000,
            source=CaptureTimestampSource.PICAMERA2_SENSOR_EXPOSURE_START,
        ),
        pixels=object(),
    )


class _FakeSession:
    def __init__(self, items):
        self.items = list(items)
        self.closed = False

    def read(self, timeout_s):
        assert timeout_s > 0
        return self.items.pop(0)

    def close(self):
        self.closed = True


class _FakeLauncher:
    def __init__(self, sessions):
        self.sessions = list(sessions)
        self.configs = []

    def start(self, config):
        self.configs.append(config)
        return self.sessions.pop(0)


def test_picamera2_source_fails_after_bounded_stall_and_new_owner_recovers():
    stalled = _FakeSession([None, None])
    recovered = _FakeSession([(_frame(), 0)])
    launcher = _FakeLauncher([stalled, recovered])
    config = Picamera2SourceConfig(max_consecutive_timeouts=2)

    first = Picamera2FrameSource(config, launcher=launcher)
    first.start()
    assert first.read(0.01) is None
    with pytest.raises(CameraUnavailableError) as failure:
        first.read(0.01)
    assert failure.value.reason_code is ReasonCode.CAMERA_UNAVAILABLE
    first.stop()

    second = Picamera2FrameSource(config, launcher=launcher)
    second.start()
    assert second.read(0.01) == (_frame(), 0)
    second.stop()

    assert stalled.closed is True
    assert recovered.closed is True
    assert len(launcher.configs) == 2


class _RealEvaluator:
    mode = "mediapipe"
    is_real = True
    is_simulated = False

    def __init__(self):
        self.closed = False

    def evaluate(self, frame):
        raise AssertionError("a stalled camera must not invoke pose inference")

    def close(self):
        self.closed = True


class _UnusedSink:
    def publish(self, event):
        raise AssertionError("a stalled camera must not publish a pose event")


def test_worker_exposes_camera_unavailable_after_bounded_stall():
    session = _FakeSession([None, None])
    source = Picamera2FrameSource(
        Picamera2SourceConfig(max_consecutive_timeouts=2),
        launcher=_FakeLauncher([session]),
    )
    evaluator = _RealEvaluator()
    worker = VisionWorker(
        config=VisionWorkerConfig(camera_id="picamera2-test"),
        source=source,
        evaluator=evaluator,
        sink=_UnusedSink(),
        clock=SimpleNamespace(now_ns=lambda: 1),
        event_id_factory=lambda: None,
    )

    with pytest.raises(CameraUnavailableError):
        worker.run()

    assert worker.state is VisionWorkerState.FAILED
    assert worker.summary().last_failure_reason is ReasonCode.CAMERA_UNAVAILABLE
    assert evaluator.closed is True
    assert session.closed is True


class _FakeProcess:
    stderr = None

    def poll(self):
        return 0

    def terminate(self):
        raise AssertionError("completed fake helper must not be terminated")

    def wait(self, timeout):
        return 0

    def kill(self):
        raise AssertionError("completed fake helper must not be killed")


def test_picamera2_helper_session_validates_and_decodes_one_bounded_frame():
    client, server = socket.socketpair()
    temporary_directory = tempfile.TemporaryDirectory(prefix="ds-adapter-test-")
    decoded = object()

    def decoder(payload, *, rows, columns):
        assert payload == bytes(range(24))
        assert (rows, columns) == (6, 4)
        return decoded

    session = LocalPicamera2HelperSession(
        connection=client,
        process=_FakeProcess(),
        temporary_directory=temporary_directory,
        analysis_size=(4, 4),
        decoder=decoder,
        monotonic_ns=lambda: 2_000_000,
    )
    server.sendall(
        FRAME_HEADER.pack(
            FRAME_MAGIC,
            7,
            1_900_000,
            100,
            4,
            4,
            6,
            4,
            24,
            2,
        )
        + bytes(range(24))
    )
    try:
        frame, dropped = session.read(0.1)
        assert frame.sequence == 7
        assert frame.pixels is decoded
        assert frame.timestamp.captured_monotonic_ns == 1_800_000
        assert dropped == 2
    finally:
        session.close()
        server.close()


def test_picamera2_helper_session_rejects_protocol_shape_mismatch():
    client, server = socket.socketpair()
    temporary_directory = tempfile.TemporaryDirectory(prefix="ds-adapter-test-")
    session = LocalPicamera2HelperSession(
        connection=client,
        process=_FakeProcess(),
        temporary_directory=temporary_directory,
        analysis_size=(4, 4),
        decoder=lambda *args, **kwargs: object(),
    )
    server.sendall(
        FRAME_HEADER.pack(FRAME_MAGIC, 1, 1_000, 0, 8, 4, 6, 4, 24, 0)
    )
    try:
        with pytest.raises(CameraProtocolError) as failure:
            session.read(0.1)
        assert failure.value.reason_code is ReasonCode.PROTOCOL_MISMATCH
    finally:
        session.close()
        server.close()


class _FakeCv2:
    COLOR_BGR2RGB = 17

    def cvtColor(self, pixels, conversion):
        assert conversion == self.COLOR_BGR2RGB
        return ("rgb", pixels)


class _RawLandmark:
    def __init__(self, index):
        self.x = index / 100.0
        self.y = index / 200.0
        self.z = -index / 300.0
        self.visibility = 0.8 if index == 25 else 0.95


class _FakePose:
    def __init__(self, result):
        self.result = result
        self.closed = False

    def process(self, rgb):
        assert rgb[0] == "rgb"
        if isinstance(self.result, Exception):
            raise self.result
        return self.result

    def close(self):
        self.closed = True


def _pose_adapter(result):
    pose = _FakePose(result)
    captured_kwargs = {}

    def factory(**kwargs):
        captured_kwargs.update(kwargs)
        return pose

    adapter = MediaPipePoseAdapter(
        MediaPipePoseConfig(model_complexity=1),
        cv2_module=_FakeCv2(),
        pose_factory=factory,
    )
    return adapter, pose, captured_kwargs


def test_mediapipe_adapter_returns_all_real_landmarks_without_inventing_angles():
    result = SimpleNamespace(
        pose_landmarks=SimpleNamespace(
            landmark=[_RawLandmark(index) for index in range(33)]
        )
    )
    adapter, pose, kwargs = _pose_adapter(result)

    evaluation = adapter.evaluate(_frame())
    adapter.close()

    assert evaluation.found is True
    assert len(evaluation.landmarks) == 33
    assert evaluation.confidence == 0.95
    assert evaluation.angles == {}
    assert kwargs == {
        "model_complexity": 1,
        "min_detection_confidence": 0.5,
        "min_tracking_confidence": 0.5,
        "static_image_mode": False,
    }
    assert pose.closed is True


def test_mediapipe_tracking_confidence_uses_best_body_side_not_face_or_far_side():
    raw = [_RawLandmark(index) for index in range(33)]
    for index in range(11):
        raw[index].visibility = 0.0
    for index in (11, 23, 25, 27):
        raw[index].visibility = 0.85
    for index in (12, 24, 26, 28):
        raw[index].visibility = 0.10
    result = SimpleNamespace(
        pose_landmarks=SimpleNamespace(landmark=raw)
    )
    adapter, _, _ = _pose_adapter(result)

    evaluation = adapter.evaluate(_frame())
    adapter.close()

    assert evaluation.found is True
    assert evaluation.confidence == 0.85


def test_mediapipe_adapter_reports_missing_pose_without_mock_landmarks():
    adapter, _, _ = _pose_adapter(SimpleNamespace(pose_landmarks=None))

    evaluation = adapter.evaluate(_frame())
    adapter.close()

    assert evaluation.found is False
    assert evaluation.landmarks == ()
    assert evaluation.angles == {}
    assert evaluation.confidence == 0.0


def test_mediapipe_adapter_turns_runtime_failure_into_typed_failure():
    adapter, _, _ = _pose_adapter(RuntimeError("injected inference failure"))

    with pytest.raises(PoseProcessingError) as failure:
        adapter.evaluate(_frame())
    adapter.close()

    assert failure.value.reason_code is ReasonCode.INTERNAL_ERROR


def test_picamera2_config_rejects_non_loopback_publication():
    with pytest.raises(ValueError, match="loopback"):
        Picamera2SourceConfig(publish_url="rtsp://192.0.2.10:8554/picam")
