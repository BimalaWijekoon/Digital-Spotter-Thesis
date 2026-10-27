from __future__ import annotations

import multiprocessing
from pathlib import Path
from uuid import UUID

import pytest

from digital_spotter.contracts import (
    MonotonicNanoseconds,
    PoseLandmark,
    Quality,
    ReasonCode,
    new_event_id,
)
from digital_spotter.core import load_replay_fixture
from digital_spotter.persistence import SessionIMUSummary, SQLiteRepository, migrate_database
from digital_spotter.persistence.schema import connect_database
from digital_spotter.vision import (
    PoseEvaluation,
    ReplayFrameSource,
    ReplayPoseEvaluator,
    VisionReplayError,
    VisionWorker,
    VisionWorkerConfig,
    VisionWorkerState,
)


FIXTURES = Path(__file__).parents[1] / "fixtures" / "replay" / "v1"
SESSION_ID = UUID("11111111-1111-4111-8111-111111111119")


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

    def __init__(self) -> None:
        self.closed = False

    def evaluate(self, frame):
        raise RuntimeError("injected vision worker crash")

    def close(self) -> None:
        self.closed = True


def _event_ids():
    sequence = iter(range(1, 100))
    return lambda: new_event_id(
        unix_time_ms=1_750_000_000_000,
        random_bits=next(sequence),
    )


def _evaluations() -> tuple[PoseEvaluation, ...]:
    good = PoseEvaluation(
        found=True,
        landmarks=(PoseLandmark(x=0.5, y=0.5, z=0.0, visibility=0.95),),
        angles={"left_knee": 100.0},
        confidence=0.95,
    )
    missing = PoseEvaluation(found=False, landmarks=(), angles={}, confidence=0.0)
    low = PoseEvaluation(
        found=True,
        landmarks=(PoseLandmark(x=0.4, y=0.6, z=0.0, visibility=0.2),),
        angles={"left_knee": 80.0},
        confidence=0.2,
    )
    return good, missing, low


def _run_replay():
    fixture = load_replay_fixture(FIXTURES / "synthetic_normal_rep.json")
    sink = _CollectingSink()
    worker = VisionWorker(
        config=VisionWorkerConfig(
            camera_id="synthetic-camera",
            device_id="pi-replay-test",
            minimum_confidence=0.7,
        ),
        source=ReplayFrameSource(
            video_path=FIXTURES / fixture.video.path,
            captured_monotonic_ns=tuple(fixture.video.captured_monotonic_ns),
        ),
        evaluator=ReplayPoseEvaluator(_evaluations()),
        sink=sink,
        clock=_SequenceClock((1_020_000, 1_040_000, 1_060_000)),
        event_id_factory=_event_ids(),
    )
    summary = worker.run()
    return summary, tuple(event.to_messagepack() for event in sink.events), sink.events


def _crashing_worker_child(video_path: str, timestamps: tuple[int, ...]) -> None:
    worker = VisionWorker(
        config=VisionWorkerConfig(camera_id="crash-test-camera"),
        source=ReplayFrameSource(
            video_path=Path(video_path),
            captured_monotonic_ns=timestamps,
        ),
        evaluator=_CrashingEvaluator(),
        sink=_CollectingSink(),
        clock=_SequenceClock((2_000_000,)),
        event_id_factory=_event_ids(),
    )
    worker.run()


def test_replay_worker_is_deterministic_bounded_and_explicitly_simulated():
    first_summary, first_encoded, first_events = _run_replay()
    second_summary, second_encoded, second_events = _run_replay()

    assert first_summary == second_summary
    assert first_encoded == second_encoded
    assert first_summary.state is VisionWorkerState.STOPPED
    assert first_summary.adapter_mode == "replay"
    assert first_summary.pose_evaluator_mode == "replay"
    assert first_summary.is_simulated is True
    assert first_summary.frames_received == 3
    assert first_summary.events_published == 3
    assert first_summary.source_frames_dropped == 0
    assert first_summary.poses_not_found == 1
    assert first_summary.poses_low_visibility == 1
    assert all(event.quality is Quality.SIMULATED for event in first_events)
    assert all(event.quality is Quality.SIMULATED for event in second_events)


def test_replay_source_rejects_frame_timestamp_count_mismatch():
    source = ReplayFrameSource(
        video_path=FIXTURES / "synthetic_motion_4x4.y4m",
        captured_monotonic_ns=(1,),
    )
    with pytest.raises(VisionReplayError, match="counts differ"):
        source.start()


def test_worker_failure_is_explicit_and_always_closes_adapters():
    fixture = load_replay_fixture(FIXTURES / "synthetic_normal_rep.json")
    source = ReplayFrameSource(
        video_path=FIXTURES / fixture.video.path,
        captured_monotonic_ns=tuple(fixture.video.captured_monotonic_ns),
    )
    evaluator = _CrashingEvaluator()
    worker = VisionWorker(
        config=VisionWorkerConfig(camera_id="crash-test-camera"),
        source=source,
        evaluator=evaluator,
        sink=_CollectingSink(),
        clock=_SequenceClock((2_000_000,)),
        event_id_factory=_event_ids(),
    )

    with pytest.raises(RuntimeError, match="injected vision worker crash"):
        worker.run()

    assert worker.state is VisionWorkerState.FAILED
    assert worker.summary().processing_failures == 1
    assert worker.summary().last_failure_reason is ReasonCode.INTERNAL_ERROR
    assert evaluator.closed is True
    assert source.is_running is False


def test_crashed_worker_process_does_not_mutate_active_database(tmp_path):
    database_path = tmp_path / "isolated.sqlite3"
    migrate_database(database_path)
    repository = SQLiteRepository(database_path)
    repository.create_session(
        session_uuid=SESSION_ID,
        device_id="pi-process-test",
        exercise_id=0,
        exercise_name="Synthetic isolation test",
        exercise_contract_version="isolation-v1",
        started_monotonic_ns=1_000_000,
        created_utc_ms=None,
        model_package_id=None,
        initial_imu_summary=SessionIMUSummary(
            imu_device_id="imu-process-test",
            sample_count=0,
            gap_count=0,
            degraded_sample_count=0,
            clock_reset_count=0,
            distinct_boot_count=0,
            ring_eviction_count=0,
            duplicate_event_count=0,
            last_boot_id=None,
            first_sequence=None,
            last_sequence=None,
            first_captured_monotonic_ns=None,
            last_captured_monotonic_ns=None,
            updated_monotonic_ns=1_000_000,
        ),
    )
    fixture = load_replay_fixture(FIXTURES / "synthetic_normal_rep.json")
    context = multiprocessing.get_context("spawn")
    process = context.Process(
        target=_crashing_worker_child,
        args=(
            str(FIXTURES / fixture.video.path),
            tuple(fixture.video.captured_monotonic_ns),
        ),
    )
    process.start()
    process.join(timeout=10.0)
    if process.is_alive():
        process.terminate()
        process.join(timeout=2.0)
        pytest.fail("crashing vision worker process did not exit")

    assert process.exitcode not in {None, 0}
    assert repository.get_session(SESSION_ID).state == "active"
    assert repository.counts() == {
        "sessions": 1,
        "session_imu_summaries": 1,
        "reps": 0,
        "analysis_events": 0,
        "outbox": 0,
    }
    connection = connect_database(database_path)
    try:
        assert connection.execute("PRAGMA quick_check").fetchone()[0] == "ok"
    finally:
        connection.close()
