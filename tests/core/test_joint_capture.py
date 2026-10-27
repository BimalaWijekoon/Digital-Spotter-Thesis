"""The first core join consumes real-shaped IMU and pose events without scoring."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from uuid import UUID

import pytest

from digital_spotter.contracts import (
    ClockState,
    EventEnvelope,
    EventType,
    HealthState,
    IMUSample,
    MonotonicNanoseconds,
    PoseSample,
    Quality,
    ReasonCode,
    Source,
    ComponentState,
    new_event_id,
)
from digital_spotter.core import (
    LocalSessionService,
    SessionInputError,
    SessionStartRequest,
    UnixIMUEventServer,
    UnixVisionEventServer,
)
from digital_spotter.imu.uds import UnixEventPublisher
from digital_spotter.persistence import SQLiteRepository, migrate_database


SESSION_ID = UUID("21111111-1111-4111-8111-111111111112")
EDGE_ID = "pi-joint-test"
IMU_ID = "dsimu-r9-test"


def _event_id(number: int) -> UUID:
    return new_event_id(unix_time_ms=1_750_000_000_000 + number, random_bits=number)


def _request() -> SessionStartRequest:
    return SessionStartRequest(
        session_uuid=SESSION_ID,
        edge_device_id=EDGE_ID,
        imu_device_id=IMU_ID,
        exercise_id=0,
        exercise_name="Joint capture check",
        exercise_contract_version="joint-capture-1",
        started_monotonic_ns=1_000_000,
        created_utc_ms=None,
        model_package_id=None,
    )


def _imu_event(number: int) -> EventEnvelope[IMUSample]:
    captured = MonotonicNanoseconds(2_000_000 + number * 20_000_000)
    sample = IMUSample(
        device_id=IMU_ID,
        boot_id=1,
        sequence=number,
        sensor_time_us=number * 20_000,
        captured_monotonic_ns=captured,
        arrival_monotonic_ns=captured,
        acceleration_m_s2=(0.0, 9.81, 0.0),
        angular_velocity_rad_s=(0.0, 0.0, 0.0),
        calibration_version=0,
        quality=Quality.IMU_DEGRADED,
        gap_count_since_previous=0,
        estimated_clock_error_ns=1_000_000,
        clock_state=ClockState.SYNCHRONIZED,
    )
    return EventEnvelope[IMUSample](
        event_type=EventType.IMU_SAMPLE,
        event_id=_event_id(number),
        source=Source.IMU,
        device_id=IMU_ID,
        captured_monotonic_ns=captured,
        created_monotonic_ns=captured,
        quality=sample.quality,
        payload=sample,
    )


def _pose_event(number: int, *, quality: Quality = Quality.VISION_DEGRADED) -> EventEnvelope[PoseSample]:
    captured = MonotonicNanoseconds(2_500_000 + number * 33_000_000)
    sample = PoseSample(
        camera_id="picamera2-imx219",
        frame_sequence=number,
        captured_monotonic_ns=captured,
        processed_monotonic_ns=MonotonicNanoseconds(int(captured) + 1_000_000),
        image_width=640,
        image_height=480,
        landmark_schema_version=1,
        landmarks=(),
        angles={},
        pose_confidence=0.0,
        quality=quality,
        processing_latency_ns=1_000_000,
    )
    return EventEnvelope[PoseSample](
        event_type=EventType.POSE_SAMPLE,
        event_id=_event_id(100 + number),
        source=Source.VISION,
        device_id=EDGE_ID,
        captured_monotonic_ns=captured,
        created_monotonic_ns=sample.processed_monotonic_ns,
        quality=quality,
        payload=sample,
    )


def _health_event() -> EventEnvelope[HealthState]:
    captured = MonotonicNanoseconds(3_000_000)
    health = HealthState(
        component="vision",
        state=ComponentState.DEGRADED,
        since_monotonic_ns=captured,
        is_simulated=False,
    )
    return EventEnvelope[HealthState](
        event_type=EventType.HEALTH_STATE,
        event_id=_event_id(900),
        source=Source.VISION,
        device_id=EDGE_ID,
        created_monotonic_ns=captured,
        quality=Quality.VISION_DEGRADED,
        payload=health,
    )


def _repository(tmp_path: Path) -> SQLiteRepository:
    path = tmp_path / "joint.sqlite3"
    migrate_database(path)
    return SQLiteRepository(path)


def test_one_core_session_receives_both_existing_uds_streams(tmp_path: Path) -> None:
    async def scenario() -> None:
        repository = _repository(tmp_path)
        service = LocalSessionService(repository=repository, pose_ring_capacity=2)
        await service.open()
        await service.begin(_request())
        imu_server = UnixIMUEventServer(
            socket_path=tmp_path / "imu.sock",
            on_event=service.accept_imu,
            allowed_uids=frozenset({os.getuid()}),
        )
        vision_server = UnixVisionEventServer(
            socket_path=tmp_path / "vision.sock",
            on_pose=service.accept_pose,
            allowed_uids=frozenset({os.getuid()}),
        )
        imu_sender = UnixEventPublisher(tmp_path / "imu.sock")
        vision_sender = UnixEventPublisher(tmp_path / "vision.sock")
        await imu_server.start()
        await vision_server.start()
        try:
            await imu_sender.send(_imu_event(1))
            await vision_sender.send(_pose_event(1))
            await vision_sender.send(_health_event())
            await vision_sender.send(_pose_event(2))
            await vision_sender.send(_pose_event(3))
            async with asyncio.timeout(1):
                while vision_server.counters().frames_received < 4 or imu_server.counters().frames_received < 1:
                    await asyncio.sleep(0.01)
            assert imu_server.counters().events_accepted == 1
            assert vision_server.counters().poses_accepted == 3
            assert vision_server.counters().health_ignored == 1
            assert [event.payload.frame_sequence for event in service.pose_snapshot()] == [2, 3]
            assert service.pose_stats().ring_evictions == 1
            assert service.pose_stats().degraded_count == 3
            assert service.pose_stats().session_uuid == SESSION_ID
            assert service.ring_snapshot()[0].payload.sequence == 1
            assert service.active_session_uuid == SESSION_ID
            fusion = service.fuse_latest_pose(now_monotonic_ns=120_000_000)
            assert fusion is not None
            assert fusion.sample is None
            assert ReasonCode.IMU_STALE in fusion.reasons
        finally:
            await imu_sender.close()
            await vision_sender.close()
            await asyncio.wait_for(imu_server.close(), timeout=1)
            await asyncio.wait_for(vision_server.close(), timeout=1)
            await service.stop(session_uuid=SESSION_ID, ended_monotonic_ns=200_000_000, ended_utc_ms=None)
            await service.close()
        assert repository.counts()["sessions"] == 1
        assert repository.counts()["analysis_events"] == 0
        assert repository.get_session_imu_summary(SESSION_ID).sample_count == 1

    asyncio.run(scenario())


def test_pose_input_fails_closed_and_is_not_reused_between_sessions(tmp_path: Path) -> None:
    async def scenario() -> None:
        service = LocalSessionService(repository=_repository(tmp_path))
        await service.open()
        assert service.accept_pose(_pose_event(1)) is False
        await service.begin(_request())
        assert service.accept_pose(_pose_event(1)) is True
        with pytest.raises(SessionInputError, match="simulated"):
            service.accept_pose(_pose_event(2, quality=Quality.SIMULATED))
        wrong = _pose_event(2).model_copy(update={"device_id": "another-pi"})
        with pytest.raises(SessionInputError, match="wrong edge device"):
            service.accept_pose(wrong)
        assert service.pose_stats().accepted_count == 1
        await service.stop(session_uuid=SESSION_ID, ended_monotonic_ns=200_000_000, ended_utc_ms=None)
        assert service.pose_snapshot() == ()
        await service.close()

    asyncio.run(scenario())
