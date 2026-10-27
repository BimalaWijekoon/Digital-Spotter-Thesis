from __future__ import annotations

from pathlib import Path
from uuid import UUID

import pytest

from digital_spotter.contracts import (
    ComponentState,
    EventEnvelope,
    HealthState,
    MonotonicNanoseconds,
    PoseLandmark,
    Quality,
    ReasonCode,
    Source,
    new_event_id,
)
from digital_spotter.core import load_replay_fixture
from digital_spotter.vision import (
    PoseEvaluation,
    ReplayFrameSource,
    ReplayPoseEvaluator,
    VisionHealthSnapshot,
    VisionWatchdog,
    VisionWorker,
    VisionWorkerConfig,
    VisionWorkerState,
    build_vision_health_envelope,
)


FIXTURES = Path(__file__).parents[1] / "fixtures" / "replay" / "v1"
EVENT_ID = UUID("01993ced-28c0-7000-8000-000000000021")


class _SequenceClock:
    def __init__(self, values: tuple[int, ...]) -> None:
        self._values = iter(values)

    def now_ns(self) -> MonotonicNanoseconds:
        return MonotonicNanoseconds(next(self._values))


class _CollectingSink:
    def __init__(self) -> None:
        self.events = []

    def publish(self, event) -> None:
        self.events.append(event)


class _CrashingEvaluator:
    mode = "replay"
    is_real = False
    is_simulated = True

    def evaluate(self, frame):
        raise RuntimeError("injected health-path failure")

    def close(self) -> None:
        pass


def _event_ids():
    sequence = iter(range(100, 200))
    return lambda: new_event_id(
        unix_time_ms=1_750_000_000_000,
        random_bits=next(sequence),
    )


def _evaluations() -> tuple[PoseEvaluation, ...]:
    return (
        PoseEvaluation(
            found=True,
            landmarks=(
                PoseLandmark(x=0.5, y=0.5, z=0.0, visibility=0.95),
            ),
            angles={"left_knee": 100.0},
            confidence=0.95,
        ),
        PoseEvaluation(found=False, landmarks=(), angles={}, confidence=0.0),
        PoseEvaluation(
            found=True,
            landmarks=(
                PoseLandmark(x=0.4, y=0.6, z=0.0, visibility=0.2),
            ),
            angles={"left_knee": 80.0},
            confidence=0.2,
        ),
    )


def _replay_source() -> ReplayFrameSource:
    fixture = load_replay_fixture(FIXTURES / "synthetic_normal_rep.json")
    return ReplayFrameSource(
        video_path=FIXTURES / fixture.video.path,
        captured_monotonic_ns=tuple(fixture.video.captured_monotonic_ns),
    )


def test_health_event_is_canonical_bounded_and_round_trips():
    event = build_vision_health_envelope(
        snapshot=VisionHealthSnapshot(
            state=ComponentState.DEGRADED,
            reason_codes=(ReasonCode.POSE_NOT_FOUND,),
            since_monotonic_ns=1_000_000,
            last_success_monotonic_ns=900_000,
            counters={"frames_received": 7, "poses_not_found": 2},
            is_simulated=False,
        ),
        event_id=EVENT_ID,
        created_monotonic_ns=1_200_000,
        device_id="pi-camera-001",
    )

    assert event.source is Source.VISION
    assert event.quality is Quality.VISION_DEGRADED
    assert event.payload.state is ComponentState.DEGRADED
    assert event.payload.reason_codes == (ReasonCode.POSE_NOT_FOUND,)
    assert EventEnvelope[HealthState].from_messagepack(event.to_messagepack()) == event


def test_watchdog_accepts_only_ordered_vision_heartbeats_and_expires_after_timeout():
    event = build_vision_health_envelope(
        snapshot=VisionHealthSnapshot(
            state=ComponentState.READY,
            reason_codes=(ReasonCode.OK,),
            since_monotonic_ns=1_000,
            last_success_monotonic_ns=1_000,
            counters={},
            is_simulated=False,
        ),
        event_id=EVENT_ID,
        created_monotonic_ns=1_000,
        device_id="pi-camera-001",
    )
    watchdog = VisionWatchdog(timeout_ns=500)

    assert watchdog.expired(now_monotonic_ns=0) is True
    watchdog.observe(event)
    assert watchdog.expired(now_monotonic_ns=1_500) is False
    assert watchdog.expired(now_monotonic_ns=1_501) is True

    with pytest.raises(ValueError, match="only canonical vision"):
        watchdog.observe(event.model_copy(update={"source": Source.IMU}))
    older = event.model_copy(update={"created_monotonic_ns": 999})
    with pytest.raises(ValueError, match="backwards"):
        watchdog.observe(older)


def test_worker_emits_simulated_lifecycle_pose_quality_and_counter_health():
    pose_sink = _CollectingSink()
    health_sink = _CollectingSink()
    worker = VisionWorker(
        config=VisionWorkerConfig(camera_id="health-replay-camera"),
        source=_replay_source(),
        evaluator=ReplayPoseEvaluator(_evaluations()),
        sink=pose_sink,
        health_sink=health_sink,
        clock=_SequenceClock(
            (900_000, 950_000, 1_020_000, 1_040_000, 1_060_000, 1_070_000)
        ),
        event_id_factory=_event_ids(),
    )

    summary = worker.run()

    assert summary.state is VisionWorkerState.STOPPED
    assert summary.health_events_published == 5
    assert summary.health_publish_failures == 0
    assert [event.payload.state for event in health_sink.events] == [
        ComponentState.STARTING,
        ComponentState.READY,
        ComponentState.DEGRADED,
        ComponentState.DEGRADED,
        ComponentState.STOPPING,
    ]
    assert health_sink.events[2].payload.reason_codes == (
        ReasonCode.SIMULATED,
        ReasonCode.POSE_NOT_FOUND,
    )
    assert health_sink.events[3].payload.reason_codes == (
        ReasonCode.SIMULATED,
        ReasonCode.POSE_LOW_VISIBILITY,
    )
    assert health_sink.events[3].payload.last_success_monotonic_ns == 1_020_000
    assert health_sink.events[-1].payload.counters["frames_received"] == 3
    assert all(event.payload.is_simulated for event in health_sink.events)
    assert all(event.quality is Quality.SIMULATED for event in health_sink.events)


def test_worker_emits_periodic_ready_heartbeats_without_state_changes():
    health_sink = _CollectingSink()
    worker = VisionWorker(
        config=VisionWorkerConfig(
            camera_id="heartbeat-replay-camera",
            health_interval_s=0.1,
        ),
        source=_replay_source(),
        evaluator=ReplayPoseEvaluator((_evaluations()[0],) * 3),
        sink=_CollectingSink(),
        health_sink=health_sink,
        clock=_SequenceClock(
            (0, 1, 100_000_001, 200_000_001, 300_000_001, 300_000_002)
        ),
        event_id_factory=_event_ids(),
    )

    summary = worker.run()

    assert summary.health_events_published == 6
    assert [event.payload.state for event in health_sink.events] == [
        ComponentState.STARTING,
        ComponentState.READY,
        ComponentState.READY,
        ComponentState.READY,
        ComponentState.READY,
        ComponentState.STOPPING,
    ]
    assert [int(event.created_monotonic_ns) for event in health_sink.events[2:5]] == [
        100_000_001,
        200_000_001,
        300_000_001,
    ]


def test_worker_failure_emits_degraded_and_stopping_health_without_masking_error():
    health_sink = _CollectingSink()
    worker = VisionWorker(
        config=VisionWorkerConfig(camera_id="health-crash-camera"),
        source=_replay_source(),
        evaluator=_CrashingEvaluator(),
        sink=_CollectingSink(),
        health_sink=health_sink,
        clock=_SequenceClock((900_000, 950_000, 1_000_000, 1_100_000)),
        event_id_factory=_event_ids(),
    )

    with pytest.raises(RuntimeError, match="injected health-path failure"):
        worker.run()

    assert worker.state is VisionWorkerState.FAILED
    assert [event.payload.state for event in health_sink.events] == [
        ComponentState.STARTING,
        ComponentState.READY,
        ComponentState.DEGRADED,
        ComponentState.STOPPING,
    ]
    assert health_sink.events[-2].payload.reason_codes == (ReasonCode.INTERNAL_ERROR,)
    assert worker.summary().health_events_published == 4
