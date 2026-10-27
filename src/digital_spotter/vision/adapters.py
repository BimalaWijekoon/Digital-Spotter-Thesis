"""Real Picamera2 and MediaPipe adapters for the isolated vision worker."""

from __future__ import annotations

import math
import os
import socket
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Protocol

from digital_spotter.contracts import PoseLandmark
from digital_spotter.vision.errors import (
    CameraProtocolError,
    CameraUnavailableError,
    PoseProcessingError,
    PoseUnavailableError,
)
from digital_spotter.vision.frames import (
    CameraFrame,
    CameraFrameError,
    picamera2_capture_timestamp,
)
from digital_spotter.vision.picamera2_helper import FRAME_HEADER, FRAME_MAGIC
from digital_spotter.vision.pose_events import PoseEvaluation


MAX_CAMERA_FRAME_BYTES = 4 * 1024 * 1024
MEDIAPIPE_POSE_LANDMARK_COUNT = 33
TRACKING_BODY_SIDES = (
    (11, 23, 25, 27),
    (12, 24, 26, 28),
)


def _validate_size(name: str, size: tuple[int, int]) -> None:
    width, height = size
    if width <= 0 or height <= 0 or width > 4096 or height > 2160:
        raise ValueError(f"{name} size must be within 1x1 and 4096x2160")
    if width % 2 or height % 2:
        raise ValueError(f"{name} size must be even for YUV420")


@dataclass(frozen=True)
class Picamera2SourceConfig:
    python_executable: str = "/usr/bin/python3"
    main_size: tuple[int, int] = (1280, 720)
    analysis_size: tuple[int, int] = (640, 360)
    fps: int = 30
    encode_h264: bool = True
    publish_url: str | None = None
    startup_timeout_s: float = 15.0
    max_consecutive_timeouts: int = 3

    def __post_init__(self) -> None:
        if not self.python_executable:
            raise ValueError("Picamera2 Python executable must not be empty")
        _validate_size("main", self.main_size)
        _validate_size("analysis", self.analysis_size)
        if self.fps not in (15, 30):
            raise ValueError("camera FPS must be 15 or 30")
        if not 0.1 <= self.startup_timeout_s <= 60.0:
            raise ValueError("camera startup timeout must be between 0.1 and 60 seconds")
        if not 1 <= self.max_consecutive_timeouts <= 10:
            raise ValueError("camera timeout limit must be between 1 and 10")
        if self.publish_url is not None and not self.publish_url.startswith(
            ("rtsp://127.0.0.1:", "rtsp://localhost:")
        ):
            raise ValueError("camera publication must use a loopback RTSP URL")


class CameraHelperSession(Protocol):
    def read(self, timeout_s: float) -> tuple[CameraFrame, int] | None: ...
    def close(self) -> None: ...


class CameraHelperLauncher(Protocol):
    def start(self, config: Picamera2SourceConfig) -> CameraHelperSession: ...


class _I420Decoder:
    def __init__(self) -> None:
        try:
            import cv2
            import numpy as np
        except ImportError as exc:
            raise CameraUnavailableError(
                "OpenCV and NumPy are required for Picamera2 lores frames"
            ) from exc
        self._cv2 = cv2
        self._np = np

    def __call__(self, payload: bytes, *, rows: int, columns: int) -> object:
        try:
            yuv = self._np.frombuffer(payload, dtype=self._np.uint8).reshape(rows, columns)
            return self._cv2.cvtColor(yuv, self._cv2.COLOR_YUV2BGR_I420)
        except Exception as exc:
            raise CameraProtocolError("Picamera2 helper YUV frame cannot be decoded") from exc


def _receive_exact(connection: socket.socket, size: int) -> bytes:
    data = bytearray()
    while len(data) < size:
        try:
            part = connection.recv(size - len(data))
        except socket.timeout:
            raise
        except OSError as exc:
            raise CameraUnavailableError("Picamera2 helper socket read failed") from exc
        if not part:
            raise CameraUnavailableError(
                "Picamera2 helper closed before a complete frame"
            )
        data.extend(part)
    return bytes(data)


def _process_error(process: subprocess.Popen[str], fallback: str) -> str:
    if process.stderr is None:
        return fallback
    try:
        stderr = process.stderr.read()
    except OSError:
        return fallback
    return stderr.strip().splitlines()[-1] if stderr.strip() else fallback


def _stop_process(process: subprocess.Popen[str]) -> None:
    if process.poll() is None:
        process.terminate()
    try:
        process.wait(timeout=3.0)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=3.0)


class LocalPicamera2HelperSession:
    """One bounded local connection to the system-Python camera owner."""

    def __init__(
        self,
        *,
        connection: socket.socket,
        process: subprocess.Popen[str],
        temporary_directory: tempfile.TemporaryDirectory[str],
        analysis_size: tuple[int, int],
        decoder: Callable[..., object],
        monotonic_ns: Callable[[], int] = time.monotonic_ns,
    ) -> None:
        self._connection = connection
        self._process = process
        self._temporary_directory = temporary_directory
        self._analysis_size = analysis_size
        self._decoder = decoder
        self._monotonic_ns = monotonic_ns
        self._pending_acknowledgement = False
        self._closed = False

    def read(self, timeout_s: float) -> tuple[CameraFrame, int] | None:
        if self._closed:
            raise CameraUnavailableError("Picamera2 helper session is closed")
        if timeout_s <= 0:
            raise ValueError("camera read timeout must be positive")
        self._connection.settimeout(timeout_s)
        try:
            if self._pending_acknowledgement:
                self._connection.sendall(b"C")
                self._pending_acknowledgement = False
            raw_header = _receive_exact(self._connection, FRAME_HEADER.size)
            (
                magic,
                sequence,
                sensor_timestamp_ns,
                exposure_time_us,
                width,
                height,
                array_rows,
                array_columns,
                payload_size,
                dropped,
            ) = FRAME_HEADER.unpack(raw_header)
            if magic != FRAME_MAGIC:
                raise CameraProtocolError("Picamera2 helper frame magic is invalid")
            expected_width, expected_height = self._analysis_size
            expected_rows = expected_height * 3 // 2
            expected_size = expected_rows * expected_width
            if (
                (width, height) != self._analysis_size
                or array_rows != expected_rows
                or array_columns != expected_width
                or payload_size != expected_size
                or payload_size > MAX_CAMERA_FRAME_BYTES
            ):
                raise CameraProtocolError("Picamera2 helper frame shape or size is invalid")
            payload = _receive_exact(self._connection, payload_size)
        except socket.timeout:
            if self._process.poll() is not None:
                raise CameraUnavailableError(
                    f"Picamera2 helper exited: {_process_error(self._process, 'unknown error')}"
                )
            return None
        except OSError as exc:
            raise CameraUnavailableError("Picamera2 helper socket closed") from exc

        received_ns = self._monotonic_ns()
        try:
            timestamp = picamera2_capture_timestamp(
                {
                    "SensorTimestamp": sensor_timestamp_ns,
                    "ExposureTime": exposure_time_us,
                },
                received_monotonic_ns=received_ns,
            )
        except CameraFrameError as exc:
            raise CameraProtocolError("Picamera2 helper timing metadata is invalid") from exc
        pixels = self._decoder(payload, rows=array_rows, columns=array_columns)
        self._pending_acknowledgement = True
        return (
            CameraFrame(
                sequence=sequence,
                received_monotonic_ns=received_ns,
                width=width,
                height=height,
                timestamp=timestamp,
                pixels=pixels,
            ),
            dropped,
        )

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            try:
                self._connection.sendall(b"Q")
            except OSError:
                pass
            self._connection.close()
            _stop_process(self._process)
        finally:
            if self._process.stderr is not None:
                self._process.stderr.close()
            self._temporary_directory.cleanup()


class LocalPicamera2HelperLauncher:
    """Start the existing system-Python Picamera2 helper over a private UDS."""

    def start(self, config: Picamera2SourceConfig) -> CameraHelperSession:
        decoder = _I420Decoder()
        temporary_directory = tempfile.TemporaryDirectory(prefix="ds-vision-camera-")
        socket_path = str(Path(temporary_directory.name) / "frames.sock")
        listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        process: subprocess.Popen[str] | None = None
        try:
            listener.bind(socket_path)
            os.chmod(socket_path, 0o600)
            listener.listen(1)
            listener.settimeout(0.2)
            helper_path = Path(__file__).with_name("picamera2_helper.py")
            command = [
                config.python_executable,
                str(helper_path),
                "--socket",
                socket_path,
                "--main-width",
                str(config.main_size[0]),
                "--main-height",
                str(config.main_size[1]),
                "--analysis-width",
                str(config.analysis_size[0]),
                "--analysis-height",
                str(config.analysis_size[1]),
                "--fps",
                str(config.fps),
            ]
            if config.encode_h264:
                command.append("--encode-h264")
            if config.publish_url:
                command.extend(("--publish-url", config.publish_url))
            process = subprocess.Popen(
                command,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True,
            )
            deadline = time.monotonic() + config.startup_timeout_s
            while True:
                if process.poll() is not None:
                    raise CameraUnavailableError(
                        f"Picamera2 helper exited during startup: "
                        f"{_process_error(process, 'unknown error')}"
                    )
                try:
                    connection, _ = listener.accept()
                    break
                except socket.timeout:
                    if time.monotonic() >= deadline:
                        raise CameraUnavailableError("Picamera2 helper startup timed out")
            listener.close()
            return LocalPicamera2HelperSession(
                connection=connection,
                process=process,
                temporary_directory=temporary_directory,
                analysis_size=config.analysis_size,
                decoder=decoder,
            )
        except Exception:
            listener.close()
            if process is not None:
                _stop_process(process)
                if process.stderr is not None:
                    process.stderr.close()
            temporary_directory.cleanup()
            raise


class Picamera2FrameSource:
    """Real camera source with bounded stall detection and restartable ownership."""

    mode = "picamera2"
    is_real = True
    is_simulated = False

    def __init__(
        self,
        config: Picamera2SourceConfig,
        *,
        launcher: CameraHelperLauncher | None = None,
    ) -> None:
        self.config = config
        self._launcher = launcher or LocalPicamera2HelperLauncher()
        self._session: CameraHelperSession | None = None
        self._consecutive_timeouts = 0

    @property
    def exhausted(self) -> bool:
        return False

    @property
    def is_running(self) -> bool:
        return self._session is not None

    def start(self) -> None:
        if self._session is not None:
            raise CameraUnavailableError("Picamera2 source is already running")
        self._session = self._launcher.start(self.config)
        self._consecutive_timeouts = 0

    def read(self, timeout_s: float) -> tuple[CameraFrame, int] | None:
        if self._session is None:
            raise CameraUnavailableError("Picamera2 source is not running")
        item = self._session.read(timeout_s)
        if item is None:
            self._consecutive_timeouts += 1
            if self._consecutive_timeouts >= self.config.max_consecutive_timeouts:
                raise CameraUnavailableError(
                    "Picamera2 source exceeded its consecutive frame-timeout limit"
                )
            return None
        self._consecutive_timeouts = 0
        return item

    def stop(self) -> None:
        session = self._session
        self._session = None
        self._consecutive_timeouts = 0
        if session is not None:
            session.close()


@dataclass(frozen=True)
class MediaPipePoseConfig:
    model_complexity: int = 1
    min_detection_confidence: float = 0.5
    min_tracking_confidence: float = 0.5

    def __post_init__(self) -> None:
        if self.model_complexity not in (0, 1, 2):
            raise ValueError("MediaPipe model complexity must be 0, 1, or 2")
        for name, value in (
            ("detection", self.min_detection_confidence),
            ("tracking", self.min_tracking_confidence),
        ):
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"MediaPipe {name} confidence must be between zero and one")


class MediaPipePoseAdapter:
    """Real MediaPipe Pose adapter with no mock or default-pose fallback."""

    mode = "mediapipe"
    is_real = True
    is_simulated = False

    def __init__(
        self,
        config: MediaPipePoseConfig,
        *,
        cv2_module: object | None = None,
        pose_factory: Callable[..., object] | None = None,
    ) -> None:
        try:
            if cv2_module is None:
                import cv2 as cv2_module
            if pose_factory is None:
                import mediapipe as mp

                pose_factory = mp.solutions.pose.Pose
            self._cv2 = cv2_module
            self._pose = pose_factory(
                model_complexity=config.model_complexity,
                min_detection_confidence=config.min_detection_confidence,
                min_tracking_confidence=config.min_tracking_confidence,
                static_image_mode=False,
            )
        except Exception as exc:
            raise PoseUnavailableError("real MediaPipe Pose initialization failed") from exc
        self._closed = False

    def evaluate(self, frame: CameraFrame) -> PoseEvaluation:
        return self.evaluate_pixels(frame.pixels)

    def evaluate_pixels(self, pixels: object) -> PoseEvaluation:
        """Evaluate one BGR image without inventing missing pose data."""

        if self._closed:
            raise PoseUnavailableError("MediaPipe pose adapter is closed")
        try:
            rgb = self._cv2.cvtColor(pixels, self._cv2.COLOR_BGR2RGB)
            result = self._pose.process(rgb)
        except Exception as exc:
            raise PoseProcessingError("MediaPipe pose inference failed") from exc
        if result.pose_landmarks is None:
            return PoseEvaluation(found=False, landmarks=(), angles={}, confidence=0.0)

        raw_landmarks = result.pose_landmarks.landmark
        if len(raw_landmarks) != MEDIAPIPE_POSE_LANDMARK_COUNT:
            raise PoseProcessingError("MediaPipe returned an unexpected landmark count")
        landmarks: list[PoseLandmark] = []
        for raw in raw_landmarks:
            values = (float(raw.x), float(raw.y), float(raw.z), float(raw.visibility))
            if not all(math.isfinite(value) for value in values):
                raise PoseProcessingError("MediaPipe returned a non-finite landmark")
            landmarks.append(
                PoseLandmark(
                    x=values[0],
                    y=values[1],
                    z=values[2],
                    visibility=max(0.0, min(1.0, values[3])),
                )
            )
        # A side-on athlete often hides the far side and may move their face out
        # of frame. Track as soon as one shoulder-hip-knee-ankle chain is usable;
        # model-feature eligibility is checked independently downstream.
        confidence = max(
            min(landmarks[index].visibility for index in side)
            for side in TRACKING_BODY_SIDES
        )
        return PoseEvaluation(
            found=True,
            landmarks=tuple(landmarks),
            angles={},
            confidence=confidence,
        )

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._pose.close()
