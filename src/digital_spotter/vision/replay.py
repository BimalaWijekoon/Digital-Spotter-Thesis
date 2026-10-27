"""Deterministic synthetic frame and pose adapters for vision-worker tests."""

from __future__ import annotations

from pathlib import Path

from digital_spotter.vision.frames import (
    CameraFrame,
    CaptureTimestamp,
    CaptureTimestampSource,
)
from digital_spotter.vision.pose_events import PoseEvaluation


MAX_REPLAY_VIDEO_BYTES = 2 * 1024 * 1024


class VisionReplayError(ValueError):
    """A replay artifact cannot satisfy the deterministic vision contract."""


def _parse_y4m(path: Path) -> tuple[int, int, tuple[bytes, ...]]:
    if not path.is_file():
        raise VisionReplayError(f"replay video not found: {path}")
    size = path.stat().st_size
    if size <= 0 or size > MAX_REPLAY_VIDEO_BYTES:
        raise VisionReplayError("replay video size is outside the accepted bound")
    data = path.read_bytes()
    header_end = data.find(b"\n")
    if header_end < 0:
        raise VisionReplayError("Y4M header is truncated")
    try:
        tokens = data[:header_end].decode("ascii").split()
    except UnicodeDecodeError as exc:
        raise VisionReplayError("Y4M header is not ASCII") from exc
    if not tokens or tokens[0] != "YUV4MPEG2":
        raise VisionReplayError("replay video is not Y4M")
    fields = {token[0]: token[1:] for token in tokens[1:] if len(token) > 1}
    try:
        width = int(fields["W"])
        height = int(fields["H"])
    except (KeyError, ValueError) as exc:
        raise VisionReplayError("Y4M dimensions are missing or invalid") from exc
    color = fields.get("C", "420")
    if width <= 0 or height <= 0:
        raise VisionReplayError("Y4M dimensions must be positive")
    if color == "mono":
        frame_bytes = width * height
    elif color.startswith("420"):
        if width % 2 or height % 2:
            raise VisionReplayError("Y4M 4:2:0 dimensions must be even")
        frame_bytes = width * height * 3 // 2
    else:
        raise VisionReplayError("only bounded Y4M mono or 4:2:0 replay is supported")
    frames: list[bytes] = []
    offset = header_end + 1
    while offset < len(data):
        marker_end = data.find(b"\n", offset)
        if marker_end < 0 or not data[offset:marker_end].startswith(b"FRAME"):
            raise VisionReplayError("Y4M frame marker is missing or truncated")
        payload_start = marker_end + 1
        payload_end = payload_start + frame_bytes
        if payload_end > len(data):
            raise VisionReplayError("Y4M frame payload is truncated")
        frames.append(data[payload_start:payload_end])
        offset = payload_end
    if not frames:
        raise VisionReplayError("Y4M replay contains no frames")
    return width, height, tuple(frames)


class ReplayFrameSource:
    """Finite, no-sleep frame source that is permanently marked simulated."""

    mode = "replay"
    is_real = False
    is_simulated = True

    def __init__(self, *, video_path: Path, captured_monotonic_ns: tuple[int, ...]) -> None:
        if not captured_monotonic_ns:
            raise VisionReplayError("replay timestamps must not be empty")
        if any(value < 0 for value in captured_monotonic_ns):
            raise VisionReplayError("replay timestamps must not be negative")
        if any(
            current <= previous
            for previous, current in zip(
                captured_monotonic_ns,
                captured_monotonic_ns[1:],
            )
        ):
            raise VisionReplayError("replay timestamps must increase")
        self.video_path = video_path
        self.captured_monotonic_ns = captured_monotonic_ns
        self._frames: tuple[bytes, ...] = ()
        self._width = 0
        self._height = 0
        self._index = 0
        self._running = False

    @property
    def exhausted(self) -> bool:
        return self._running and self._index >= len(self._frames)

    @property
    def is_running(self) -> bool:
        return self._running

    def start(self) -> None:
        if self._running:
            raise VisionReplayError("replay frame source is already running")
        width, height, frames = _parse_y4m(self.video_path)
        if len(frames) != len(self.captured_monotonic_ns):
            raise VisionReplayError("replay frame and timestamp counts differ")
        self._width = width
        self._height = height
        self._frames = frames
        self._index = 0
        self._running = True

    def read(self, timeout_s: float) -> tuple[CameraFrame, int] | None:
        if not self._running:
            raise VisionReplayError("replay frame source is not running")
        if timeout_s <= 0:
            raise ValueError("timeout must be positive")
        if self._index >= len(self._frames):
            return None
        captured_ns = self.captured_monotonic_ns[self._index]
        frame = CameraFrame(
            sequence=self._index + 1,
            received_monotonic_ns=captured_ns,
            width=self._width,
            height=self._height,
            timestamp=CaptureTimestamp(
                captured_monotonic_ns=captured_ns,
                source=CaptureTimestampSource.REPLAY_FIXTURE,
            ),
            pixels=self._frames[self._index],
        )
        self._index += 1
        return frame, 0

    def stop(self) -> None:
        self._running = False
        self._frames = ()


class ReplayPoseEvaluator:
    """Return a fixed evaluation for each replay frame, without image inference."""

    mode = "replay"
    is_real = False
    is_simulated = True

    def __init__(self, evaluations: tuple[PoseEvaluation, ...]) -> None:
        if not evaluations:
            raise VisionReplayError("replay pose evaluations must not be empty")
        self._evaluations = evaluations
        self._index = 0
        self.closed = False

    def evaluate(self, frame: CameraFrame) -> PoseEvaluation:
        if self.closed:
            raise VisionReplayError("replay pose evaluator is closed")
        if self._index >= len(self._evaluations):
            raise VisionReplayError("replay pose evaluations are exhausted")
        if frame.sequence != self._index + 1:
            raise VisionReplayError("replay frame sequence is not deterministic")
        evaluation = self._evaluations[self._index]
        self._index += 1
        return evaluation

    def close(self) -> None:
        self.closed = True
