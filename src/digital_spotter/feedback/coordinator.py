"""Bounded demonstration feedback policy.

The model result selects GOOD/BAD. Browser scenario metadata never does.
Hardware execution failures are reported but cannot rewrite inference output.
"""

from __future__ import annotations

import asyncio
from enum import Enum
from typing import Protocol


class DemoCue(str, Enum):
    START = "start"
    GOOD = "good"
    BAD = "bad"
    COMPLETE = "complete"


class FeedbackEndpoint(Protocol):
    async def emit(self, cue: DemoCue) -> None: ...

    async def close(self) -> None: ...


class PiFeedbackEndpoint(FeedbackEndpoint, Protocol):
    def set_imu_state(self, state: str) -> None: ...

    def set_demo_active(self, active: bool) -> None: ...

    def set_network_state(self, state: str) -> None: ...


class FeedbackCoordinator:
    """Fan one policy decision out to the Pi and the single wearable owner."""

    def __init__(
        self,
        *,
        pi: PiFeedbackEndpoint | None,
        wearable: FeedbackEndpoint | None,
        enabled: bool,
        completion_delay_s: float = 2.1,
    ) -> None:
        if completion_delay_s < 0 or completion_delay_s > 10:
            raise ValueError("completion delay must be between 0 and 10 seconds")
        if enabled and (pi is None or wearable is None):
            raise ValueError("enabled feedback requires Pi and wearable endpoints")
        self.pi = pi
        self.wearable = wearable
        self.enabled = enabled
        self.completion_delay_s = completion_delay_s
        self._tasks: set[asyncio.Task] = set()
        self._closed = False

    async def _dispatch(self, cue: DemoCue) -> dict:
        if not self.enabled:
            return {
                "enabled": False,
                "cue": cue.value,
                "dispatched": False,
                "warnings": [],
            }
        if self._closed:
            return {
                "enabled": True,
                "cue": cue.value,
                "dispatched": False,
                "warnings": ["feedback:closed"],
            }
        endpoints = (("pi", self.pi), ("wearable", self.wearable))
        results = await asyncio.gather(
            *(endpoint.emit(cue) for _name, endpoint in endpoints),
            return_exceptions=True,
        )
        warnings = [
            f"{name}:{result}"
            for (name, _endpoint), result in zip(endpoints, results)
            if isinstance(result, Exception)
        ]
        return {
            "enabled": True,
            "cue": cue.value,
            "dispatched": not warnings,
            "warnings": warnings,
        }

    async def demo_start(self) -> dict:
        if self.enabled and not self._closed:
            self.pi.set_demo_active(True)
        return await self._dispatch(DemoCue.START)

    async def demo_result(self, *, predicted_class: int, final_rep: bool) -> dict:
        if predicted_class not in (0, 1):
            raise ValueError("predicted class must be 0 or 1")
        result = await self._dispatch(
            DemoCue.BAD if predicted_class == 1 else DemoCue.GOOD
        )
        if final_rep and self.enabled and not self._closed:
            task = asyncio.create_task(
                self._complete_after_delay(), name="demo-feedback-complete"
            )
            self._tasks.add(task)
            task.add_done_callback(self._tasks.discard)
        return result

    async def _complete_after_delay(self) -> None:
        await asyncio.sleep(self.completion_delay_s)
        await self._dispatch(DemoCue.COMPLETE)

    def set_imu_state(self, state: str) -> None:
        if state not in ("receiving", "degraded", "stale", "unavailable"):
            raise ValueError("invalid IMU feedback state")
        if self.enabled and not self._closed:
            self.pi.set_imu_state(state)

    def set_network_state(self, state: str) -> None:
        if state not in ("connected", "disconnected", "unavailable"):
            raise ValueError("invalid network feedback state")
        if self.enabled and not self._closed:
            self.pi.set_network_state(state)

    async def drain(self) -> None:
        if self._tasks:
            await asyncio.gather(*tuple(self._tasks))

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        for task in tuple(self._tasks):
            task.cancel()
        if self._tasks:
            await asyncio.gather(*tuple(self._tasks), return_exceptions=True)
        endpoints = [endpoint for endpoint in (self.pi, self.wearable) if endpoint]
        await asyncio.gather(
            *(endpoint.close() for endpoint in endpoints), return_exceptions=True
        )
