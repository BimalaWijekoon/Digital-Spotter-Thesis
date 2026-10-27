"""Authoritative local session lifecycle and bounded real-IMU ingestion."""

from __future__ import annotations

import asyncio
import re
from collections import deque
from dataclasses import dataclass
from enum import Enum
from uuid import UUID

from digital_spotter.contracts import (
    ClockState,
    EventEnvelope,
    EventType,
    IMUSample,
    PoseSample,
    Quality,
    Source,
)
from digital_spotter.core.database_queue import DatabaseWorkQueue
from digital_spotter.core.fusion import FusionEngine, FusionOutcome, FusionPolicy
from digital_spotter.core.rep_phases import CompletedRep, PHASE_NAMES, RepPhaseBuilder
from digital_spotter.persistence import (
    SessionIMUSummary,
    SessionRecord,
    SQLiteRepository,
)


_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{2,63}$")


class SessionError(RuntimeError):
    """Base failure for the canonical local session service."""


class SessionStateError(SessionError):
    """Raised when a lifecycle command is invalid for the current state."""


class SessionInputError(SessionError):
    """Raised when an event violates the active session contract."""


class SessionRuntimeState(str, Enum):
    IDLE = "idle"
    ACTIVE = "active"
    STOPPING = "stopping"
    STORAGE_DEGRADED = "storage_degraded"
    CLOSED = "closed"


@dataclass(frozen=True)
class SessionStartRequest:
    session_uuid: UUID
    edge_device_id: str
    imu_device_id: str
    exercise_id: int
    exercise_name: str
    exercise_contract_version: str
    started_monotonic_ns: int
    created_utc_ms: int | None
    model_package_id: str | None
    privacy_mode: str = "summary_only"

    def __post_init__(self) -> None:
        if not _SAFE_ID.fullmatch(self.edge_device_id):
            raise ValueError("edge_device_id must contain 3-64 safe characters")
        if not _SAFE_ID.fullmatch(self.imu_device_id):
            raise ValueError("imu_device_id must contain 3-64 safe characters")
        if self.exercise_id < 0:
            raise ValueError("exercise_id cannot be negative")
        if not self.exercise_name or len(self.exercise_name) > 128:
            raise ValueError("exercise_name must contain 1-128 characters")
        if (
            not self.exercise_contract_version
            or len(self.exercise_contract_version) > 64
        ):
            raise ValueError("exercise_contract_version must contain 1-64 characters")
        if self.model_package_id is not None and len(self.model_package_id) > 128:
            raise ValueError("model_package_id cannot exceed 128 characters")
        if self.started_monotonic_ns < 0:
            raise ValueError("started_monotonic_ns cannot be negative")
        if self.created_utc_ms is not None and self.created_utc_ms < 0:
            raise ValueError("created_utc_ms cannot be negative")
        if self.privacy_mode != "summary_only":
            raise ValueError("R12 supports summary_only persistence")


@dataclass(frozen=True)
class SessionView:
    record: SessionRecord
    imu_summary: SessionIMUSummary
    state: SessionRuntimeState
    ring_size: int
    ring_capacity: int
    restored_after_restart: bool
    already_existed: bool


@dataclass(frozen=True)
class PoseCaptureStats:
    """Ephemeral capture evidence; no raw pose is written to the R12 database."""

    session_uuid: UUID | None
    accepted_count: int
    degraded_count: int
    ring_evictions: int
    duplicate_count: int
    first_captured_monotonic_ns: int | None
    last_captured_monotonic_ns: int | None


class _PoseAccumulator:
    def __init__(self, *, session_uuid: UUID, ring_capacity: int) -> None:
        self.session_uuid = session_uuid
        self.ring: deque[EventEnvelope[PoseSample]] = deque(maxlen=ring_capacity)
        self._event_ids: set[UUID] = set()
        self.accepted_count = 0
        self.degraded_count = 0
        self.ring_evictions = 0
        self.duplicate_count = 0
        self.first_captured_monotonic_ns: int | None = None
        self.last_captured_monotonic_ns: int | None = None

    def accept(self, event: EventEnvelope[PoseSample]) -> bool:
        if event.event_id in self._event_ids:
            self.duplicate_count += 1
            return False
        captured_ns = int(event.payload.captured_monotonic_ns)
        if (
            self.last_captured_monotonic_ns is not None
            and captured_ns < self.last_captured_monotonic_ns
        ):
            raise SessionInputError("pose capture time moved backward")
        if len(self.ring) == self.ring.maxlen:
            evicted = self.ring.popleft()
            self._event_ids.remove(evicted.event_id)
            self.ring_evictions += 1
        self.ring.append(event)
        self._event_ids.add(event.event_id)
        self.accepted_count += 1
        if event.quality is not Quality.GOOD:
            self.degraded_count += 1
        if self.first_captured_monotonic_ns is None:
            self.first_captured_monotonic_ns = captured_ns
        self.last_captured_monotonic_ns = captured_ns
        return True

    def stats(self) -> PoseCaptureStats:
        return PoseCaptureStats(
            session_uuid=self.session_uuid,
            accepted_count=self.accepted_count,
            degraded_count=self.degraded_count,
            ring_evictions=self.ring_evictions,
            duplicate_count=self.duplicate_count,
            first_captured_monotonic_ns=self.first_captured_monotonic_ns,
            last_captured_monotonic_ns=self.last_captured_monotonic_ns,
        )


class _IMUAccumulator:
    def __init__(
        self,
        *,
        imu_device_id: str,
        ring_capacity: int,
        restored: SessionIMUSummary | None = None,
    ) -> None:
        self.imu_device_id = imu_device_id
        self.ring: deque[EventEnvelope[IMUSample]] = deque(maxlen=ring_capacity)
        self._ring_event_ids: set[UUID] = set()
        self.sample_count = restored.sample_count if restored else 0
        self.gap_count = restored.gap_count if restored else 0
        self.degraded_sample_count = restored.degraded_sample_count if restored else 0
        self.clock_reset_count = restored.clock_reset_count if restored else 0
        self.distinct_boot_count = restored.distinct_boot_count if restored else 0
        self.ring_eviction_count = restored.ring_eviction_count if restored else 0
        self.duplicate_event_count = restored.duplicate_event_count if restored else 0
        self.first_sequence = restored.first_sequence if restored else None
        self.last_sequence = restored.last_sequence if restored else None
        self.first_captured_monotonic_ns = (
            restored.first_captured_monotonic_ns if restored else None
        )
        self.last_captured_monotonic_ns = (
            restored.last_captured_monotonic_ns if restored else None
        )
        self.last_boot_id = restored.last_boot_id if restored else None

    @property
    def capacity(self) -> int:
        return self.ring.maxlen or 0

    def accept(self, event: EventEnvelope[IMUSample]) -> bool:
        payload = event.payload
        if event.event_id in self._ring_event_ids:
            self.duplicate_event_count += 1
            return False
        if (
            self.last_captured_monotonic_ns is not None
            and int(payload.captured_monotonic_ns) < self.last_captured_monotonic_ns
        ):
            raise SessionInputError("IMU capture time moved backward")
        if len(self.ring) == self.capacity:
            evicted = self.ring.popleft()
            self._ring_event_ids.remove(evicted.event_id)
            self.ring_eviction_count += 1
        self.ring.append(event)
        self._ring_event_ids.add(event.event_id)
        self.sample_count += 1
        self.gap_count += payload.gap_count_since_previous
        if event.quality is not Quality.GOOD:
            self.degraded_sample_count += 1
        if payload.clock_state is ClockState.RESET:
            self.clock_reset_count += 1
        if payload.boot_id != self.last_boot_id:
            self.distinct_boot_count += 1
            self.last_boot_id = payload.boot_id
        if self.first_sequence is None:
            self.first_sequence = payload.sequence
            self.first_captured_monotonic_ns = int(payload.captured_monotonic_ns)
        self.last_sequence = payload.sequence
        self.last_captured_monotonic_ns = int(payload.captured_monotonic_ns)
        return True

    def summary(self, *, updated_monotonic_ns: int) -> SessionIMUSummary:
        return SessionIMUSummary(
            imu_device_id=self.imu_device_id,
            sample_count=self.sample_count,
            gap_count=self.gap_count,
            degraded_sample_count=self.degraded_sample_count,
            clock_reset_count=self.clock_reset_count,
            distinct_boot_count=self.distinct_boot_count,
            ring_eviction_count=self.ring_eviction_count,
            duplicate_event_count=self.duplicate_event_count,
            last_boot_id=self.last_boot_id,
            first_sequence=self.first_sequence,
            last_sequence=self.last_sequence,
            first_captured_monotonic_ns=self.first_captured_monotonic_ns,
            last_captured_monotonic_ns=self.last_captured_monotonic_ns,
            updated_monotonic_ns=updated_monotonic_ns,
        )


class LocalSessionService:
    """Own local session state while keeping high-rate ingestion non-blocking."""

    def __init__(
        self,
        *,
        repository: SQLiteRepository,
        database_queue: DatabaseWorkQueue | None = None,
        imu_ring_capacity: int = 250,
        pose_ring_capacity: int = 4,
        fusion_policy: FusionPolicy | None = None,
        rep_fps: int = 30,
        rep_frame_capacity: int = 300,
    ) -> None:
        if not 2 <= imu_ring_capacity <= 5000:
            raise ValueError("IMU ring capacity must be between 2 and 5000")
        if not 1 <= pose_ring_capacity <= 16:
            raise ValueError("pose ring capacity must be between 1 and 16")
        self.repository = repository
        self.database_queue = database_queue or DatabaseWorkQueue(max_items=256)
        self.imu_ring_capacity = imu_ring_capacity
        self.pose_ring_capacity = pose_ring_capacity
        self.rep_fps = rep_fps
        self.rep_frame_capacity = rep_frame_capacity
        self._fusion_engine = FusionEngine(fusion_policy)
        self._record: SessionRecord | None = None
        self._accumulator: _IMUAccumulator | None = None
        self._pose_accumulator: _PoseAccumulator | None = None
        self._rep_builder: RepPhaseBuilder | None = None
        self._restored_after_restart = False
        self._accepting_imu = False
        self._accepting_pose = False
        self._state = SessionRuntimeState.IDLE
        self._lock = asyncio.Lock()

    @property
    def state(self) -> SessionRuntimeState:
        return self._state

    @property
    def active_session_uuid(self) -> UUID | None:
        return self._record.session_uuid if self._record is not None else None

    async def open(self) -> SessionView | None:
        async with self._lock:
            if self._state is SessionRuntimeState.CLOSED:
                raise SessionStateError("session service is closed")
            await self.database_queue.start()
            record = await self.database_queue.submit(self.repository.get_active_session)
            if record is None:
                return None
            summary = await self.database_queue.submit(
                lambda: self.repository.get_session_imu_summary(record.session_uuid)
            )
            if summary is None:
                raise SessionStateError("active session has no durable IMU summary")
            self._record = record
            self._accumulator = _IMUAccumulator(
                imu_device_id=summary.imu_device_id,
                ring_capacity=self.imu_ring_capacity,
                restored=summary,
            )
            self._pose_accumulator = _PoseAccumulator(
                session_uuid=record.session_uuid,
                ring_capacity=self.pose_ring_capacity,
            )
            self._rep_builder = self._new_rep_builder(record)
            self._restored_after_restart = True
            self._accepting_imu = True
            self._accepting_pose = True
            self._state = SessionRuntimeState.ACTIVE
            return self._view(already_existed=True)

    async def begin(self, request: SessionStartRequest) -> SessionView:
        async with self._lock:
            self._require_open()
            if self._record is not None:
                if self._matches(request):
                    return self._view(already_existed=True)
                raise SessionStateError("another session is already active")
            accumulator = _IMUAccumulator(
                imu_device_id=request.imu_device_id,
                ring_capacity=self.imu_ring_capacity,
            )
            initial_summary = accumulator.summary(
                updated_monotonic_ns=request.started_monotonic_ns
            )
            try:
                await self.database_queue.submit(
                    lambda: self.repository.create_session(
                        session_uuid=request.session_uuid,
                        device_id=request.edge_device_id,
                        exercise_id=request.exercise_id,
                        exercise_name=request.exercise_name,
                        exercise_contract_version=request.exercise_contract_version,
                        started_monotonic_ns=request.started_monotonic_ns,
                        created_utc_ms=request.created_utc_ms,
                        model_package_id=request.model_package_id,
                        privacy_mode=request.privacy_mode,
                        initial_imu_summary=initial_summary,
                    )
                )
                record = await self.database_queue.submit(
                    lambda: self.repository.get_session(request.session_uuid)
                )
            except Exception:
                self._state = SessionRuntimeState.STORAGE_DEGRADED
                raise
            if record is None:
                self._state = SessionRuntimeState.STORAGE_DEGRADED
                raise SessionStateError("durable session record is unavailable")
            if record.state == "completed":
                stored_summary = await self.database_queue.submit(
                    lambda: self.repository.get_session_imu_summary(
                        request.session_uuid
                    )
                )
                if stored_summary is None:
                    self._state = SessionRuntimeState.STORAGE_DEGRADED
                    raise SessionStateError("completed session has no IMU summary")
                self._state = SessionRuntimeState.IDLE
                return SessionView(
                    record=record,
                    imu_summary=stored_summary,
                    state=SessionRuntimeState.IDLE,
                    ring_size=0,
                    ring_capacity=self.imu_ring_capacity,
                    restored_after_restart=False,
                    already_existed=True,
                )
            if record.state != "active":
                raise SessionStateError(
                    f"session cannot start from durable state {record.state}"
                )
            self._record = record
            self._accumulator = accumulator
            self._pose_accumulator = _PoseAccumulator(
                session_uuid=record.session_uuid,
                ring_capacity=self.pose_ring_capacity,
            )
            self._rep_builder = self._new_rep_builder(record)
            self._restored_after_restart = False
            self._accepting_imu = True
            self._accepting_pose = True
            self._state = SessionRuntimeState.ACTIVE
            return self._view(already_existed=False)

    def accept_imu(self, event: EventEnvelope[IMUSample]) -> bool:
        if self._record is None or self._accumulator is None or not self._accepting_imu:
            return False
        if event.event_type is not EventType.IMU_SAMPLE or event.source is not Source.IMU:
            raise SessionInputError("session accepts only IMU source events")
        if event.quality is Quality.SIMULATED:
            raise SessionInputError("simulated IMU cannot enter a real local session")
        if event.device_id != event.payload.device_id:
            raise SessionInputError("IMU envelope and payload device IDs differ")
        if event.payload.device_id != self._accumulator.imu_device_id:
            raise SessionInputError("IMU event is from the wrong wearable")
        return self._accumulator.accept(event)

    def accept_pose(self, event: EventEnvelope[PoseSample]) -> bool:
        if self._record is None or self._pose_accumulator is None or not self._accepting_pose:
            return False
        if event.event_type is not EventType.POSE_SAMPLE or event.source is not Source.VISION:
            raise SessionInputError("session accepts only vision pose events")
        if event.quality is Quality.SIMULATED:
            raise SessionInputError("simulated pose cannot enter a real local session")
        if event.device_id is not None and event.device_id != self._record.device_id:
            raise SessionInputError("pose event is from the wrong edge device")
        accepted = self._pose_accumulator.accept(event)
        if accepted and self._rep_builder is not None:
            self._rep_builder.add(event)
        return accepted

    def poll_completed_reps(self) -> tuple[CompletedRep, ...]:
        """Build completed research reps outside the high-rate capture callback."""
        if (
            self._state is not SessionRuntimeState.ACTIVE
            or self._rep_builder is None
            or self._accumulator is None
        ):
            return ()
        return self._rep_builder.poll(tuple(self._accumulator.ring))

    def pose_snapshot(self) -> tuple[EventEnvelope[PoseSample], ...]:
        if self._pose_accumulator is None:
            return ()
        return tuple(self._pose_accumulator.ring)

    def discard_partial_rep(self) -> None:
        """Explicit capture pause boundary; retain the completed-rep cursor."""
        if self._rep_builder is not None:
            self._rep_builder.discard_partial_rep()

    def pose_stats(self) -> PoseCaptureStats:
        if self._pose_accumulator is None:
            return PoseCaptureStats(None, 0, 0, 0, 0, None, None)
        return self._pose_accumulator.stats()

    def fuse_latest_pose(self, *, now_monotonic_ns: int) -> FusionOutcome | None:
        """Associate the newest pose with bounded session IMU history on demand."""
        if self._record is None or self._pose_accumulator is None or not self._pose_accumulator.ring:
            return None
        imu_events = self._accumulator.ring if self._accumulator is not None else ()
        return self._fusion_engine.fuse(
            self._pose_accumulator.ring[-1],
            imu_events,
            now_monotonic_ns=now_monotonic_ns,
        )

    async def checkpoint(self, *, now_monotonic_ns: int) -> SessionView | None:
        if now_monotonic_ns < 0:
            raise ValueError("checkpoint time cannot be negative")
        async with self._lock:
            self._require_open()
            if self._record is None or self._accumulator is None:
                return None
            summary = self._accumulator.summary(updated_monotonic_ns=now_monotonic_ns)
            try:
                await self.database_queue.submit(
                    lambda: self.repository.checkpoint_session_imu(
                        session_uuid=self._record.session_uuid,
                        summary=summary,
                    )
                )
            except Exception:
                self._state = SessionRuntimeState.STORAGE_DEGRADED
                raise
            self._state = SessionRuntimeState.ACTIVE
            return self._view(already_existed=False)

    async def stop(
        self,
        *,
        session_uuid: UUID,
        ended_monotonic_ns: int,
        ended_utc_ms: int | None,
    ) -> SessionView:
        async with self._lock:
            self._require_open()
            if self._record is None or self._accumulator is None:
                record = await self.database_queue.submit(
                    lambda: self.repository.get_session(session_uuid)
                )
                if record is None or record.state != "completed":
                    raise SessionStateError("session is not active")
                summary = await self.database_queue.submit(
                    lambda: self.repository.get_session_imu_summary(session_uuid)
                )
                if summary is None:
                    raise SessionStateError("completed session has no IMU summary")
                return SessionView(
                    record=record,
                    imu_summary=summary,
                    state=SessionRuntimeState.IDLE,
                    ring_size=0,
                    ring_capacity=self.imu_ring_capacity,
                    restored_after_restart=False,
                    already_existed=True,
                )
            if self._record.session_uuid != session_uuid:
                raise SessionStateError("stop session UUID does not match active session")
            self._accepting_imu = False
            self._accepting_pose = False
            self._state = SessionRuntimeState.STOPPING
            summary = self._accumulator.summary(updated_monotonic_ns=ended_monotonic_ns)
            try:
                completed = await self.database_queue.submit(
                    lambda: self.repository.complete_session(
                        session_uuid=session_uuid,
                        ended_monotonic_ns=ended_monotonic_ns,
                        ended_utc_ms=ended_utc_ms,
                        summary=summary,
                    )
                )
            except Exception:
                self._accepting_imu = True
                self._accepting_pose = True
                self._state = SessionRuntimeState.STORAGE_DEGRADED
                raise
            view = SessionView(
                record=completed,
                imu_summary=summary,
                state=SessionRuntimeState.IDLE,
                ring_size=len(self._accumulator.ring),
                ring_capacity=self.imu_ring_capacity,
                restored_after_restart=self._restored_after_restart,
                already_existed=False,
            )
            self._record = None
            self._accumulator = None
            self._pose_accumulator = None
            self._rep_builder = None
            self._restored_after_restart = False
            self._state = SessionRuntimeState.IDLE
            return view

    def ring_snapshot(self) -> tuple[EventEnvelope[IMUSample], ...]:
        if self._accumulator is None:
            return ()
        return tuple(self._accumulator.ring)

    def _new_rep_builder(self, record: SessionRecord) -> RepPhaseBuilder | None:
        if record.exercise_id not in PHASE_NAMES:
            return None
        return RepPhaseBuilder(
            session_uuid=record.session_uuid,
            exercise_id=record.exercise_id,
            fps=self.rep_fps,
            exercise_contract_version=record.exercise_contract_version,
            max_frames=self.rep_frame_capacity,
        )

    async def close(self, *, checkpoint_monotonic_ns: int | None = None) -> None:
        if self._state is SessionRuntimeState.CLOSED:
            return
        if self._record is not None:
            if checkpoint_monotonic_ns is None:
                raise SessionStateError("active session requires a shutdown checkpoint time")
            await self.checkpoint(now_monotonic_ns=checkpoint_monotonic_ns)
        self._accepting_imu = False
        self._accepting_pose = False
        self._state = SessionRuntimeState.CLOSED
        await self.database_queue.close()

    def _view(self, *, already_existed: bool) -> SessionView:
        if self._record is None or self._accumulator is None:
            raise SessionStateError("no active session")
        updated_ns = (
            self._accumulator.last_captured_monotonic_ns
            or self._record.started_monotonic_ns
        )
        return SessionView(
            record=self._record,
            imu_summary=self._accumulator.summary(updated_monotonic_ns=updated_ns),
            state=self._state,
            ring_size=len(self._accumulator.ring),
            ring_capacity=self.imu_ring_capacity,
            restored_after_restart=self._restored_after_restart,
            already_existed=already_existed,
        )

    def _matches(self, request: SessionStartRequest) -> bool:
        if self._record is None or self._accumulator is None:
            return False
        return (
            self._record.session_uuid == request.session_uuid
            and self._record.device_id == request.edge_device_id
            and self._accumulator.imu_device_id == request.imu_device_id
            and self._record.exercise_id == request.exercise_id
            and self._record.exercise_name == request.exercise_name
            and self._record.exercise_contract_version
            == request.exercise_contract_version
            and self._record.started_monotonic_ns == request.started_monotonic_ns
            and self._record.created_utc_ms == request.created_utc_ms
            and self._record.model_package_id == request.model_package_id
            and self._record.privacy_mode == request.privacy_mode
        )

    def _require_open(self) -> None:
        if self._state is SessionRuntimeState.CLOSED:
            raise SessionStateError("session service is closed")
