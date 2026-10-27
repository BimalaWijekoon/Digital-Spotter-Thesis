"""Synthetic demo inference is real, isolated from live workouts and actuators."""
import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from digital_spotter.inference.v5_candidate import V5CandidateRuntime
from digital_spotter.inference.v5_model import V5Prediction
from digital_spotter.inference.v5_demo import DemoReplay
from digital_spotter.api.workout import allowed_mutation, execute_demo, execute_demo_start
from digital_spotter.feedback import DemoCue


PACKAGE = Path(__file__).resolve().parents[1] / 'models/digital_spotter_v5_imu_synthetic_r1'


@pytest.fixture(scope='module')
def demo():
    if not PACKAGE.is_dir():
        pytest.skip('Frozen local research model package is not installed')
    return DemoReplay(V5CandidateRuntime(PACKAGE))


def test_owner_requested_curated_bad_squat_is_a_real_correctly_recognised_example(demo):
    result = demo.predict({'exercise': 'squat', 'form': 'incorrect', 'rep_id': 1})
    assert result['fixture_index'] == 6
    assert result['source_label'] == 1 and result['predicted_class'] == 1
    assert result['calibrated_probability'] == pytest.approx(.8506134321850672, abs=1e-6)
    assert result['threshold'] == .3976007923801824
    assert demo.catalog()['selection_policy'] == 'curated_demonstration_not_accuracy_evaluation'


def test_replay_charts_expose_exact_phase_imu_inputs_not_generated_live_samples(demo):
    for case in demo.catalog()['cases']:
        replay = case['imu_replay']
        assert replay['version'] == 'demo_phase_imu_v1'
        assert replay['source'] == 'synthetic_training_replay'
        assert replay['representation'] == 'phase_medians'
        assert replay['measured_timestamps'] is False
        assert replay['units'] == {'acceleration_m_s2': 'm/s^2',
                                   'angular_velocity_rad_s': 'rad/s'}
        assert [row['phase'] for row in replay['phases']] == [1, 2, 3]
        _, inputs, _ = demo.cases[(case['exercise'], case['form'])]
        for plotted, model_input in zip(replay['phases'], inputs):
            assert plotted['acceleration_m_s2'] == [model_input[f'IMU_Acc_{axis}']
                                                   for axis in 'XYZ']
            assert plotted['angular_velocity_rad_s'] == [model_input[f'IMU_Gyro_{axis}']
                                                        for axis in 'XYZ']
            assert 't_ms' not in plotted and 'sequence' not in plotted


@pytest.mark.parametrize('exercise,form,index,load', [
    ('squat', 'correct', 5, 35), ('squat', 'incorrect', 6, 35),
    ('deadlift', 'correct', 42, 50), ('deadlift', 'incorrect', 45, 50),
])
def test_replay_calls_canonical_model_with_original_context(demo, exercise, form, index, load):
    case = next(case for case in demo.catalog()['cases']
                if case['exercise'] == exercise and case['form'] == form)
    assert case['fixture_index'] == index
    assert case['load_kg'] == load
    result = demo.predict({'exercise': exercise, 'form': form, 'rep_id': 1})
    assert result['fixture_index'] == index and result['load_kg'] == load
    assert 0 <= result['raw_probability'] <= 1
    assert result['predicted_class'] == int(result['calibrated_probability'] >= result['threshold'])
    assert result['reference_only'] is True and result['live'] is False
    assert result['actuators_enabled'] is False and result['animation_drives_features'] is False
    assert result['source'] == 'synthetic_training_replay'


def test_demo_boundary_has_own_origin_header_and_never_accepts_forced_prediction(demo):
    origin = 'http://127.0.0.1:4176'
    assert allowed_mutation({'Origin': origin, 'X-DS-Demo': '1'}, origins={origin}, demo=True)
    assert not allowed_mutation({'Origin': origin, 'X-DS-Workout': '1'}, origins={origin}, demo=True)
    assert not allowed_mutation({'Origin': 'https://other.test', 'X-DS-Demo': '1'}, origins={origin}, demo=True)
    service = SimpleNamespace(state='idle', pose_test=None, demo=demo)
    request = {'exercise': 'squat', 'form': 'correct', 'rep_id': 1}
    with pytest.raises(ValueError, match='invalid demo request'):
        asyncio.run(execute_demo(service, {**request, 'predicted_class': 0}))
    service.state = 'active'
    with pytest.raises(ValueError, match='live session'):
        asyncio.run(execute_demo(service, request))
    service.state, service.demo = 'idle', None
    with pytest.raises(ValueError, match='not enabled'):
        asyncio.run(execute_demo(service, request))


def test_demo_feedback_uses_actual_prediction_and_final_rep_completion(demo):
    class Feedback:
        enabled = True

        def __init__(self):
            self.started = 0
            self.results = []

        async def demo_start(self):
            self.started += 1
            return {'enabled': True, 'cue': 'start', 'dispatched': True, 'warnings': []}

        async def demo_result(self, *, predicted_class, final_rep):
            self.results.append((predicted_class, final_rep))
            cue = DemoCue.BAD if predicted_class else DemoCue.GOOD
            return {'enabled': True, 'cue': cue.value, 'dispatched': True, 'warnings': []}

    feedback = Feedback()
    service = SimpleNamespace(state='idle', pose_test=None, demo=demo, feedback=feedback)

    started = asyncio.run(execute_demo_start(service))
    result = asyncio.run(execute_demo(
        service, {'exercise': 'squat', 'form': 'incorrect', 'rep_id': 3}
    ))

    assert started['cue'] == 'start' and feedback.started == 1
    assert result['predicted_class'] == 1
    assert result['actuators_enabled'] is True
    assert result['feedback']['cue'] == 'bad'
    assert feedback.results == [(1, True)]


def test_selected_form_does_not_override_actual_model_decision(demo):
    original = demo.runtime
    # A deliberately disagreeing model response protects against wiring form -> class.
    demo.runtime = SimpleNamespace(predict_reference_only=lambda phases, context: V5Prediction(
        raw_probability=.1, calibrated_probability=.2, predicted_class=0,
        threshold=.4, model_version=original.model_version, reference_only=True))
    try:
        result = demo.predict({'exercise': 'deadlift', 'form': 'incorrect', 'rep_id': 2})
        assert result['predicted_class'] == 0
        assert result['source_label'] == 1
        assert result['matches_source_label'] is False
    finally:
        demo.runtime = original
