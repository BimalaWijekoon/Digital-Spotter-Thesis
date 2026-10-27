"""Non-blocking Raspberry Pi RGB and buzzer execution for demo feedback."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass

from .coordinator import DemoCue


@dataclass(frozen=True)
class CueProfile:
    color: tuple[int, int, int]
    mode: str
    duration_s: float
    period_s: float
    buzzer_pattern_s: tuple[float, ...]


CUE_PROFILES = {
    DemoCue.START: CueProfile((0, 210, 255), "flash", 0.7, 0.14, (0.10, 0.08, 0.10)),
    DemoCue.GOOD: CueProfile((0, 255, 0), "solid", 2.0, 1.0, (0.12,)),
    DemoCue.BAD: CueProfile((255, 0, 0), "flash", 2.0, 0.15,
                            (0.10, 0.08, 0.10, 0.08, 0.10)),
    DemoCue.COMPLETE: CueProfile((180, 0, 255), "solid", 1.0, 1.0, (0.25,)),
}


class PiGPIOFeedback:
    """One asyncio-owned renderer; no sleep occurs in capture or inference code."""

    def __init__(
        self,
        *,
        red_pin: int,
        green_pin: int,
        blue_pin: int,
        buzzer_pin: int,
        common_anode: bool = False,
        gpio_module=None,
    ) -> None:
        pins = (red_pin, green_pin, blue_pin, buzzer_pin)
        if any(type(pin) is not int or not 0 <= pin <= 27 for pin in pins):
            raise ValueError("Pi feedback pins must be distinct BCM GPIO 0-27")
        if len(set(pins)) != len(pins):
            raise ValueError("Pi feedback pins must be distinct")
        if gpio_module is None:
            try:
                import RPi.GPIO as gpio_module  # type: ignore[import-not-found]
            except ImportError as exc:
                raise RuntimeError("RPi.GPIO is required for enabled Pi feedback") from exc
        self.gpio = gpio_module
        self.rgb_pins = (red_pin, green_pin, blue_pin)
        self.buzzer_pin = buzzer_pin
        self.common_anode = common_anode
        self.imu_state = "unavailable"
        self.network_state = "unavailable"
        self._demo_active = False
        self._override: tuple[DemoCue, CueProfile, float] | None = None
        self._render_task: asyncio.Task | None = None
        self._buzzer_task: asyncio.Task | None = None
        self._closed = False
        self._last_color: tuple[int, int, int] | None = None
        self._setup()

    def _setup(self) -> None:
        self.gpio.setmode(self.gpio.BCM)
        for pin in (*self.rgb_pins, self.buzzer_pin):
            self.gpio.setup(pin, self.gpio.OUT, initial=self.gpio.LOW)
        self._rgb_pwm = [self.gpio.PWM(pin, 100) for pin in self.rgb_pins]
        for channel in self._rgb_pwm:
            channel.start(0)

    async def open(self) -> None:
        if self._closed:
            raise RuntimeError("Pi feedback is closed")
        if self._render_task is None:
            self._render_task = asyncio.create_task(
                self._render_loop(), name="pi-feedback-renderer"
            )

    def set_imu_state(self, state: str) -> None:
        if state not in ("receiving", "degraded", "stale", "unavailable"):
            raise ValueError("invalid IMU feedback state")
        self.imu_state = state

    def set_demo_active(self, active: bool) -> None:
        self._demo_active = bool(active)

    def set_network_state(self, state: str) -> None:
        if state not in ("connected", "disconnected", "unavailable"):
            raise ValueError("invalid network feedback state")
        self.network_state = state

    async def emit(self, cue: DemoCue) -> None:
        if self._closed:
            raise RuntimeError("Pi feedback is closed")
        profile = CUE_PROFILES[cue]
        if cue is DemoCue.START:
            self._demo_active = True
        self._override = (cue, profile, time.monotonic())
        if self._buzzer_task is not None:
            self._buzzer_task.cancel()
            await asyncio.gather(self._buzzer_task, return_exceptions=True)
        self._buzzer_task = asyncio.create_task(
            self._play_buzzer(profile.buzzer_pattern_s), name="pi-feedback-buzzer"
        )

    def _base_color(self, now: float) -> tuple[int, int, int]:
        if not self._demo_active:
            if self.network_state == "connected":
                return (0, 0, 42)
            return (170, 55, 0) if now % 2.0 < 0.35 else (0, 0, 0)
        if self.imu_state in ("receiving", "degraded"):
            return (0, 180, 255) if now % 0.5 < 0.12 else (0, 8, 12)
        if self.imu_state == "stale":
            return (255, 80, 0) if now % 0.5 < 0.25 else (0, 0, 0)
        return (0, 0, 90) if now % 1.2 < 0.15 else (0, 0, 4)

    def _current_color(self, now: float) -> tuple[int, int, int]:
        if self._override is None:
            return self._base_color(now)
        cue, profile, started = self._override
        elapsed = now - started
        if elapsed >= profile.duration_s:
            self._override = None
            if cue is DemoCue.COMPLETE:
                self._demo_active = False
            return self._base_color(now)
        if profile.mode == "solid":
            return profile.color
        return profile.color if elapsed % (2 * profile.period_s) < profile.period_s else (0, 0, 0)

    async def _render_loop(self) -> None:
        try:
            while True:
                self._apply_color(self._current_color(time.monotonic()))
                await asyncio.sleep(0.04)
        except asyncio.CancelledError:
            raise

    def _apply_color(self, color: tuple[int, int, int]) -> None:
        if color == self._last_color:
            return
        self._last_color = color
        for channel, value in zip(self._rgb_pwm, color):
            duty = value * 100.0 / 255.0
            channel.ChangeDutyCycle(100.0 - duty if self.common_anode else duty)

    async def _play_buzzer(self, pattern: tuple[float, ...]) -> None:
        try:
            for index, duration in enumerate(pattern):
                self.gpio.output(
                    self.buzzer_pin,
                    self.gpio.HIGH if index % 2 == 0 else self.gpio.LOW,
                )
                await asyncio.sleep(duration)
        finally:
            self.gpio.output(self.buzzer_pin, self.gpio.LOW)

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        for task in (self._render_task, self._buzzer_task):
            if task is not None:
                task.cancel()
        await asyncio.gather(
            *(task for task in (self._render_task, self._buzzer_task) if task),
            return_exceptions=True,
        )
        self._apply_color((0, 0, 0))
        self.gpio.output(self.buzzer_pin, self.gpio.LOW)
        for channel in self._rgb_pwm:
            channel.stop()
        self.gpio.cleanup([*self.rgb_pins, self.buzzer_pin])
