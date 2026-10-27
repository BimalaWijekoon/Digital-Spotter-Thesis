"""The research status boundary must never present unverified V5 scores."""

from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

from digital_spotter.contracts import Quality
from digital_spotter.core.research_status import ResearchStatusProjector
from digital_spotter.core.sessions import SessionRuntimeState


class SessionStub:
    def __init__(self) -> None:
        self.state = SessionRuntimeState.IDLE
        self.active_session_uuid = None
        self.imu_events = ()
        self.pose_events = ()
        self.completed = ()

    def ring_snapshot(self):
        return self.imu_events

    def pose_snapshot(self):
        return self.pose_events

    def poll_completed_reps(self):
        result, self.completed = self.completed, ()
        return result


def test_no_session_or_sensor_is_not_presented_as_live_analysis():
    status = ResearchStatusProjector(SessionStub()).refresh(now_monotonic_ns=3_000_000_000)

    assert status["session"] == {"state": "idle", "rep_count": 0}
    assert status["wearable"]["state"] == "unavailable"
    assert status["camera"]["state"] == "unavailable"
    assert status["analysis"] == {
        "state": "unavailable",
        "reason": "v5_live_feature_contract_unverified",
    }
    assert status["latest_rep"] is None
    assert "probability" not in str(status)


def test_recent_degraded_sensors_and_completed_rep_remain_unscored():
    session = SessionStub()
    session.state = SessionRuntimeState.ACTIVE
    session.active_session_uuid = uuid4()
    session.imu_events = (SimpleNamespace(payload=SimpleNamespace(
        arrival_monotonic_ns=2_900_000_000, quality=Quality.IMU_DEGRADED,
    )),)
    session.pose_events = (SimpleNamespace(payload=SimpleNamespace(
        processed_monotonic_ns=2_900_000_000, quality=Quality.VISION_DEGRADED,
    )),)
    session.completed = (SimpleNamespace(event=SimpleNamespace(
        rep_id=uuid4(), rep_number=1, quality=Quality.UNAVAILABLE,
    )),)
    projector = ResearchStatusProjector(session)

    status = projector.refresh(now_monotonic_ns=3_000_000_000)
    assert status["session"]["rep_count"] == 1
    assert status["latest_rep"] == {"number": 1, "quality": "unavailable"}
    assert status["wearable"]["state"] == "degraded"
    assert status["camera"]["state"] == "degraded"
    assert status["analysis"]["state"] == "unavailable"
    assert projector.refresh(now_monotonic_ns=5_100_000_000)["wearable"]["state"] == "stale"
    assert projector.refresh(now_monotonic_ns=5_100_000_000)["session"]["rep_count"] == 1


def test_status_count_resets_for_new_session():
    session = SessionStub()
    session.state = SessionRuntimeState.ACTIVE
    session.active_session_uuid = uuid4()
    session.completed = (SimpleNamespace(event=SimpleNamespace(
        rep_id=uuid4(), rep_number=1, quality=Quality.GOOD,
    )),)
    projector = ResearchStatusProjector(session)
    assert projector.refresh(now_monotonic_ns=1)["session"]["rep_count"] == 1

    session.active_session_uuid = uuid4()
    assert projector.refresh(now_monotonic_ns=2)["session"]["rep_count"] == 0
    assert projector.refresh(now_monotonic_ns=2)["latest_rep"] is None


def test_explicit_completed_reps_do_not_poll_session_twice():
    session = SessionStub()
    session.state = SessionRuntimeState.ACTIVE
    session.active_session_uuid = uuid4()
    explicit = SimpleNamespace(event=SimpleNamespace(
        rep_id=uuid4(), rep_number=1, quality=Quality.GOOD,
    ))
    session.completed = (SimpleNamespace(event=SimpleNamespace(
        rep_id=uuid4(), rep_number=99, quality=Quality.GOOD,
    )),)

    status = ResearchStatusProjector(session).refresh(
        now_monotonic_ns=1, completed_reps=(explicit,)
    )

    assert status["session"]["rep_count"] == 1
    assert session.completed[0].event.rep_number == 99


def test_imu_window_is_bounded_and_uses_real_sensor_vectors():
    session = SessionStub()
    session.state = SessionRuntimeState.ACTIVE
    session.active_session_uuid = uuid4()
    session.imu_events = tuple(SimpleNamespace(payload=SimpleNamespace(
        boot_id=1 if index < 2 else 2,
        sequence=index,
        captured_monotonic_ns=1_000_000_000 + index * 20_000_000,
        arrival_monotonic_ns=1_000_000_000 + index * 20_000_000,
        acceleration_m_s2=(float(index), 2.0, 3.0),
        angular_velocity_rad_s=(0.1, 0.2, 0.3),
        quality=Quality.IMU_DEGRADED,
    )) for index in range(4))

    window = ResearchStatusProjector(session).imu_window(now_monotonic_ns=1_100_000_000)

    assert window["version"] == "research_imu_window_v1"
    assert window["state"] == "degraded"
    assert [point["sequence"] for point in window["samples"]] == [2, 3]
    assert window["samples"][-1]["acceleration_m_s2"] == [3.0, 2.0, 3.0]
    assert window["samples"][-1]["angular_velocity_rad_s"] == [0.1, 0.2, 0.3]
    assert ResearchStatusProjector(session).imu_window(now_monotonic_ns=4_000_000_000)["state"] == "stale"
