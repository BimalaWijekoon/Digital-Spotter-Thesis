from __future__ import annotations
import asyncio

from digital_spotter.feedback import DemoCue, FeedbackCoordinator
from digital_spotter.feedback.pi_gpio import PiGPIOFeedback


class RecordingEndpoint:
    def __init__(self, *, fail: bool = False) -> None:
        self.cues: list[DemoCue] = []
        self.imu_states: list[str] = []
        self.demo_active_states: list[bool] = []
        self.network_states: list[str] = []
        self.fail = fail

    async def emit(self, cue: DemoCue) -> None:
        if self.fail:
            raise RuntimeError("synthetic endpoint failure")
        self.cues.append(cue)

    def set_imu_state(self, state: str) -> None:
        self.imu_states.append(state)

    def set_demo_active(self, active: bool) -> None:
        self.demo_active_states.append(active)

    def set_network_state(self, state: str) -> None:
        self.network_states.append(state)

    async def close(self) -> None:
        return None


def test_demo_feedback_uses_actual_model_class_and_orders_final_cue():
    async def scenario() -> None:
        pi = RecordingEndpoint()
        wearable = RecordingEndpoint()
        coordinator = FeedbackCoordinator(
            pi=pi,
            wearable=wearable,
            enabled=True,
            completion_delay_s=0,
        )

        await coordinator.demo_start()
        good = await coordinator.demo_result(predicted_class=0, final_rep=False)
        bad = await coordinator.demo_result(predicted_class=1, final_rep=True)
        await coordinator.drain()

        assert pi.cues == [DemoCue.START, DemoCue.GOOD, DemoCue.BAD, DemoCue.COMPLETE]
        assert wearable.cues == pi.cues
        assert pi.demo_active_states == [True]
        assert good["cue"] == "good" and good["dispatched"] is True
        assert bad["cue"] == "bad" and bad["dispatched"] is True
        await coordinator.close()

    asyncio.run(scenario())


def test_feedback_failure_is_reported_without_changing_model_result_path():
    async def scenario() -> None:
        pi = RecordingEndpoint()
        wearable = RecordingEndpoint(fail=True)
        coordinator = FeedbackCoordinator(pi=pi, wearable=wearable, enabled=True)

        result = await coordinator.demo_result(predicted_class=1, final_rep=False)

        assert result == {
            "enabled": True,
            "cue": "bad",
            "dispatched": False,
            "warnings": ["wearable:synthetic endpoint failure"],
        }
        assert pi.cues == [DemoCue.BAD]
        await coordinator.close()

    asyncio.run(scenario())


def test_live_imu_state_is_only_forwarded_to_the_pi_indicator():
    pi = RecordingEndpoint()
    wearable = RecordingEndpoint()
    coordinator = FeedbackCoordinator(pi=pi, wearable=wearable, enabled=True)

    coordinator.set_imu_state("receiving")
    coordinator.set_imu_state("stale")

    assert pi.imu_states == ["receiving", "stale"]
    assert wearable.imu_states == []


def test_pi_indicator_uses_wifi_state_while_idle_and_demo_overrides_it():
    indicator = object.__new__(PiGPIOFeedback)
    indicator.imu_state = "receiving"
    indicator.network_state = "connected"
    indicator._demo_active = False

    assert indicator._base_color(0.0) == (0, 0, 42)

    indicator.set_network_state("disconnected")
    assert indicator._base_color(0.0) == (170, 55, 0)
    assert indicator._base_color(1.0) == (0, 0, 0)

    indicator.set_demo_active(True)
    assert indicator._base_color(0.0) == (0, 180, 255)


def test_network_state_is_only_forwarded_to_the_pi_indicator():
    pi = RecordingEndpoint()
    wearable = RecordingEndpoint()
    coordinator = FeedbackCoordinator(pi=pi, wearable=wearable, enabled=True)

    coordinator.set_network_state("connected")

    assert pi.network_states == ["connected"]
    assert wearable.network_states == []
