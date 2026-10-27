"""Structured vision health events and heartbeat expiry policy."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping
from uuid import UUID

from digital_spotter.contracts import (
    ComponentState,
    EventEnvelope,
    EventType,
    HealthState,
    MonotonicNanoseconds,
    Quality,
    ReasonCode,
    Source,
)


VISION_COMPONENT = "vision"
VISION_HEALTH_VERSION = "1"


@dataclass(frozen=True)
class VisionHealthSnapshot:
    """One bounded component-health observation produced by the worker."""

    state: ComponentState
    reason_codes: tuple[ReasonCode, ...]
    since_monotonic_ns: int
    last_success_monotonic_ns: int | None
    counters: Mapping[str, int]
    is_simulated: bool


def build_vision_health_envelope(
    *,
    snapshot: VisionHealthSnapshot,
    event_id: UUID,
    created_monotonic_ns: int,
    device_id: str | None,
) -> EventEnvelope[HealthState]:
    """Build a canonical health heartbeat without camera frames or landmarks."""

    if snapshot.is_simulated:
        quality = Quality.SIMULATED
    elif snapshot.state is ComponentState.DEGRADED:
        quality = Quality.VISION_DEGRADED
    elif snapshot.state in (ComponentState.STARTING, ComponentState.STOPPING):
        quality = Quality.UNAVAILABLE
    else:
        quality = Quality.GOOD

    payload = HealthState(
        component=VISION_COMPONENT,
        state=snapshot.state,
        reason_codes=snapshot.reason_codes,
        since_monotonic_ns=MonotonicNanoseconds(snapshot.since_monotonic_ns),
        versions={"health_contract": VISION_HEALTH_VERSION},
        last_success_monotonic_ns=(
            MonotonicNanoseconds(snapshot.last_success_monotonic_ns)
            if snapshot.last_success_monotonic_ns is not None
            else None
        ),
        counters=dict(snapshot.counters),
        is_simulated=snapshot.is_simulated,
    )
    return EventEnvelope[HealthState](
        event_type=EventType.HEALTH_STATE,
        event_id=event_id,
        source=Source.VISION,
        device_id=device_id,
        created_monotonic_ns=MonotonicNanoseconds(created_monotonic_ns),
        quality=quality,
        payload=payload,
    )


class VisionWatchdog:
    """Detect a missing vision heartbeat in the Pi monotonic clock domain."""

    def __init__(self, *, timeout_ns: int) -> None:
        if timeout_ns <= 0:
            raise ValueError("watchdog timeout must be positive")
        self.timeout_ns = timeout_ns
        self._last_heartbeat_ns: int | None = None

    @property
    def last_heartbeat_ns(self) -> int | None:
        return self._last_heartbeat_ns

    def observe(self, event: EventEnvelope[HealthState]) -> None:
        if (
            event.event_type is not EventType.HEALTH_STATE
            or event.source is not Source.VISION
            or event.payload.component != VISION_COMPONENT
        ):
            raise ValueError("watchdog accepts only canonical vision health events")
        observed_ns = int(event.created_monotonic_ns)
        if self._last_heartbeat_ns is not None and observed_ns < self._last_heartbeat_ns:
            raise ValueError("vision heartbeat moved backwards")
        self._last_heartbeat_ns = observed_ns

    def expired(self, *, now_monotonic_ns: int) -> bool:
        if now_monotonic_ns < 0:
            raise ValueError("watchdog time must not be negative")
        if self._last_heartbeat_ns is None:
            return True
        if now_monotonic_ns < self._last_heartbeat_ns:
            raise ValueError("watchdog time precedes the latest heartbeat")
        return now_monotonic_ns - self._last_heartbeat_ns > self.timeout_ns
