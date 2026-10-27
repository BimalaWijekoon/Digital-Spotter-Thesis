"""Deterministic, non-real replay fixtures for contract and regression work."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from digital_spotter.contracts import (
    AnalysisEvent,
    EventEnvelope,
    EventType,
    HealthState,
    IMUSample,
    MonotonicNanoseconds,
    PoseSample,
    RepEvent,
    RepPhase,
)
from digital_spotter.contracts.events import FusedSample


MAX_FIXTURE_BYTES = 2 * 1024 * 1024
MAX_FIXTURE_EVENTS = 10_000


class ReplayFixtureError(ValueError):
    """Raised when replay evidence is malformed or contradicts expectations."""


class ReplayModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, protected_namespaces=())


class FixtureProvenance(ReplayModel):
    kind: Literal["synthetic"]
    contains_person_data: Literal[False]
    consent: Literal["not_applicable_synthetic"]
    description: str = Field(min_length=1, max_length=512)


class VideoFixture(ReplayModel):
    kind: Literal["none", "synthetic"]
    path: str | None = Field(default=None, max_length=255)
    sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    media_type: Literal["video/x-yuv4mpeg"] | None = None
    frame_count: int | None = Field(default=None, ge=1, le=MAX_FIXTURE_EVENTS)
    captured_monotonic_ns: tuple[MonotonicNanoseconds, ...] = Field(
        default_factory=tuple,
        max_length=MAX_FIXTURE_EVENTS,
    )

    @model_validator(mode="after")
    def synthetic_video_requires_identity(self) -> "VideoFixture":
        if self.kind == "synthetic":
            if self.path is None or self.sha256 is None or self.media_type is None:
                raise ValueError("synthetic video requires path, sha256, and media_type")
            if self.frame_count is None or len(self.captured_monotonic_ns) != self.frame_count:
                raise ValueError("synthetic video timestamps must match frame_count")
            timestamps = self.captured_monotonic_ns
            if any(value < 0 for value in timestamps):
                raise ValueError("synthetic video timestamps cannot be negative")
            if any(current <= previous for previous, current in zip(timestamps, timestamps[1:])):
                raise ValueError("synthetic video timestamps must increase")
        if self.kind == "none" and (
            self.path is not None
            or self.sha256 is not None
            or self.media_type is not None
            or self.frame_count is not None
            or self.captured_monotonic_ns
        ):
            raise ValueError("video kind none cannot name an artifact")
        if self.path is not None:
            relative = PurePosixPath(self.path)
            if relative.is_absolute() or ".." in relative.parts or "\\" in self.path:
                raise ValueError("video path must be a safe fixture-relative POSIX path")
        return self


class ReplayExpectation(ReplayModel):
    event_count: int = Field(ge=1, le=MAX_FIXTURE_EVENTS)
    phase_sequence: tuple[RepPhase, ...] = Field(default_factory=tuple, max_length=128)
    analysis_labels: tuple[str, ...] = Field(default_factory=tuple, max_length=128)
    imu_gap_count: int = Field(ge=0)
    clock_reset_count: int = Field(ge=0)
    event_digest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class ReplayFixture(ReplayModel):
    schema_version: Literal[1]
    fixture_id: str = Field(
        min_length=3,
        max_length=128,
        pattern=r"^[a-z0-9][a-z0-9._-]+$",
    )
    adapter_mode: Literal["replay"]
    provenance: FixtureProvenance
    video: VideoFixture
    events: tuple[dict[str, Any], ...] = Field(min_length=1, max_length=MAX_FIXTURE_EVENTS)
    expected: ReplayExpectation


class ReplayResult(ReplayModel):
    fixture_id: str
    adapter_mode: Literal["replay"] = "replay"
    is_real: Literal[False] = False
    persistence_allowed: Literal[False] = False
    event_count: int
    phase_sequence: tuple[RepPhase, ...]
    analysis_labels: tuple[str, ...]
    imu_gap_count: int
    clock_reset_count: int
    event_digest_sha256: str


_ENVELOPE_TYPES = {
    EventType.IMU_SAMPLE: EventEnvelope[IMUSample],
    EventType.POSE_SAMPLE: EventEnvelope[PoseSample],
    EventType.FUSED_SAMPLE: EventEnvelope[FusedSample],
    EventType.REP_EVENT: EventEnvelope[RepEvent],
    EventType.ANALYSIS_EVENT: EventEnvelope[AnalysisEvent],
    EventType.HEALTH_STATE: EventEnvelope[HealthState],
}


def _parse_envelope(raw: dict[str, Any]):
    try:
        event_type = EventType(raw.get("event_type"))
        return _ENVELOPE_TYPES[event_type].model_validate(raw)
    except Exception as exc:
        raise ReplayFixtureError(f"invalid replay event: {exc}") from exc


def load_replay_fixture(path: Path) -> ReplayFixture:
    try:
        if not path.is_file():
            raise ReplayFixtureError(f"fixture not found: {path}")
        if path.stat().st_size > MAX_FIXTURE_BYTES:
            raise ReplayFixtureError(f"fixture exceeds {MAX_FIXTURE_BYTES} bytes")
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ReplayFixtureError("fixture root must be an object")
        fixture = ReplayFixture.model_validate(raw)
        if fixture.video.kind == "synthetic":
            fixture_root = path.parent.resolve()
            video_path = (fixture_root / fixture.video.path).resolve()
            try:
                video_path.relative_to(fixture_root)
            except ValueError as exc:
                raise ReplayFixtureError("video path escapes fixture directory") from exc
            if not video_path.is_file():
                raise ReplayFixtureError("synthetic video artifact not found")
            if video_path.stat().st_size > MAX_FIXTURE_BYTES:
                raise ReplayFixtureError(f"video exceeds {MAX_FIXTURE_BYTES} bytes")
            if hashlib.sha256(video_path.read_bytes()).hexdigest() != fixture.video.sha256:
                raise ReplayFixtureError("synthetic video hash mismatch")
        return fixture
    except ReplayFixtureError:
        raise
    except Exception as exc:
        raise ReplayFixtureError(f"invalid replay fixture: {exc}") from exc


@dataclass
class ReplayClock:
    """A no-sleep monotonic clock driven only by fixture timestamps."""

    current_ns: MonotonicNanoseconds = MonotonicNanoseconds(0)

    def advance_to(self, value: MonotonicNanoseconds) -> None:
        if value < self.current_ns:
            raise ReplayFixtureError("replay clock cannot move backward")
        self.current_ns = value

    def now_ns(self) -> MonotonicNanoseconds:
        return self.current_ns


class ReplayAdapter:
    """Fixture adapter that can never be mistaken for release hardware."""

    mode: Literal["replay"] = "replay"
    is_real: Literal[False] = False
    is_simulated: Literal[True] = True
    persistence_allowed: Literal[False] = False

    def __init__(self, fixture: ReplayFixture):
        self.fixture = fixture

    def run(self, *, verify_expected: bool = True) -> ReplayResult:
        clock = ReplayClock()
        digest = hashlib.sha256()
        event_ids = set()
        phases: list[RepPhase] = []
        labels: list[str] = []
        imu_gaps = 0
        clock_resets = 0
        previous_imu: IMUSample | None = None

        for raw_event in self.fixture.events:
            envelope = _parse_envelope(raw_event)
            if envelope.event_id in event_ids:
                raise ReplayFixtureError("duplicate replay event_id")
            event_ids.add(envelope.event_id)
            clock.advance_to(envelope.created_monotonic_ns)
            encoded = envelope.to_messagepack()
            digest.update(len(encoded).to_bytes(4, "big"))
            digest.update(encoded)

            payload = envelope.payload
            if isinstance(payload, IMUSample):
                imu_gaps += payload.gap_count_since_previous
                if previous_imu is not None and payload.boot_id == previous_imu.boot_id:
                    sequence_gap = (payload.sequence - previous_imu.sequence - 1) & 0xFFFF
                    if sequence_gap != payload.gap_count_since_previous:
                        raise ReplayFixtureError("declared IMU gap does not match sequence")
                if previous_imu is not None and payload.boot_id != previous_imu.boot_id:
                    if payload.clock_state.value != "reset":
                        raise ReplayFixtureError("new IMU boot_id must declare reset clock state")
                    clock_resets += 1
                previous_imu = payload
            elif isinstance(payload, RepEvent) and payload.phase is not None:
                phases.append(payload.phase)
            elif isinstance(payload, AnalysisEvent):
                labels.append(payload.label)

        result = ReplayResult(
            fixture_id=self.fixture.fixture_id,
            event_count=len(self.fixture.events),
            phase_sequence=tuple(phases),
            analysis_labels=tuple(labels),
            imu_gap_count=imu_gaps,
            clock_reset_count=clock_resets,
            event_digest_sha256=digest.hexdigest(),
        )
        if verify_expected:
            expected = self.fixture.expected
            comparisons = {
                "event_count": (result.event_count, expected.event_count),
                "phase_sequence": (result.phase_sequence, expected.phase_sequence),
                "analysis_labels": (result.analysis_labels, expected.analysis_labels),
                "imu_gap_count": (result.imu_gap_count, expected.imu_gap_count),
                "clock_reset_count": (result.clock_reset_count, expected.clock_reset_count),
                "event_digest_sha256": (
                    result.event_digest_sha256,
                    expected.event_digest_sha256,
                ),
            }
            mismatches = [name for name, values in comparisons.items() if values[0] != values[1]]
            if mismatches:
                raise ReplayFixtureError("replay expectation mismatch: " + ", ".join(mismatches))
        return result
