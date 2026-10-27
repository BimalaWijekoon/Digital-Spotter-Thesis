"""Presentation-only pose diagnostics; deterministic data, no hardware/database."""
from types import SimpleNamespace
from unittest.mock import patch

from digital_spotter.contracts import EventType, PoseLandmark, PoseSample, Quality, Source
from digital_spotter.core.workout import WorkoutService
from digital_spotter.api.workout import WorkoutHub


def service():
    return WorkoutService(session=SimpleNamespace(), repository=SimpleNamespace(),
        model=SimpleNamespace(model_version='test'), edge_device_id='pi-test',
        imu_device_id='imu-test')


def event(*, found=True):
    landmarks = tuple(PoseLandmark(x=.5, y=.5, z=0, visibility=.3) for _ in range(33)) if found else ()
    pose = PoseSample(camera_id='camera-test', frame_sequence=1,
        captured_monotonic_ns=1_000_000_000, processed_monotonic_ns=1_100_000_000,
        image_width=640, image_height=360, landmark_schema_version=1,
        landmarks=landmarks, pose_confidence=.3 if found else 0,
        quality=Quality.VISION_DEGRADED, processing_latency_ns=100_000_000)
    return SimpleNamespace(event_type=EventType.POSE_SAMPLE, source=Source.VISION,
        device_id='pi-test', quality=pose.quality, payload=pose)


def test_detection_is_independent_of_quality_and_contains_all_33_landmarks():
    core = service()
    core.accept_pose(event())
    with patch('digital_spotter.core.workout.time.monotonic_ns', return_value=1_200_000_000):
        camera = core.snapshot()['camera']
        latest = core.pose_latest()
    assert camera['detected_pose_frames'] == 1
    assert camera['good_pose_frames'] == 0
    assert latest['state'] == 'detected'
    assert latest['frame_aligned'] is False
    assert latest['age_ms'] == 200
    assert len(latest['pose']['landmarks']) == 33
    assert latest['pose']['quality'] == 'vision_degraded'
    assert core.analysis['state'] == 'unavailable'


def test_old_or_missing_pose_does_not_leave_a_stale_skeleton():
    core = service()
    assert core.pose_latest()['pose'] is None
    core.accept_pose(event())
    with patch('digital_spotter.core.workout.time.monotonic_ns', return_value=2_000_000_000):
        assert core.pose_latest()['state'] == 'stale'
        assert core.pose_latest()['pose'] is None
    core.accept_pose(event(found=False))
    with patch('digital_spotter.core.workout.time.monotonic_ns', return_value=1_200_000_000):
        assert core.pose_latest()['state'] == 'not_found'
        assert core.pose_latest()['pose'] is None
        assert core.snapshot()['camera']['detected_pose_frames'] == 1


def test_api_snapshot_rechecks_age_instead_of_serving_an_expired_hub_value():
    core = service()
    core.accept_pose(event())
    hub = WorkoutHub()
    with patch('digital_spotter.core.workout.time.monotonic_ns', return_value=1_200_000_000):
        hub.publish(core)
    with patch('digital_spotter.api.workout.time.monotonic_ns', return_value=2_000_000_000):
        result = hub.snapshot('pose')
    assert result['state'] == 'stale'
    assert result['pose'] is None
