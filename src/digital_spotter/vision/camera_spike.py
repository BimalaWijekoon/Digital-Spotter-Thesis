"""R13-C camera-owner measurement primitives.

This module is intentionally smaller than the eventual vision worker.  It keeps
the camera-owner comparison honest by separating sensor capture time from frame
arrival and pose-processing time, and by exposing a capacity-one latest-frame
slot for adapters that otherwise buffer stale frames.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Mapping

from digital_spotter.vision.frames import (
    CameraFrame,
    CameraFrameError,
    CaptureTimestamp,
    CaptureTimestampSource,
    LatestFrameSlot,
    picamera2_capture_timestamp as _picamera2_capture_timestamp,
)


class CameraSpikeError(RuntimeError):
    """The candidate cannot provide a usable camera frame."""


def picamera2_capture_timestamp(
    metadata: Mapping[str, object],
    *,
    received_monotonic_ns: int,
) -> CaptureTimestamp:
    """Keep the R13-C spike error contract while sharing canonical logic."""

    try:
        return _picamera2_capture_timestamp(
            metadata,
            received_monotonic_ns=received_monotonic_ns,
        )
    except CameraFrameError as exc:
        raise CameraSpikeError(str(exc)) from exc


@dataclass(frozen=True)
class PoseMeasurement:
    found: bool
    valid: bool
    confidence: float
    processing_time_ns: int

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("pose confidence must be between zero and one")
        if self.processing_time_ns < 0:
            raise ValueError("pose processing time must not be negative")
        if self.valid and not self.found:
            raise ValueError("a valid pose must have been found")


@dataclass(frozen=True)
class FrameMeasurement:
    frame_sequence: int
    captured_monotonic_ns: int | None
    received_monotonic_ns: int
    processed_monotonic_ns: int
    timestamp_source: CaptureTimestampSource
    width: int
    height: int
    dropped_since_previous: int
    pose_found: bool
    pose_valid: bool
    pose_confidence: float
    pose_processing_time_ns: int

    def __post_init__(self) -> None:
        if self.processed_monotonic_ns < self.received_monotonic_ns:
            raise ValueError("processing completion cannot precede frame receipt")
        if self.captured_monotonic_ns is not None:
            if self.captured_monotonic_ns > self.received_monotonic_ns:
                raise ValueError("frame capture cannot follow frame receipt")
        if self.dropped_since_previous < 0:
            raise ValueError("frame drop count must not be negative")


@dataclass(frozen=True)
class CameraSpikeSummary:
    candidate: str
    frames_processed: int
    observed_duration_s: float
    effective_pose_fps: float | None
    pose_found_pct: float
    pose_valid_pct: float
    timestamp_coverage_pct: float
    capture_age_p50_ms: float | None
    capture_age_p95_ms: float | None
    pose_processing_p50_ms: float | None
    pose_processing_p95_ms: float | None
    source_frames_dropped: int
    capture_times_monotonic: bool
    missing_person_explicit: bool
    failed_checks: tuple[str, ...]


def _nearest_rank(values: list[int], quantile: float) -> int | None:
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, math.ceil(quantile * len(ordered)) - 1)
    return ordered[index]


def summarize_measurements(
    candidate: str,
    measurements: list[FrameMeasurement],
    *,
    person_required: bool,
    capture_timestamps_required: bool,
) -> CameraSpikeSummary:
    """Summarize one bounded candidate run without inventing missing evidence."""

    failed: list[str] = []
    if not measurements:
        return CameraSpikeSummary(
            candidate=candidate,
            frames_processed=0,
            observed_duration_s=0.0,
            effective_pose_fps=None,
            pose_found_pct=0.0,
            pose_valid_pct=0.0,
            timestamp_coverage_pct=0.0,
            capture_age_p50_ms=None,
            capture_age_p95_ms=None,
            pose_processing_p50_ms=None,
            pose_processing_p95_ms=None,
            source_frames_dropped=0,
            capture_times_monotonic=False,
            missing_person_explicit=True,
            failed_checks=("no_camera_frames",),
        )

    first_ns = measurements[0].received_monotonic_ns
    last_ns = measurements[-1].processed_monotonic_ns
    duration_s = max(0.0, (last_ns - first_ns) / 1_000_000_000.0)
    effective_fps = len(measurements) / duration_s if duration_s > 0 else None
    found_count = sum(item.pose_found for item in measurements)
    valid_count = sum(item.pose_valid for item in measurements)
    captures = [
        item.captured_monotonic_ns
        for item in measurements
        if item.captured_monotonic_ns is not None
    ]
    capture_ages = [
        item.received_monotonic_ns - item.captured_monotonic_ns
        for item in measurements
        if item.captured_monotonic_ns is not None
    ]
    processing_times = [item.pose_processing_time_ns for item in measurements]
    captures_monotonic = bool(captures) and all(
        current > previous for previous, current in zip(captures, captures[1:])
    )
    missing_person = found_count == 0 or valid_count == 0
    coverage = 100.0 * len(captures) / len(measurements)

    if capture_timestamps_required and coverage < 100.0:
        failed.append("capture_timestamp_unavailable")
    if captures and not captures_monotonic:
        failed.append("capture_timestamp_not_strictly_monotonic")
    if person_required and missing_person:
        failed.append("person_pose_not_observed")

    p50_age = _nearest_rank(capture_ages, 0.50)
    p95_age = _nearest_rank(capture_ages, 0.95)
    p50_pose = _nearest_rank(processing_times, 0.50)
    p95_pose = _nearest_rank(processing_times, 0.95)
    return CameraSpikeSummary(
        candidate=candidate,
        frames_processed=len(measurements),
        observed_duration_s=round(duration_s, 6),
        effective_pose_fps=round(effective_fps, 3) if effective_fps else None,
        pose_found_pct=round(100.0 * found_count / len(measurements), 3),
        pose_valid_pct=round(100.0 * valid_count / len(measurements), 3),
        timestamp_coverage_pct=round(coverage, 3),
        capture_age_p50_ms=round(p50_age / 1_000_000.0, 3) if p50_age is not None else None,
        capture_age_p95_ms=round(p95_age / 1_000_000.0, 3) if p95_age is not None else None,
        pose_processing_p50_ms=round(p50_pose / 1_000_000.0, 3) if p50_pose is not None else None,
        pose_processing_p95_ms=round(p95_pose / 1_000_000.0, 3) if p95_pose is not None else None,
        source_frames_dropped=sum(item.dropped_since_previous for item in measurements),
        capture_times_monotonic=captures_monotonic,
        missing_person_explicit=missing_person,
        failed_checks=tuple(failed),
    )
