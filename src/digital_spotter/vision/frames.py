"""Bounded camera-frame primitives shared by vision adapters and workers."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Generic, Mapping, TypeVar


class CameraFrameError(ValueError):
    """A camera frame cannot satisfy the canonical capture contract."""


class CaptureTimestampSource(str, Enum):
    PICAMERA2_SENSOR_EXPOSURE_START = "picamera2_sensor_exposure_start"
    REPLAY_FIXTURE = "replay_fixture"
    ARRIVAL_ONLY = "arrival_only"


@dataclass(frozen=True)
class CaptureTimestamp:
    captured_monotonic_ns: int | None
    source: CaptureTimestampSource
    sensor_timestamp_ns: int | None = None
    exposure_time_ns: int | None = None


def picamera2_capture_timestamp(
    metadata: Mapping[str, object],
    *,
    received_monotonic_ns: int,
) -> CaptureTimestamp:
    """Return first-pixel exposure start from Picamera2 request metadata."""

    sensor_timestamp = metadata.get("SensorTimestamp")
    exposure_time_us = metadata.get("ExposureTime")
    if isinstance(sensor_timestamp, bool) or not isinstance(sensor_timestamp, int):
        raise CameraFrameError("Picamera2 metadata has no integer SensorTimestamp")
    if isinstance(exposure_time_us, bool) or not isinstance(exposure_time_us, int):
        raise CameraFrameError("Picamera2 metadata has no integer ExposureTime")
    if sensor_timestamp <= 0 or exposure_time_us < 0:
        raise CameraFrameError("Picamera2 timing metadata is outside its valid range")
    if received_monotonic_ns < 0:
        raise CameraFrameError("frame receipt time must not be negative")

    exposure_time_ns = exposure_time_us * 1_000
    captured_monotonic_ns = sensor_timestamp - exposure_time_ns
    if captured_monotonic_ns < 0:
        raise CameraFrameError("calculated camera capture time is negative")
    if captured_monotonic_ns > received_monotonic_ns:
        raise CameraFrameError("camera capture time is later than frame receipt")

    return CaptureTimestamp(
        captured_monotonic_ns=captured_monotonic_ns,
        source=CaptureTimestampSource.PICAMERA2_SENSOR_EXPOSURE_START,
        sensor_timestamp_ns=sensor_timestamp,
        exposure_time_ns=exposure_time_ns,
    )


@dataclass(frozen=True)
class CameraFrame:
    sequence: int
    received_monotonic_ns: int
    width: int
    height: int
    timestamp: CaptureTimestamp
    pixels: object = field(repr=False, compare=False)

    def __post_init__(self) -> None:
        if self.sequence < 0:
            raise ValueError("frame sequence must not be negative")
        if self.received_monotonic_ns < 0:
            raise ValueError("frame receipt time must not be negative")
        if self.width <= 0 or self.height <= 0:
            raise ValueError("frame dimensions must be positive")
        captured = self.timestamp.captured_monotonic_ns
        if captured is not None and captured > self.received_monotonic_ns:
            raise ValueError("frame capture time cannot follow receipt")


T = TypeVar("T")


class LatestFrameSlot(Generic[T]):
    """Thread-safe capacity-one slot with explicit overwrite accounting."""

    def __init__(self) -> None:
        self._condition = threading.Condition()
        self._generation = 0
        self._item: T | None = None
        self._closed = False

    def publish(self, item: T) -> int:
        with self._condition:
            if self._closed:
                raise RuntimeError("latest-frame slot is closed")
            self._generation += 1
            self._item = item
            self._condition.notify_all()
            return self._generation

    def wait_after(
        self,
        generation: int,
        *,
        timeout_s: float,
    ) -> tuple[int, T, int] | None:
        if generation < 0:
            raise ValueError("generation must not be negative")
        if timeout_s <= 0:
            raise ValueError("timeout must be positive")
        deadline = time.monotonic() + timeout_s
        with self._condition:
            while not self._closed and self._generation <= generation:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return None
                self._condition.wait(remaining)
            if self._generation <= generation or self._item is None:
                return None
            dropped = max(0, self._generation - generation - 1)
            return self._generation, self._item, dropped

    def close(self) -> None:
        with self._condition:
            self._closed = True
            self._condition.notify_all()
