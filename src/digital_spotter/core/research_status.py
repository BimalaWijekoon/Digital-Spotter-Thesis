"""Read-only, explicitly unscored research status from the canonical session."""

from __future__ import annotations

from digital_spotter.contracts import Quality
from digital_spotter.core.rep_phases import CompletedRep
from digital_spotter.core.sessions import LocalSessionService, SessionRuntimeState


STATUS_VERSION = "research_status_v1"
IMU_WINDOW_VERSION = "research_imu_window_v1"
IMU_WINDOW_SAMPLES = 100
STALE_AFTER_NS = 2_000_000_000
UNVERIFIED_V5_REASON = "v5_live_feature_contract_unverified"


def _sensor_state(*, timestamp_ns: int | None, quality: Quality | None, now_ns: int) -> str:
    if timestamp_ns is None or quality is None:
        return "unavailable"
    age_ns = now_ns - timestamp_ns
    if age_ns < 0 or age_ns > STALE_AFTER_NS:
        return "stale"
    return "receiving" if quality is Quality.GOOD else "degraded"


class ResearchStatusProjector:
    """Project completed reps once; expose only truthful local display state.

    This projection is process-local. It neither authorizes V5 inference nor
    persists a scored result. The caller invokes ``refresh`` outside capture
    callbacks on the same event loop that owns ``LocalSessionService``. A caller
    may pass already-polled reps so an opt-in research observer sees them too.
    """

    def __init__(self, session: LocalSessionService) -> None:
        self.session = session
        self._session_uuid = None
        self._rep_count = 0
        self._latest_rep: dict[str, int | str] | None = None

    def refresh(
        self,
        *,
        now_monotonic_ns: int,
        completed_reps: tuple[CompletedRep, ...] | None = None,
    ) -> dict[str, object]:
        if now_monotonic_ns < 0:
            raise ValueError("status time cannot be negative")
        current_uuid = self.session.active_session_uuid
        if current_uuid != self._session_uuid:
            self._session_uuid = current_uuid
            self._rep_count = 0
            self._latest_rep = None

        if current_uuid is not None and self.session.state is SessionRuntimeState.ACTIVE:
            if completed_reps is None:
                completed_reps = self.session.poll_completed_reps()
            for completed in completed_reps:
                event = completed.event
                if event.rep_number > self._rep_count:
                    self._rep_count = event.rep_number
                    self._latest_rep = {
                        "number": event.rep_number,
                        "quality": event.quality.value,
                    }

        imu_events = self.session.ring_snapshot() if current_uuid is not None else ()
        pose_events = self.session.pose_snapshot() if current_uuid is not None else ()
        latest_imu = imu_events[-1].payload if imu_events else None
        latest_pose = pose_events[-1].payload if pose_events else None
        return {
            "version": STATUS_VERSION,
            "session": {
                "state": self.session.state.value,
                "rep_count": self._rep_count,
            },
            "wearable": {
                "state": _sensor_state(
                    timestamp_ns=(int(latest_imu.arrival_monotonic_ns) if latest_imu else None),
                    quality=(latest_imu.quality if latest_imu else None),
                    now_ns=now_monotonic_ns,
                ),
            },
            "camera": {
                "state": _sensor_state(
                    timestamp_ns=(int(latest_pose.processed_monotonic_ns) if latest_pose else None),
                    quality=(latest_pose.quality if latest_pose else None),
                    now_ns=now_monotonic_ns,
                ),
            },
            "analysis": {
                "state": "unavailable",
                "reason": UNVERIFIED_V5_REASON,
            },
            "latest_rep": self._latest_rep,
        }

    def imu_window(self, *, now_monotonic_ns: int) -> dict[str, object]:
        """Return a small display-only window from the canonical IMU ring."""
        events = self.session.ring_snapshot() if self.session.active_session_uuid else ()
        latest = events[-1].payload if events else None
        state = _sensor_state(
            timestamp_ns=(int(latest.arrival_monotonic_ns) if latest else None),
            quality=(latest.quality if latest else None),
            now_ns=now_monotonic_ns,
        )
        samples = []
        if state in ("receiving", "degraded") and latest is not None:
            for event in events[-IMU_WINDOW_SAMPLES:]:
                sample = event.payload
                if sample.boot_id != latest.boot_id or (
                    now_monotonic_ns - int(sample.arrival_monotonic_ns) > STALE_AFTER_NS
                ):
                    continue
                samples.append({
                    "sequence": int(sample.sequence),
                    "t_ms": round((int(sample.captured_monotonic_ns) - int(latest.captured_monotonic_ns)) / 1_000_000, 2),
                    "acceleration_m_s2": [round(value, 3) for value in sample.acceleration_m_s2],
                    "angular_velocity_rad_s": [round(value, 3) for value in sample.angular_velocity_rad_s],
                })
        return {"version": IMU_WINDOW_VERSION, "state": state, "samples": samples}
