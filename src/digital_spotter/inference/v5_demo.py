"""Four frozen synthetic replay cases; never live scoring or actuator commands.

Source labels and complete inputs are preserved. At the owner's explicit request,
the bad-squat case is a curated, correctly recognised example, not an evaluation.
The previous false negative remains documented; no model/threshold was changed.
The source CSV is provenance only and is not needed by the deployment runtime.
"""
from __future__ import annotations

from dataclasses import asdict
import hashlib
import time

import numpy as np

from .v5_candidate import CANDIDATE_VERSION


SOURCE_DATASET_SHA256 = '934925aa40ad7e24e6f34ff12075d76d70d0a97ba1f200374508505323d620ff'
FIXTURE_SHA256 = '95c4064fda91714272f57bc8afb397fae895ce39750abf5abc8e70238db04106'
_CASES = (
    ('squat', 'correct', 5, 0, 35., 0),
    ('squat', 'incorrect', 6, 1, 35., 3),
    ('deadlift', 'correct', 42, 0, 50., 0),
    ('deadlift', 'incorrect', 45, 1, 50., 2),
)


class DemoReplay:
    """Core-loop owned, shares the canonical V5 interpreter and fitted policy."""

    def __init__(self, runtime):
        if runtime.model_version != CANDIDATE_VERSION:
            raise ValueError('Demo requires the explicitly selected synthetic V5 revision')
        fixture = runtime.package / 'inference_fixture.npz'
        if hashlib.sha256(fixture.read_bytes()).hexdigest() != FIXTURE_SHA256:
            raise ValueError('Demo fixture hash mismatch')
        self.runtime = runtime
        self.cases = {}
        with np.load(fixture, allow_pickle=False) as values:
            raw, context = values['raw_temporal'], values['raw_context']
            if raw.shape != (64, 3, 29) or context.shape != (64, 2):
                raise ValueError('Demo fixture shape mismatch')
            for exercise, form, index, label, load, error in _CASES:
                exercise_id = int(exercise == 'deadlift')
                if (not np.isfinite(raw[index]).all()
                        or context[index].tolist() != [exercise_id, load]):
                    raise ValueError('Demo fixture context/feature mismatch')
                metadata = dict(exercise=exercise, form=form, fixture_index=index,
                                source_label=label, error_type_id=error, load_kg=load)
                phases = [{'phase': i + 1, **dict(zip(runtime.preprocessor.temporal_features,
                                                    map(float, row)))}
                          for i, row in enumerate(raw[index])]
                metadata['imu_replay'] = {
                    'version': 'demo_phase_imu_v1', 'source': 'synthetic_training_replay',
                    'representation': 'phase_medians', 'measured_timestamps': False,
                    'units': {'acceleration_m_s2': 'm/s^2', 'angular_velocity_rad_s': 'rad/s'},
                    'phases': [dict(phase=row['phase'],
                                    acceleration_m_s2=[row[f'IMU_Acc_{axis}'] for axis in 'XYZ'],
                                    angular_velocity_rad_s=[row[f'IMU_Gyro_{axis}'] for axis in 'XYZ'])
                               for row in phases],
                }
                self.cases[(exercise, form)] = (metadata, phases,
                                               {'Exercise_ID': exercise_id, 'Load_kg': load})

    def catalog(self):
        return {'model_version': self.runtime.model_version, 'reference_only': True, 'live': False,
                'source': 'synthetic_training_replay', 'fixture_sha256': FIXTURE_SHA256,
                'selection_policy': 'curated_demonstration_not_accuracy_evaluation',
                'known_false_negative_fixture_index': 1,
                'source_dataset_sha256': SOURCE_DATASET_SHA256,
                'animation_drives_features': False, 'actuators_enabled': False,
                'cases': [dict(case[0]) for case in self.cases.values()]}

    def predict(self, request):
        if (not isinstance(request, dict) or set(request) != {'exercise', 'form', 'rep_id'}
                or request['exercise'] not in ('squat', 'deadlift')
                or request['form'] not in ('correct', 'incorrect')
                or type(request['rep_id']) is not int or not 1 <= request['rep_id'] <= 3):
            raise ValueError('invalid demo request')
        metadata, phases, context = self.cases[(request['exercise'], request['form'])]
        started = time.perf_counter()
        prediction = self.runtime.predict_reference_only(phases, context)
        result = asdict(prediction)
        return {**metadata, **result, 'rep_id': request['rep_id'],
                'matches_source_label': prediction.predicted_class == metadata['source_label'],
                'source': 'synthetic_training_replay', 'live': False,
                'actuators_enabled': False, 'animation_drives_features': False,
                'phase_order': [1, 2, 3], 'compute_ms': round((time.perf_counter() - started) * 1000, 3)}
