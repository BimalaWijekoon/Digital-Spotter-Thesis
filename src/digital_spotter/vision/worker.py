"""Adapter-injected, bounded latest-frame vision worker."""

from __future__ import annotations

import re
import threading
from dataclasses import dataclass
from enum import Enum
from typing import Callable, Protocol
from uuid import UUID

from digital_spotter.contracts import (
    ComponentState,
    EventEnvelope,
    HealthState,
    PoseSample,
    ReasonCode,
)
from digital_spotter.contracts.time import MonotonicClock
from digital_spotter.vision.errors import VisionAdapterError
from digital_spotter.vision.frames import CameraFrame
from digital_spotter.vision.health import (
    VisionHealthSnapshot,
    build_vision_health_envelope,
)
from digital_spotter.vision.pose_events import (
    PoseEvaluation,
    build_pose_envelope,
    build_pose_sample,
)


_SAFE_CAMERA_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


class VisionFrameSource(Protocol):
    mode: str
    is_real: bool
    is_simulated: bool

    @property
    def exhausted(self) -> bool: ...

    def start(self) -> None: ...
    def read(self, timeout_s: float) -> tuple[CameraFrame, int] | None: ...
    def stop(self) -> None: ...


class PoseEvaluator(Protocol):
    mode: str
    is_real: bool
    is_simulated: bool

    def evaluate(self, frame: CameraFrame) -> PoseEvaluation: ...
    def close(self) -> None: ...


class PoseEventSink(Protocol):
    def publish(self, event: EventEnvelope[PoseSample]) -> None: ...


class HealthEventSink(Protocol):
    def publish(self, event: EventEnvelope[HealthState]) -> None: ...


class VisionWorkerState(str, Enum):
    IDLE = "idle"
    RUNNING = "running"
    STOPPED = "stopped"
    FAILED = "failed"


@dataclass(frozen=True)
class VisionWorkerConfig:
    camera_id: str
    device_id: str | None = None
    minimum_confidence: float = 0.5
    read_timeout_s: float = 1.0
    health_interval_s: float = 1.0

    def __post_init__(self) -> None:
        if not _SAFE_CAMERA_ID.fullmatch(self.camera_id):
            raise ValueError("camera_id must contain 1-64 safe characters")
        if self.device_id is not None and not _SAFE_CAMERA_ID.fullmatch(self.device_id):
            raise ValueError("device_id must contain 1-64 safe characters")
        if not 0.0 <= self.minimum_confidence <= 1.0:
            raise ValueError("minimum confidence must be between zero and one")
        if self.read_timeout_s <= 0:
            raise ValueError("read timeout must be positive")
        if not 0.1 <= self.health_interval_s <= 60.0:
            raise ValueError("health interval must be between 0.1 and 60 seconds")


@dataclass(frozen=True)
class VisionWorkerSummary:
    state: VisionWorkerState
    adapter_mode: str
    pose_evaluator_mode: str
    is_simulated: bool
    frames_received: int
    events_published: int
    source_frames_dropped: int
    poses_not_found: int
    poses_low_visibility: int
    read_timeouts: int
    processing_failures: int
    health_events_published: int
    health_publish_failures: int
    last_failure_reason: ReasonCode | None


class VisionWorker:
    """Process frames serially while the source keeps only its latest frame."""

    def __init__(
        self,
        *,
        config: VisionWorkerConfig,
        source: VisionFrameSource,
        evaluator: PoseEvaluator,
        sink: PoseEventSink,
        health_sink: HealthEventSink | None = None,
        clock: MonotonicClock,
        event_id_factory: Callable[[], UUID],
    ) -> None:
        if (
            source.is_simulated != evaluator.is_simulated
            or source.is_real != evaluator.is_real
        ):
            raise ValueError("frame source and pose evaluator evidence levels must match")
        self.config = config
        self.source = source
        self.evaluator = evaluator
        self.sink = sink
        self.health_sink = health_sink
        self.clock = clock
        self.event_id_factory = event_id_factory
        self._stop_requested = threading.Event()
        self._state = VisionWorkerState.IDLE
        self._frames_received = 0
        self._events_published = 0
        self._source_frames_dropped = 0
        self._poses_not_found = 0
        self._poses_low_visibility = 0
        self._read_timeouts = 0
        self._processing_failures = 0
        self._health_events_published = 0
        self._health_publish_failures = 0
        self._last_failure_reason: ReasonCode | None = None
        self._health_state: ComponentState | None = None
        self._health_reason_codes: tuple[ReasonCode, ...] = ()
        self._health_since_ns: int | None = None
        self._last_health_ns: int | None = None
        self._last_success_ns: int | None = None

    @property
    def state(self) -> VisionWorkerState:
        return self._state

    def stop(self) -> None:
        self._stop_requested.set()

    def summary(self) -> VisionWorkerSummary:
        return VisionWorkerSummary(
            state=self._state,
            adapter_mode=self.source.mode,
            pose_evaluator_mode=self.evaluator.mode,
            is_simulated=self.source.is_simulated,
            frames_received=self._frames_received,
            events_published=self._events_published,
            source_frames_dropped=self._source_frames_dropped,
            poses_not_found=self._poses_not_found,
            poses_low_visibility=self._poses_low_visibility,
            read_timeouts=self._read_timeouts,
            processing_failures=self._processing_failures,
            health_events_published=self._health_events_published,
            health_publish_failures=self._health_publish_failures,
            last_failure_reason=self._last_failure_reason,
        )

    def _health_counters(self) -> dict[str, int]:
        return {
            "events_published": self._events_published,
            "frames_received": self._frames_received,
            "health_publish_failures": self._health_publish_failures,
            "poses_low_visibility": self._poses_low_visibility,
            "poses_not_found": self._poses_not_found,
            "processing_failures": self._processing_failures,
            "read_timeouts": self._read_timeouts,
            "source_frames_dropped": self._source_frames_dropped,
        }

    def _publish_health(
        self,
        *,
        state: ComponentState,
        reason_codes: tuple[ReasonCode, ...],
        now_ns: int,
        force: bool = False,
    ) -> None:
        if self.health_sink is None:
            return
        state_changed = (
            state is not self._health_state
            or reason_codes != self._health_reason_codes
        )
        if state_changed:
            self._health_state = state
            self._health_reason_codes = reason_codes
            self._health_since_ns = now_ns
        interval_ns = int(self.config.health_interval_s * 1_000_000_000)
        if (
            not force
            and not state_changed
            and self._last_health_ns is not None
            and now_ns - self._last_health_ns < interval_ns
        ):
            return
        assert self._health_since_ns is not None
        event = build_vision_health_envelope(
            snapshot=VisionHealthSnapshot(
                state=state,
                reason_codes=reason_codes,
                since_monotonic_ns=self._health_since_ns,
                last_success_monotonic_ns=self._last_success_ns,
                counters=self._health_counters(),
                is_simulated=self.source.is_simulated,
            ),
            event_id=self.event_id_factory(),
            created_monotonic_ns=now_ns,
            device_id=self.config.device_id,
        )
        try:
            self.health_sink.publish(event)
        except Exception:
            self._health_publish_failures += 1
            raise
        self._health_events_published += 1
        self._last_health_ns = now_ns

    def _publish_health_safely(
        self,
        *,
        state: ComponentState,
        reason_codes: tuple[ReasonCode, ...],
        now_ns: int | None = None,
    ) -> None:
        try:
            self._publish_health(
                state=state,
                reason_codes=reason_codes,
                now_ns=int(self.clock.now_ns()) if now_ns is None else now_ns,
                force=True,
            )
        except Exception:
            pass

    def run(self, *, max_frames: int | None = None) -> VisionWorkerSummary:
        if self._state is not VisionWorkerState.IDLE:
            raise RuntimeError("vision worker instances can run only once")
        if max_frames is not None and max_frames <= 0:
            raise ValueError("max_frames must be positive")
        self._stop_requested.clear()
        self._state = VisionWorkerState.RUNNING
        source_started = False
        try:
            if self.health_sink is not None:
                self._publish_health(
                    state=ComponentState.STARTING,
                    reason_codes=(ReasonCode.STARTING,),
                    now_ns=int(self.clock.now_ns()),
                    force=True,
                )
            self.source.start()
            source_started = True
            if self.health_sink is not None:
                self._publish_health(
                    state=ComponentState.READY,
                    reason_codes=(
                        ReasonCode.SIMULATED if self.source.is_simulated else ReasonCode.OK,
                    ),
                    now_ns=int(self.clock.now_ns()),
                    force=True,
                )
            while not self._stop_requested.is_set():
                if max_frames is not None and self._frames_received >= max_frames:
                    break
                item = self.source.read(self.config.read_timeout_s)
                if item is None:
                    if self.source.exhausted:
                        break
                    self._read_timeouts += 1
                    if self.health_sink is not None:
                        self._publish_health(
                            state=self._health_state or ComponentState.READY,
                            reason_codes=self._health_reason_codes
                            or (ReasonCode.OK,),
                            now_ns=int(self.clock.now_ns()),
                        )
                    continue
                frame, dropped = item
                self._frames_received += 1
                self._source_frames_dropped += dropped
                evaluation = self.evaluator.evaluate(frame)
                processed_ns = int(self.clock.now_ns())
                if not evaluation.found:
                    self._poses_not_found += 1
                elif evaluation.confidence < self.config.minimum_confidence:
                    self._poses_low_visibility += 1
                result = build_pose_sample(
                    camera_id=self.config.camera_id,
                    frame=frame,
                    evaluation=evaluation,
                    processed_monotonic_ns=processed_ns,
                    frames_dropped_since_previous=dropped,
                    minimum_confidence=self.config.minimum_confidence,
                    simulated=self.source.is_simulated,
                )
                event = build_pose_envelope(
                    result=result,
                    event_id=self.event_id_factory(),
                    created_monotonic_ns=processed_ns,
                    device_id=self.config.device_id,
                )
                self.sink.publish(event)
                self._events_published += 1
                if result.reason_code in (ReasonCode.OK, ReasonCode.SIMULATED):
                    self._last_success_ns = processed_ns
                    health_state = ComponentState.READY
                    health_reasons = (
                        ReasonCode.SIMULATED if self.source.is_simulated else ReasonCode.OK,
                    )
                else:
                    health_state = ComponentState.DEGRADED
                    health_reasons = (
                        (ReasonCode.SIMULATED, result.reason_code)
                        if self.source.is_simulated
                        else (result.reason_code,)
                    )
                self._publish_health(
                    state=health_state,
                    reason_codes=health_reasons,
                    now_ns=processed_ns,
                )
            self._state = VisionWorkerState.STOPPED
            if self.health_sink is not None:
                self._publish_health(
                    state=ComponentState.STOPPING,
                    reason_codes=(ReasonCode.OK,),
                    now_ns=int(self.clock.now_ns()),
                    force=True,
                )
            return self.summary()
        except Exception as exc:
            self._processing_failures += 1
            self._last_failure_reason = (
                exc.reason_code
                if isinstance(exc, VisionAdapterError)
                else ReasonCode.INTERNAL_ERROR
            )
            self._state = VisionWorkerState.FAILED
            if self.health_sink is not None:
                self._publish_health_safely(
                    state=ComponentState.DEGRADED,
                    reason_codes=(self._last_failure_reason,),
                )
                self._publish_health_safely(
                    state=ComponentState.STOPPING,
                    reason_codes=(self._last_failure_reason,),
                )
            raise
        finally:
            try:
                self.evaluator.close()
            finally:
                if source_started:
                    self.source.stop()
