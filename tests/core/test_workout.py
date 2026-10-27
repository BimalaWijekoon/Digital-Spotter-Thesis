"""Focused field-workout lifecycle checks; deterministic inputs, not hardware."""
import asyncio
from types import SimpleNamespace

import pytest

from digital_spotter.core.workout import WorkoutService
from digital_spotter.core.sessions import LocalSessionService
from digital_spotter.persistence import SQLiteRepository, migrate_database
from digital_spotter.inference.v5_model import MODEL_VERSION


class FixedNetworkProbe:
    def __init__(self, state='connected'):
        self.state = state
        self.calls = 0

    def sample(self):
        self.calls += 1
        return {'state': self.state, 'interface': 'wlan0',
                'has_local_address': self.state == 'connected'}


def make_service(tmp_path, *, model_version=MODEL_VERSION, network_probe=None):
    path = tmp_path / 'workouts.sqlite3'
    migrate_database(path)
    repository = SQLiteRepository(path)
    model = SimpleNamespace(threshold=0.20549274582373653, model_version=model_version)
    service = WorkoutService(
        session=LocalSessionService(repository=repository, imu_ring_capacity=1500),
        repository=repository, model=model,
        edge_device_id='pi4-test', imu_device_id='dsimu-test',
        network_probe=network_probe,
    )
    return service, repository


def test_start_pause_resume_stop_are_real_and_save_context(tmp_path):
    async def run():
        service, repository = make_service(tmp_path)
        await service.open()
        assert service.snapshot()['session']['state'] == 'idle'
        result = await service.command('start', {'exercise_id': 1, 'load_kg': 35})
        session_id = result['session']['id']
        assert result['session']['state'] == 'active'
        assert result['session']['load_kg'] == 35
        assert (await service.command('pause', {}))['session']['state'] == 'paused'
        assert (await service.command('resume', {}))['session']['state'] == 'active'
        result = await service.command('stop', {})
        assert result['session']['state'] == 'idle'
        assert result['session']['saved'] is True
        assert repository.get_active_session() is None
        from uuid import UUID
        assert repository.get_session(UUID(session_id)).state == 'completed'
        assert result['analysis']['state'] == 'unavailable'
        assert 'probability' not in result['analysis']
        completed = result['completed_set']
        assert completed['schema_version'] == 1
        assert completed['kind'] == 'digital_spotter_research_set'
        assert completed['status'] == 'complete'
        assert completed['hardware_simulated'] is False
        assert completed['session_id'] == session_id
        assert completed['exercise'] == {'id': 1, 'name': 'Deadlift', 'load_kg': 35.0}
        assert completed['rep_count'] == 0
        assert completed['model']['live_inputs_verified'] is False
        assert completed['analysis']['state'] == 'unavailable'
        assert completed['warnings'] == ['v5_live_feature_contract_unverified']
        await service.close()
    asyncio.run(run())


def test_invalid_context_and_repeated_start_do_not_replace_session(tmp_path):
    async def run():
        service, repository = make_service(tmp_path)
        await service.open()
        for data in ({'exercise_id': 9, 'load_kg': 10},
                     {'exercise_id': 0, 'load_kg': -1},
                     {'exercise_id': 0, 'load_kg': float('nan')}):
            with pytest.raises(ValueError):
                await service.command('start', data)
        await service.command('start', {'exercise_id': 0, 'load_kg': 0})
        first = repository.get_active_session().session_uuid
        with pytest.raises(ValueError):
            await service.command('start', {'exercise_id': 1, 'load_kg': 20})
        assert repository.get_active_session().session_uuid == first
        await service.command('stop', {})
        await service.close()
    asyncio.run(run())


def test_idle_monitor_does_not_create_workout_or_fake_model_readiness(tmp_path):
    async def run():
        service, repository = make_service(tmp_path)
        await service.open()
        state = service.snapshot()
        assert state['camera']['state'] == 'unavailable'
        assert state['wearable']['state'] == 'unavailable'
        assert state['model']['loaded'] is True
        assert state['model']['live_inputs_verified'] is False
        assert state['analysis']['reason'] == 'v5_live_feature_contract_unverified'
        assert repository.get_active_session() is None
        assert service.imu_window()['samples'] == []
        await service.close()
    asyncio.run(run())


def test_selected_candidate_version_is_saved_without_enabling_scores(tmp_path):
    async def run():
        version = 'digital_spotter_v5_imu_synthetic_r1'
        service, repository = make_service(tmp_path, model_version=version)
        await service.open()
        started = await service.command('start', {'exercise_id': 0, 'load_kg': 20})
        assert started['model']['version'] == version
        assert started['model']['live_inputs_verified'] is False
        from uuid import UUID
        saved = repository.get_session(UUID(started['session']['id']))
        assert saved.model_package_id == version
        assert started['analysis']['state'] == 'unavailable'
        await service.command('stop', {})
        await service.close()
    asyncio.run(run())


def test_workout_status_exposes_bounded_pi_network_state(tmp_path):
    probe = FixedNetworkProbe()
    service, _repository = make_service(tmp_path, network_probe=probe)

    assert service.snapshot()['network'] == {
        'state': 'connected', 'interface': 'wlan0', 'has_local_address': True,
    }
    assert probe.calls == 1
