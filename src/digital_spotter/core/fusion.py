"""Small, scoring-independent pose/IMU association in Pi monotonic time."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence
from uuid import UUID

from digital_spotter.contracts import (
    ClockState,
    EventEnvelope,
    EventType,
    FusedSample,
    IMUSample,
    InterpolatedIMU,
    PoseSample,
    Quality,
    ReasonCode,
    Source,
)


@dataclass(frozen=True)
class FusionPolicy:
    """Research association bounds, not a measured alignment guarantee."""

    max_pose_age_ns: int = 250_000_000
    max_imu_neighbor_distance_ns: int = 30_000_000
    max_imu_bracket_span_ns: int = 40_000_000
    max_clock_error_ns: int = 20_000_000

    def __post_init__(self) -> None:
        if any(
            value <= 0
            for value in (
                self.max_pose_age_ns,
                self.max_imu_neighbor_distance_ns,
                self.max_imu_bracket_span_ns,
                self.max_clock_error_ns,
            )
        ):
            raise ValueError("fusion bounds must be positive")


@dataclass(frozen=True)
class FusionOutcome:
    pose_event_id: UUID
    quality: Quality
    reasons: tuple[ReasonCode, ...]
    sample: FusedSample | None


class FusionEngine:
    """Interpolate only safely bracketed measurements; never use arrival time."""

    def __init__(self, policy: FusionPolicy | None = None) -> None:
        self.policy = policy or FusionPolicy()

    @staticmethod
    def _unavailable(
        pose: EventEnvelope[PoseSample],
        quality: Quality,
        reason: ReasonCode,
    ) -> FusionOutcome:
        return FusionOutcome(pose.event_id, quality, (reason,), None)

    def fuse(
        self,
        pose: EventEnvelope[PoseSample],
        imu_events: Sequence[EventEnvelope[IMUSample]],
        *,
        now_monotonic_ns: int,
    ) -> FusionOutcome:
        if pose.event_type is not EventType.POSE_SAMPLE or pose.source is not Source.VISION:
            raise ValueError("fusion requires a vision pose event")
        if pose.quality is Quality.SIMULATED:
            raise ValueError("simulated pose cannot enter real fusion")
        for event in imu_events:
            if event.event_type is not EventType.IMU_SAMPLE or event.source is not Source.IMU:
                raise ValueError("fusion requires IMU source events")
            if event.quality is Quality.SIMULATED:
                raise ValueError("simulated IMU cannot enter real fusion")
        timestamps = [int(event.payload.captured_monotonic_ns) for event in imu_events]
        if timestamps != sorted(timestamps):
            raise ValueError("IMU capture timestamps must be ordered")

        pose_time = int(pose.payload.captured_monotonic_ns)
        if now_monotonic_ns < pose_time:
            return self._unavailable(pose, Quality.UNSYNCHRONIZED, ReasonCode.CLOCK_UNSYNCHRONIZED)
        if now_monotonic_ns - pose_time > self.policy.max_pose_age_ns:
            return self._unavailable(pose, Quality.VISION_DEGRADED, ReasonCode.POSE_STALE)
        if not imu_events:
            return self._unavailable(pose, Quality.UNAVAILABLE, ReasonCode.IMU_UNAVAILABLE)

        before = None
        after = None
        for event, captured_ns in zip(imu_events, timestamps):
            if captured_ns <= pose_time:
                before = event
            if captured_ns >= pose_time:
                after = event
                break
        if before is None or after is None:
            nearest_distance = min(abs(value - pose_time) for value in timestamps)
            reason = (
                ReasonCode.IMU_STALE
                if nearest_distance > self.policy.max_imu_neighbor_distance_ns
                else ReasonCode.IMU_UNAVAILABLE
            )
            return self._unavailable(pose, Quality.UNAVAILABLE, reason)

        before_time = int(before.payload.captured_monotonic_ns)
        after_time = int(after.payload.captured_monotonic_ns)
        if (
            max(pose_time - before_time, after_time - pose_time)
            > self.policy.max_imu_neighbor_distance_ns
            or after_time - before_time > self.policy.max_imu_bracket_span_ns
        ):
            return self._unavailable(pose, Quality.IMU_DEGRADED, ReasonCode.IMU_STALE)
        if (
            before.payload.boot_id != after.payload.boot_id
            or before.payload.clock_state is not ClockState.SYNCHRONIZED
            or after.payload.clock_state is not ClockState.SYNCHRONIZED
            or max(
                before.payload.estimated_clock_error_ns,
                after.payload.estimated_clock_error_ns,
            ) > self.policy.max_clock_error_ns
        ):
            return self._unavailable(
                pose, Quality.UNSYNCHRONIZED, ReasonCode.CLOCK_UNSYNCHRONIZED
            )
        if after.payload.gap_count_since_previous or (
            before is not after
            and after.payload.sequence != ((before.payload.sequence + 1) & 0xFFFF)
        ):
            return self._unavailable(
                pose, Quality.IMU_DEGRADED, ReasonCode.IMU_GAP_RATE_HIGH
            )
        if before.payload.calibration_version != after.payload.calibration_version:
            return self._unavailable(
                pose, Quality.IMU_DEGRADED, ReasonCode.CALIBRATION_REQUIRED
            )

        fraction = (
            (pose_time - before_time) / (after_time - before_time)
            if after_time > before_time
            else 0.0
        )

        def interpolate(
            first: tuple[float, float, float],
            last: tuple[float, float, float],
        ) -> tuple[float, float, float]:
            return (
                first[0] + (last[0] - first[0]) * fraction,
                first[1] + (last[1] - first[1]) * fraction,
                first[2] + (last[2] - first[2]) * fraction,
            )

        reasons: list[ReasonCode] = []
        if not pose.payload.landmarks:
            reasons.append(ReasonCode.POSE_NOT_FOUND)
        elif pose.quality is not Quality.GOOD:
            reasons.append(ReasonCode.POSE_LOW_VISIBILITY)
        if before.payload.calibration_version == 0:
            reasons.append(ReasonCode.CALIBRATION_REQUIRED)
        if pose.quality is not Quality.GOOD or not pose.payload.landmarks:
            quality = Quality.VISION_DEGRADED
        elif (
            before.quality is not Quality.GOOD
            or after.quality is not Quality.GOOD
            or before.payload.calibration_version == 0
        ):
            quality = Quality.IMU_DEGRADED
        else:
            quality = Quality.GOOD
        sample = FusedSample(
            pose_event_id=pose.event_id,
            captured_monotonic_ns=pose.payload.captured_monotonic_ns,
            interpolated_imu=InterpolatedIMU(
                acceleration_m_s2=interpolate(
                    before.payload.acceleration_m_s2,
                    after.payload.acceleration_m_s2,
                ),
                angular_velocity_rad_s=interpolate(
                    before.payload.angular_velocity_rad_s,
                    after.payload.angular_velocity_rad_s,
                ),
            ),
            imu_before_sequence=before.payload.sequence,
            imu_after_sequence=after.payload.sequence,
            alignment_error_ns=max(
                before.payload.estimated_clock_error_ns,
                after.payload.estimated_clock_error_ns,
            ),
            calibration_version=before.payload.calibration_version,
            quality=quality,
            quality_reasons=tuple(reasons),
        )
        return FusionOutcome(pose.event_id, quality, tuple(reasons), sample)
