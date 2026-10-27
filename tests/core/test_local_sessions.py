from __future__ import annotations

import asyncio
import os
import threading
from pathlib import Path
from uuid import UUID

import pytest

from digital_spotter.contracts import (
    ClockState,
    EventEnvelope,
    EventType,
    IMUSample,
    MonotonicNanoseconds,
    Quality,
    Source,
    new_event_id,
)
from digital_spotter.core import (
    DatabaseQueueFull,
    DatabaseWorkQueue,
    LocalSessionService,
    SessionInputError,
    SessionRuntimeState,
    SessionStartRequest,
    UnixIMUEventServer,
)
from digital_spotter.imu.uds import UnixEventPublisher
from digital_spotter.persistence import RepositoryError, SQLiteRepository, migrate_database
from digital_spotter.persistence.schema import connect_database


SESSION_ID = UUID("11111111-1111-4111-8111-111111111112")
EDGE_DEVICE_ID = "pi-r12-test"
IMU_DEVICE_ID = "dsimu-r9-test"


def _repository(tmp_path: Path) -> SQLiteRepository:
    path = tmp_path / "r12.sqlite3"
    migrate_database(path)
    return SQLiteRepository(path)


def _request() -> SessionStartRequest:
    return SessionStartRequest(
        session_uuid=SESSION_ID,
        edge_device_id=EDGE_DEVICE_ID,
        imu_device_id=IMU_DEVICE_ID,
        exercise_id=0,
        exercise_name="Barbell Back Squat",
        exercise_contract_version="squat-r12-test",
        started_monotonic_ns=1_000_000,
        created_utc_ms=1_750_000_000_000,
        model_package_id=None,
    )


def _imu_event(
    sequence: int,
    *,
    boot_id: int = 7,
    gap_count: int = 0,
    quality: Quality = Quality.IMU_DEGRADED,
    random_bits: int | None = None,
) -> EventEnvelope[IMUSample]:
    captured_ns = MonotonicNanoseconds(2_000_000 + sequence * 20_000)
    payload = IMUSample(
        device_id=IMU_DEVICE_ID,
        boot_id=boot_id,
        sequence=sequence,
        sensor_time_us=sequence * 20_000,
        captured_monotonic_ns=captured_ns,
        arrival_monotonic_ns=captured_ns,
        acceleration_m_s2=(0.0, 9.81, 0.0),
        angular_velocity_rad_s=(0.0, 0.0, 0.0),
        calibration_version=0,
        quality=quality,
        gap_count_since_previous=gap_count,
        estimated_clock_error_ns=50_000_000,
        clock_state=ClockState.ACQUIRING,
    )
    return EventEnvelope[IMUSample](
        event_type=EventType.IMU_SAMPLE,
        event_id=new_event_id(
            unix_time_ms=1_750_000_000_000 + sequence,
            random_bits=sequence if random_bits is None else random_bits,
        ),
        source=Source.IMU,
        device_id=IMU_DEVICE_ID,
        captured_monotonic_ns=captured_ns,
        created_monotonic_ns=captured_ns,
        quality=quality,
        payload=payload,
    )


def test_session_lifecycle_is_idempotent_bounded_and_summary_only(tmp_path):
    async def scenario() -> None:
        repository = _repository(tmp_path)
        service = LocalSessionService(repository=repository, imu_ring_capacity=3)

        assert await service.open() is None
        started = await service.begin(_request())
        repeated = await service.begin(_request())
        assert started.record.state == "active"
        assert repeated.already_existed is True

        for sequence in range(5):
            assert service.accept_imu(
                _imu_event(sequence, gap_count=2 if sequence == 3 else 0)
            )
        assert [event.payload.sequence for event in service.ring_snapshot()] == [2, 3, 4]

        checkpoint = await service.checkpoint(now_monotonic_ns=3_000_000)
        assert checkpoint is not None
        assert checkpoint.imu_summary.sample_count == 5
        assert checkpoint.imu_summary.gap_count == 2
        assert checkpoint.imu_summary.ring_eviction_count == 2
        assert checkpoint.imu_summary.degraded_sample_count == 5
        assert checkpoint.imu_summary.distinct_boot_count == 1

        stopped = await service.stop(
            session_uuid=SESSION_ID,
            ended_monotonic_ns=4_000_000,
            ended_utc_ms=1_750_000_001_000,
        )
        repeated_stop = await service.stop(
            session_uuid=SESSION_ID,
            ended_monotonic_ns=5_000_000,
            ended_utc_ms=1_750_000_002_000,
        )
        assert stopped.record.state == "completed"
        assert repeated_stop.already_existed is True
        assert repeated_stop.record.ended_monotonic_ns == 4_000_000
        repeated_start = await service.begin(_request())
        assert repeated_start.already_existed is True
        assert repeated_start.record.state == "completed"
        assert service.state is SessionRuntimeState.IDLE
        assert repository.counts() == {
            "sessions": 1,
            "session_imu_summaries": 1,
            "reps": 0,
            "analysis_events": 0,
            "outbox": 0,
        }
        await service.close()

    asyncio.run(scenario())


def test_active_session_restores_after_core_restart_without_duplicate(tmp_path):
    async def scenario() -> None:
        repository = _repository(tmp_path)
        first = LocalSessionService(repository=repository, imu_ring_capacity=4)
        await first.open()
        await first.begin(_request())
        first.accept_imu(_imu_event(1))
        first.accept_imu(_imu_event(2))
        await first.close(checkpoint_monotonic_ns=2_100_000)

        second = LocalSessionService(repository=repository, imu_ring_capacity=4)
        restored = await second.open()
        assert restored is not None
        assert restored.restored_after_restart is True
        assert restored.imu_summary.sample_count == 2
        assert restored.ring_size == 0
        assert (await second.begin(_request())).already_existed is True

        second.accept_imu(_imu_event(3))
        completed = await second.stop(
            session_uuid=SESSION_ID,
            ended_monotonic_ns=3_000_000,
            ended_utc_ms=1_750_000_003_000,
        )
        assert completed.imu_summary.sample_count == 3
        assert repository.counts()["sessions"] == 1
        await second.close()

    asyncio.run(scenario())


def test_wrong_or_simulated_imu_fails_closed_and_idle_input_is_ignored(tmp_path):
    async def scenario() -> None:
        repository = _repository(tmp_path)
        service = LocalSessionService(repository=repository)
        await service.open()
        assert service.accept_imu(_imu_event(1)) is False
        await service.begin(_request())

        simulated = _imu_event(2, quality=Quality.SIMULATED)
        with pytest.raises(SessionInputError, match="simulated"):
            service.accept_imu(simulated)
        raw = _imu_event(3).model_dump(mode="json")
        raw["device_id"] = "another-wearable"
        raw["payload"]["device_id"] = "another-wearable"
        wrong = EventEnvelope[IMUSample].model_validate(raw)
        with pytest.raises(SessionInputError, match="wrong wearable"):
            service.accept_imu(wrong)

        await service.stop(
            session_uuid=SESSION_ID,
            ended_monotonic_ns=4_000_000,
            ended_utc_ms=None,
        )
        await service.close()

    asyncio.run(scenario())


def test_storage_failure_does_not_report_session_completed(tmp_path):
    async def scenario() -> None:
        repository = _repository(tmp_path)
        service = LocalSessionService(repository=repository)
        await service.open()
        await service.begin(_request())
        service.accept_imu(_imu_event(1))
        connection = connect_database(repository.database_path)
        try:
            connection.execute(
                "CREATE TRIGGER reject_r12_summary BEFORE UPDATE "
                "ON session_imu_summaries "
                "BEGIN SELECT RAISE(ABORT, 'injected R12 failure'); END"
            )
        finally:
            connection.close()

        with pytest.raises(RepositoryError, match="completion transaction failed"):
            await service.stop(
                session_uuid=SESSION_ID,
                ended_monotonic_ns=3_000_000,
                ended_utc_ms=None,
            )
        assert service.state is SessionRuntimeState.STORAGE_DEGRADED
        assert repository.get_session(SESSION_ID).state == "active"
        assert service.accept_imu(_imu_event(2)) is True

        connection = connect_database(repository.database_path)
        try:
            connection.execute("DROP TRIGGER reject_r12_summary")
        finally:
            connection.close()
        await service.stop(
            session_uuid=SESSION_ID,
            ended_monotonic_ns=4_000_000,
            ended_utc_ms=None,
        )
        await service.close()

    asyncio.run(scenario())


def test_database_queue_is_bounded_and_runs_off_event_loop():
    async def scenario() -> None:
        queue = DatabaseWorkQueue(max_items=1)
        started = threading.Event()
        release = threading.Event()
        worker_thread_ids: list[int] = []

        def blocking_operation() -> int:
            worker_thread_ids.append(threading.get_ident())
            started.set()
            release.wait(timeout=2)
            return 1

        first = asyncio.create_task(queue.submit(blocking_operation))
        await asyncio.to_thread(started.wait, 1)
        second = asyncio.create_task(queue.submit(lambda: 2))
        await asyncio.sleep(0)
        with pytest.raises(DatabaseQueueFull):
            await queue.submit(lambda: 3)
        release.set()
        assert await first == 1
        assert await second == 2
        assert worker_thread_ids != [threading.get_ident()]
        assert queue.rejected_full == 1
        await queue.close()

    asyncio.run(scenario())


def test_r11_publisher_reaches_session_through_validated_uds(tmp_path):
    async def scenario() -> None:
        repository = _repository(tmp_path)
        service = LocalSessionService(repository=repository)
        await service.open()
        await service.begin(_request())
        received = asyncio.Event()

        def on_event(event: EventEnvelope[IMUSample]) -> bool:
            accepted = service.accept_imu(event)
            received.set()
            return accepted

        socket_path = tmp_path / "core-events.sock"
        server = UnixIMUEventServer(
            socket_path=socket_path,
            on_event=on_event,
            allowed_uids=frozenset({os.getuid()}),
        )
        publisher = UnixEventPublisher(socket_path)
        await server.start()
        await publisher.send(_imu_event(1))
        await asyncio.wait_for(received.wait(), timeout=1.0)

        counters = server.counters()
        assert counters.connections_accepted == 1
        assert counters.frames_received == 1
        assert counters.events_accepted == 1
        assert service.ring_snapshot()[0].payload.sequence == 1

        # Core shutdown must not wait forever for a still-connected producer.
        await asyncio.wait_for(server.close(), timeout=1.0)
        await publisher.close()
        await service.stop(
            session_uuid=SESSION_ID,
            ended_monotonic_ns=3_000_000,
            ended_utc_ms=None,
        )
        await service.close()

    asyncio.run(scenario())
