"""Clock-domain types used by event and fusion contracts."""

from __future__ import annotations

from typing import NewType, Protocol


MonotonicNanoseconds = NewType("MonotonicNanoseconds", int)
UtcMilliseconds = NewType("UtcMilliseconds", int)


class MonotonicClock(Protocol):
    """Injectable measurement/ordering clock unaffected by wall-clock changes."""

    def now_ns(self) -> MonotonicNanoseconds: ...


class UtcClock(Protocol):
    """Injectable display/correlation clock; never used for sensor ordering."""

    def now_ms(self) -> UtcMilliseconds: ...
