from __future__ import annotations

import pytest

from digital_spotter.vision.camera_bench import (
    RTSPFrameSource,
    _process_ticks,
    _receive_exact,
    run_restart_probe,
)
from digital_spotter.vision.camera_spike import (
    CameraFrame,
    CameraSpikeError,
    CaptureTimestamp,
    CaptureTimestampSource,
    FrameMeasurement,
    LatestFrameSlot,
    picamera2_capture_timestamp,
    summarize_measurements,
)


def _measurement(
    sequence: int,
    *,
    captured: int | None,
    received: int,
    processed: int,
    found: bool = True,
    valid: bool = True,
    dropped: int = 0,
) -> FrameMeasurement:
    return FrameMeasurement(
        frame_sequence=sequence,
        captured_monotonic_ns=captured,
        received_monotonic_ns=received,
        processed_monotonic_ns=processed,
        timestamp_source=(
            CaptureTimestampSource.PICAMERA2_SENSOR_EXPOSURE_START
            if captured is not None
            else CaptureTimestampSource.ARRIVAL_ONLY
        ),
        width=640,
        height=360,
        dropped_since_previous=dropped,
        pose_found=found,
        pose_valid=valid,
        pose_confidence=0.9 if found else 0.0,
        pose_processing_time_ns=processed - received,
    )


def test_picamera2_timestamp_uses_sensor_time_and_exposure_start():
    estimate = picamera2_capture_timestamp(
        {"SensorTimestamp": 10_000_000_000, "ExposureTime": 8_000},
        received_monotonic_ns=10_020_000_000,
    )

    assert estimate.captured_monotonic_ns == 9_992_000_000
    assert estimate.sensor_timestamp_ns == 10_000_000_000
    assert estimate.exposure_time_ns == 8_000_000
    assert estimate.source is CaptureTimestampSource.PICAMERA2_SENSOR_EXPOSURE_START


@pytest.mark.parametrize(
    "metadata",
    [
        {},
        {"SensorTimestamp": "10", "ExposureTime": 5_000},
        {"SensorTimestamp": 10_000, "ExposureTime": -1},
    ],
)
def test_picamera2_timestamp_rejects_missing_or_invalid_metadata(metadata):
    with pytest.raises(CameraSpikeError):
        picamera2_capture_timestamp(metadata, received_monotonic_ns=20_000)


def test_picamera2_timestamp_rejects_future_capture():
    with pytest.raises(CameraSpikeError, match="later than frame receipt"):
        picamera2_capture_timestamp(
            {"SensorTimestamp": 50_000, "ExposureTime": 0},
            received_monotonic_ns=49_999,
        )


def test_latest_frame_slot_is_capacity_one_and_counts_overwrites():
    slot: LatestFrameSlot[str] = LatestFrameSlot()
    assert slot.publish("first") == 1
    assert slot.publish("second") == 2
    assert slot.publish("latest") == 3

    assert slot.wait_after(0, timeout_s=0.01) == (3, "latest", 2)


def test_latest_frame_slot_close_unblocks_without_fabricating_frame():
    slot: LatestFrameSlot[str] = LatestFrameSlot()
    slot.close()

    assert slot.wait_after(0, timeout_s=0.01) is None
    with pytest.raises(RuntimeError, match="closed"):
        slot.publish("late")


def test_camera_frame_refuses_capture_after_receipt():
    with pytest.raises(ValueError, match="cannot follow receipt"):
        CameraFrame(
            sequence=1,
            received_monotonic_ns=100,
            width=640,
            height=360,
            timestamp=CaptureTimestamp(
                captured_monotonic_ns=101,
                source=CaptureTimestampSource.PICAMERA2_SENSOR_EXPOSURE_START,
            ),
            pixels=object(),
        )


def test_summary_preserves_capture_and_pose_measurement_evidence():
    samples = [
        _measurement(1, captured=1_000, received=2_000, processed=4_000),
        _measurement(2, captured=11_000, received=12_000, processed=14_000, dropped=2),
        _measurement(3, captured=21_000, received=22_000, processed=24_000),
    ]

    summary = summarize_measurements(
        "picamera2",
        samples,
        person_required=True,
        capture_timestamps_required=True,
    )

    assert summary.frames_processed == 3
    assert summary.timestamp_coverage_pct == 100.0
    assert summary.capture_age_p95_ms == 0.001
    assert summary.pose_found_pct == 100.0
    assert summary.pose_valid_pct == 100.0
    assert summary.source_frames_dropped == 2
    assert summary.capture_times_monotonic is True
    assert summary.failed_checks == ()


def test_arrival_only_candidate_is_not_misreported_as_capture_time():
    samples = [
        _measurement(1, captured=None, received=1_000, processed=2_000),
        _measurement(2, captured=None, received=3_000, processed=4_000),
    ]

    summary = summarize_measurements(
        "mediamtx-rtsp",
        samples,
        person_required=False,
        capture_timestamps_required=True,
    )

    assert summary.timestamp_coverage_pct == 0.0
    assert summary.capture_age_p95_ms is None
    assert summary.capture_times_monotonic is False
    assert summary.failed_checks == ("capture_timestamp_unavailable",)


def test_missing_camera_and_person_are_explicit():
    empty = summarize_measurements(
        "candidate",
        [],
        person_required=True,
        capture_timestamps_required=True,
    )
    no_person = summarize_measurements(
        "candidate",
        [
            _measurement(
                1,
                captured=1_000,
                received=2_000,
                processed=3_000,
                found=False,
                valid=False,
            )
        ],
        person_required=True,
        capture_timestamps_required=True,
    )

    assert empty.failed_checks == ("no_camera_frames",)
    assert empty.missing_person_explicit is True
    assert no_person.failed_checks == ("person_pose_not_observed",)
    assert no_person.missing_person_explicit is True


class _RestartSource:
    def __init__(self, result=True):
        self.result = result
        self.started = False
        self.stopped = False

    def start(self):
        self.started = True

    def read(self, timeout_s):
        assert timeout_s == 3.0
        return (object(), 0) if self.result else None

    def stop(self):
        self.stopped = True


def test_restart_probe_creates_and_closes_one_owner_per_cycle():
    sources = []

    def factory():
        source = _RestartSource()
        sources.append(source)
        return source

    assert run_restart_probe(factory, cycles=3) == (True, True, True)
    assert all(source.started and source.stopped for source in sources)


def test_rtsp_shutdown_waits_for_reader_before_releasing_capture():
    events = []

    class _Capture:
        def release(self):
            events.append("release")

    class _Thread:
        def __init__(self):
            self.join_calls = 0

        def join(self, timeout):
            self.join_calls += 1
            events.append(f"join:{timeout}")

        def is_alive(self):
            return False

    source = RTSPFrameSource(
        "rtsp://example.invalid/test",
        analysis_size=(640, 360),
    )
    source._running = True
    source._slot = LatestFrameSlot()
    source._capture = _Capture()
    source._thread = _Thread()

    source.stop()

    assert events == ["join:3.0", "release"]


def test_rtsp_drain_resizes_browser_stream_for_pose_input():
    class _Pixels:
        shape = (720, 1280, 3)

    class _ResizedPixels:
        shape = (360, 640, 3)

    class _Cv2:
        INTER_AREA = "area"

        def resize(self, pixels, size, interpolation):
            assert isinstance(pixels, _Pixels)
            assert size == (640, 360)
            assert interpolation == self.INTER_AREA
            return _ResizedPixels()

    source = RTSPFrameSource(
        "rtsp://example.invalid/test",
        analysis_size=(640, 360),
    )

    class _Capture:
        def read(self):
            source._running = False
            return True, _Pixels()

    source._capture = _Capture()
    source._cv2 = _Cv2()
    source._slot = LatestFrameSlot()
    source._running = True

    source._drain()

    item = source._slot.wait_after(0, timeout_s=0.01)
    assert item is not None
    _, frame, _ = item
    assert (frame.width, frame.height) == (640, 360)


def test_receive_exact_reassembles_bounded_socket_parts():
    class _Socket:
        parts = [b"ab", b"c", b"def"]

        def recv(self, size):
            return self.parts.pop(0)[:size]

    assert _receive_exact(_Socket(), 6) == b"abcdef"


def test_receive_exact_rejects_truncated_helper_frame():
    class _Socket:
        def recv(self, size):
            return b""

    with pytest.raises(CameraSpikeError, match="complete frame"):
        _receive_exact(_Socket(), 1)


def test_process_ticks_reads_current_process():
    import os

    ticks = _process_ticks(os.getpid())

    assert isinstance(ticks, int)
    assert ticks >= 0
