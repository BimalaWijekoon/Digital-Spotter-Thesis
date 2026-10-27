"""Field-workout orchestration; one session, real sensor monitoring, no fake scores."""
from __future__ import annotations

import json
import math
import time
from datetime import datetime, timezone
from collections import deque
from pathlib import Path
from uuid import uuid4

from digital_spotter.contracts import EventType, Quality, Source
from digital_spotter.core.sessions import SessionStartRequest
from digital_spotter.inference.v5_features import build_v5_candidate_inputs, V5FeatureUnavailable


def freshness(sample, *, now_ns, timestamp):
    if sample is None:
        return 'unavailable'
    age = now_ns - int(getattr(sample, timestamp))
    if age < 0 or age > 2_000_000_000:
        return 'stale'
    return 'receiving' if sample.quality is Quality.GOOD else 'degraded'


class WorkoutService:
    """Called only on the core event loop; HTTP threads submit commands to it."""
    def __init__(self, *, session, repository, model, edge_device_id, imu_device_id,
                 log_path: Path | None = None, reference_result=None, demo=None,
                 feedback=None, network_probe=None):
        self.session = session
        self.repository = repository
        self.model = model
        self.model_version = model.model_version
        self.edge_device_id = edge_device_id
        self.imu_device_id = imu_device_id
        self.log_path = log_path
        self.reference_result = reference_result
        self.demo = demo
        self.feedback = feedback
        self.network_probe = network_probe
        self.network = self._sample_network()
        self._network_sampled_ns = time.monotonic_ns()
        self.state = 'idle'
        self.session_id = None
        self.exercise_id = None
        self.load_kg = None
        self.rep_count = 0
        self.latest_rep = None
        self.started_ns = None
        self.paused_ns = None
        self.pause_total_ns = 0
        self.finished_elapsed = 0.0
        self.saved = False
        self.started_utc_ms = None
        self.completed_set = None
        self.set_pose_count_at_start = 0
        self.set_pose_detected_at_start = 0
        self.set_pose_good_at_start = 0
        self.imu = deque(maxlen=100)
        self.pose = None
        self.pose_count = 0
        self.pose_detected_count = 0
        self.pose_good_count = 0
        self.pose_test = None
        self.pose_test_result = None
        self.analysis = self._unavailable('v5_live_feature_contract_unverified')

    @staticmethod
    def _unavailable(reason):
        return {'state': 'unavailable', 'reason': reason}

    def _sample_network(self):
        if self.network_probe is None:
            return {'state': 'unavailable', 'interface': None,
                    'has_local_address': False}
        try:
            status = self.network_probe.sample()
            if (status.get('state') not in ('connected', 'disconnected', 'unavailable')
                    or not isinstance(status.get('has_local_address'), bool)):
                raise ValueError('invalid network probe result')
            return {'state': status['state'], 'interface': status.get('interface'),
                    'has_local_address': status['has_local_address']}
        except (OSError, ValueError, TypeError, AttributeError):
            return {'state': 'unavailable', 'interface': None,
                    'has_local_address': False}

    async def open(self):
        restored = await self.session.open()
        if restored is not None:
            # Do not silently adopt a workout whose load/context was not restored.
            raise RuntimeError('unfinished workout in database; preserve it and select a new run directory')

    def accept_imu(self, event):
        if (event.event_type is not EventType.IMU_SAMPLE or event.source is not Source.IMU
                or event.device_id != self.imu_device_id or event.payload.device_id != self.imu_device_id
                or event.quality is Quality.SIMULATED):
            raise ValueError('unexpected or simulated IMU event')
        if self.imu and self.imu[-1].payload.boot_id != event.payload.boot_id:
            self.imu.clear()
        self.imu.append(event)
        if self.state in ('active', 'paused'):
            return self.session.accept_imu(event)
        return True

    def accept_pose(self, event):
        if (event.event_type is not EventType.POSE_SAMPLE or event.source is not Source.VISION
                or event.device_id != self.edge_device_id or event.quality is Quality.SIMULATED):
            raise ValueError('unexpected or simulated pose event')
        self.pose = event
        self.pose_count += 1
        self.pose_detected_count += int(bool(event.payload.landmarks))
        if event.quality is Quality.GOOD:
            self.pose_good_count += 1
        check = self.pose_test
        if check and check['start_ns'] <= int(event.payload.captured_monotonic_ns) <= check['end_ns']:
            check['frames_received'] += 1
            check['good_pose_frames'] += int(event.quality is Quality.GOOD)
            check['poses_not_found'] += int(not event.payload.landmarks)
            check['poses_low_visibility'] += int(bool(event.payload.landmarks) and event.quality is not Quality.GOOD)
        if self.state == 'active':
            return self.session.accept_pose(event)
        return True

    async def command(self, action, data):
        if action == 'start':
            if self.state != 'idle':
                raise ValueError('a set is already active')
            exercise, load = data.get('exercise_id'), data.get('load_kg')
            if (isinstance(exercise, bool) or exercise not in (0, 1)
                    or isinstance(load, (bool, str)) or not isinstance(load, (int, float))
                    or not math.isfinite(load) or not 0 <= load <= 1000):
                raise ValueError('choose Squat/Deadlift and a finite load of 0–1000 kg')
            session_id = uuid4()
            now = time.monotonic_ns()
            created_utc_ms = time.time_ns() // 1_000_000
            await self.session.begin(SessionStartRequest(
                session_uuid=session_id, edge_device_id=self.edge_device_id,
                imu_device_id=self.imu_device_id, exercise_id=exercise,
                exercise_name=('Squat', 'Deadlift')[exercise],
                exercise_contract_version='v5-research-video-rule-1',
                started_monotonic_ns=now, created_utc_ms=created_utc_ms,
                model_package_id=self.model_version,
            ))
            self.session_id, self.exercise_id, self.load_kg = session_id, exercise, float(load)
            self.started_ns, self.paused_ns = now, None
            self.started_utc_ms = created_utc_ms
            self.pause_total_ns = 0
            self.rep_count, self.latest_rep, self.saved = 0, None, False
            self.completed_set = None
            self.set_pose_count_at_start = self.pose_count
            self.set_pose_detected_at_start = self.pose_detected_count
            self.set_pose_good_at_start = self.pose_good_count
            self.state = 'active'
            self.analysis = self._unavailable('v5_live_feature_contract_unverified')
            await self._save_context()
        elif action == 'pause':
            if self.state == 'active':
                self.session.discard_partial_rep()
                self.paused_ns = time.monotonic_ns()
                self.state = 'paused'
            elif self.state != 'paused':
                raise ValueError('no active set to pause')
        elif action == 'resume':
            if self.state == 'paused':
                self.session.discard_partial_rep()
                self.pause_total_ns += time.monotonic_ns() - self.paused_ns
                self.paused_ns = None
                self.state = 'active'
            elif self.state != 'active':
                raise ValueError('no paused set to resume')
        elif action == 'stop':
            if self.state in ('active', 'paused'):
                self.tick()
                self.finished_elapsed = self.elapsed_s()
                await self._save_context()
                ended_utc_ms = time.time_ns() // 1_000_000
                await self.session.stop(session_uuid=self.session_id,
                    ended_monotonic_ns=time.monotonic_ns(), ended_utc_ms=ended_utc_ms)
                self.state, self.saved = 'idle', True
                self.completed_set = self._completed_set(ended_utc_ms)
        else:
            raise ValueError('unknown workout command')
        return self.snapshot()

    async def _save_context(self):
        await self.session.database_queue.submit(lambda: self.repository.save_workout_context(
            session_uuid=self.session_id, load_kg=self.load_kg,
            rep_count=self.rep_count, model_version=self.model_version,
        ))

    def _completed_set(self, ended_utc_ms):
        imu = self.imu[-1].payload if self.imu else None
        now = time.monotonic_ns()
        warning = self.analysis.get('reason', 'live_analysis_unavailable')
        return {
            'schema_version': 1,
            'kind': 'digital_spotter_research_set',
            'status': 'complete',
            'hardware_simulated': False,
            'session_id': str(self.session_id),
            'started_utc_ms': self.started_utc_ms,
            'ended_utc_ms': ended_utc_ms,
            'duration_s': round(self.finished_elapsed, 2),
            'exercise': {
                'id': self.exercise_id,
                'name': ('Squat', 'Deadlift')[self.exercise_id],
                'load_kg': self.load_kg,
            },
            'rep_count': self.rep_count,
            'latest_rep': self.latest_rep,
            'camera': {
                'frames': self.pose_count - self.set_pose_count_at_start,
                'detected_pose_frames': self.pose_detected_count - self.set_pose_detected_at_start,
                'good_pose_frames': self.pose_good_count - self.set_pose_good_at_start,
            },
            'wearable': {
                'state': freshness(imu, now_ns=now, timestamp='arrival_monotonic_ns'),
            },
            'model': {
                'version': self.model_version,
                'live_inputs_verified': False,
            },
            'analysis': dict(self.analysis),
            'warnings': [warning],
        }

    def tick(self):
        now_ns = time.monotonic_ns()
        if now_ns - self._network_sampled_ns >= 2_000_000_000:
            self.network = self._sample_network()
            self._network_sampled_ns = now_ns
        if self.feedback is not None:
            self.feedback.set_network_state(self.network['state'])
            latest_imu = self.imu[-1].payload if self.imu else None
            self.feedback.set_imu_state(freshness(
                latest_imu, now_ns=now_ns,
                timestamp='arrival_monotonic_ns'))
        if self.pose_test and time.monotonic_ns() >= self.pose_test['end_ns']:
            check, self.pose_test = self.pose_test, None
            self.pose_test_result = {
                'schema_version': 1, 'kind': 'person_pose_quality_research',
                'status': 'complete', 'hardware_simulated': False, 'camera': 'imx219',
                'pose_evaluator': 'mediapipe', 'duration_requested_s': 30,
                'completed_utc': datetime.now(timezone.utc).isoformat(timespec='seconds'),
                **{key: check[key] for key in ('frames_received', 'good_pose_frames',
                   'poses_not_found', 'poses_low_visibility')},
            }
            if self.log_path:
                destination = self.log_path.parent / 'person-pose-latest.json'
                temporary = destination.with_suffix('.tmp')
                temporary.write_text(json.dumps(self.pose_test_result) + '\n', encoding='utf-8')
                temporary.replace(destination)
        if self.state != 'active':
            return
        for rep in self.session.poll_completed_reps():
            self.rep_count = rep.event.rep_number
            self.latest_rep = {'number': self.rep_count, 'quality': rep.event.quality.value}
            # One canonical feature path. Do not claim unresolved input provenance is validated.
            reason = 'v5_live_feature_contract_unverified'
            try:
                build_v5_candidate_inputs(rep, exercise_id=self.exercise_id,
                    load_kg=self.load_kg, preprocessor=self.model.preprocessor)
            except V5FeatureUnavailable:
                reason = 'phase_or_calibrated_imu_unavailable'
            self.analysis = self._unavailable(reason)
            if self.log_path is not None:
                record = {'timestamp_utc_ms': time.time_ns() // 1_000_000,
                    'session_id': str(self.session_id), 'rep_id': str(rep.event.rep_id),
                    'exercise_id': self.exercise_id, 'load_kg': self.load_kg,
                    'raw_probability': None, 'calibrated_probability': None,
                    'threshold': self.model.threshold, 'predicted_class': None,
                    'preprocessing_ms': None, 'inference_ms': None, 'model_version': self.model_version,
                    'camera_timestamp_range_ns': [rep.phases[0].started_monotonic_ns, rep.phases[-1].ended_monotonic_ns],
                    'imu_timestamp_range_ns': None, 'sync_delta_ns': None, 'warnings': [reason]}
                with self.log_path.open('a', encoding='utf-8') as output:
                    output.write(json.dumps(record, allow_nan=False) + '\n')

    def elapsed_s(self):
        if self.state == 'idle':
            return self.finished_elapsed
        end = self.paused_ns or time.monotonic_ns()
        return max(0, (end - self.started_ns - self.pause_total_ns) / 1_000_000_000)

    def snapshot(self):
        now = time.monotonic_ns()
        imu = self.imu[-1].payload if self.imu else None
        pose = self.pose.payload if self.pose else None
        result = {'version': 'workout_v1',
            'network': dict(self.network),
            'session': {'state': self.state, 'id': str(self.session_id) if self.session_id else None,
                'exercise_id': self.exercise_id, 'load_kg': self.load_kg,
                'rep_count': self.rep_count, 'elapsed_s': round(self.elapsed_s(), 2), 'saved': self.saved},
            'wearable': {'state': freshness(imu, now_ns=now, timestamp='arrival_monotonic_ns')},
            'camera': {'state': freshness(pose, now_ns=now, timestamp='processed_monotonic_ns'),
                'frames': self.pose_count, 'detected_pose_frames': self.pose_detected_count,
                'good_pose_frames': self.pose_good_count},
            'model': {'loaded': True, 'version': self.model_version, 'live_inputs_verified': False},
            'analysis': self.analysis, 'latest_rep': self.latest_rep}
        if self.completed_set is not None:
            result['completed_set'] = self.completed_set
        return result

    def pose_latest(self):
        """Bounded diagnostic view, never a frame-match or scoring authorization."""
        result = {'version': 'research_pose_latest_v1', 'state': 'unavailable',
                  'frame_aligned': False, 'age_ms': None, 'pose': None}
        if self.pose is None:
            return result
        pose = self.pose.payload
        age = time.monotonic_ns() - int(pose.captured_monotonic_ns)
        result['age_ms'] = round(age / 1e6, 2)
        if age < 0 or age > 500_000_000:
            result['state'] = 'stale'
        elif not pose.landmarks:
            result['state'] = 'not_found'
        elif (len(pose.landmarks) == 33
                and int(pose.captured_monotonic_ns) // 1000 <= 9_007_199_254_740_991
                and int(pose.frame_sequence) <= 9_007_199_254_740_991):
            result['state'] = 'detected'
            result['pose'] = {'frame_sequence': int(pose.frame_sequence),
                'captured_monotonic_us': int(pose.captured_monotonic_ns) // 1000,
                'image_width': pose.image_width, 'image_height': pose.image_height,
                'quality': pose.quality.value,
                'landmarks': [point.model_dump(mode='json') for point in pose.landmarks]}
        return result

    def imu_window(self):
        now = time.monotonic_ns()
        latest = self.imu[-1].payload if self.imu else None
        state = freshness(latest, now_ns=now, timestamp='arrival_monotonic_ns')
        samples = []
        if state in ('receiving', 'degraded'):
            for event in self.imu:
                value = event.payload
                if now - int(value.arrival_monotonic_ns) > 2_000_000_000:
                    continue
                samples.append({'sequence': int(value.sequence),
                    't_ms': round((int(value.captured_monotonic_ns) - int(latest.captured_monotonic_ns)) / 1e6, 2),
                    'acceleration_m_s2': list(value.acceleration_m_s2),
                    'angular_velocity_rad_s': list(value.angular_velocity_rad_s)})
        return {'version': 'research_imu_window_v1', 'state': state, 'samples': samples}

    def start_pose_test(self):
        if self.pose_test:
            raise ValueError('a pose test is already running')
        now = time.monotonic_ns()
        self.pose_test_result = None
        self.pose_test = {'start_ns': now + 20_000_000_000, 'end_ns': now + 50_000_000_000,
            'frames_received': 0, 'good_pose_frames': 0, 'poses_not_found': 0, 'poses_low_visibility': 0}
        return self.pose_test_snapshot()

    def pose_test_snapshot(self):
        if not self.pose_test:
            return {'phase': 'complete' if self.pose_test_result else 'idle',
                    'result': self.pose_test_result, 'uses_live_camera': True}
        now = time.monotonic_ns()
        countdown = now < self.pose_test['start_ns']
        deadline = self.pose_test['start_ns'] if countdown else self.pose_test['end_ns']
        return {'phase': 'countdown' if countdown else 'running',
                'remaining_s': max(0, math.ceil((deadline - now) / 1e9)),
                'uses_live_camera': True}

    async def close(self):
        if self.state in ('active', 'paused'):
            await self.command('stop', {})
        if self.feedback is not None:
            await self.feedback.close()
        await self.session.close()

    def demo_catalog(self):
        if self.demo is None:
            return None
        return {**self.demo.catalog(),
                'actuators_enabled': bool(self.feedback and self.feedback.enabled)}
