"""Focused completed-set export contract without hardware or database I/O."""
import asyncio
from types import SimpleNamespace

from digital_spotter.core.workout import WorkoutService


class ImmediateQueue:
    async def submit(self, operation):
        operation()


class FakeRepository:
    def save_workout_context(self, **_values):
        return None


class FakeSession:
    def __init__(self):
        self.database_queue = ImmediateQueue()

    async def begin(self, _request):
        return None

    async def stop(self, **_values):
        return None

    def poll_completed_reps(self):
        return []

    def discard_partial_rep(self):
        return None


def test_stop_returns_truthful_downloadable_set_summary():
    async def run():
        service = WorkoutService(
            session=FakeSession(), repository=FakeRepository(),
            model=SimpleNamespace(model_version='v5-test', threshold=0.4),
            edge_device_id='pi-test', imu_device_id='imu-test',
        )
        started = await service.command('start', {'exercise_id': 1, 'load_kg': 35})
        completed = (await service.command('stop', {}))['completed_set']

        assert completed['session_id'] == started['session']['id']
        assert completed['exercise'] == {'id': 1, 'name': 'Deadlift', 'load_kg': 35.0}
        assert completed['hardware_simulated'] is False
        assert completed['model'] == {'version': 'v5-test', 'live_inputs_verified': False}
        assert completed['analysis']['state'] == 'unavailable'
        assert completed['warnings'] == ['v5_live_feature_contract_unverified']

    asyncio.run(run())
