"""Browser-facing contracts for direct video and pose-overlay synchronization.

Internal events keep nanosecond precision. Browser payloads deliberately use
integer microseconds so long-running monotonic timestamps remain exact in a
JavaScript Number for far longer than the product's expected uptime.
"""

from __future__ import annotations

from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from digital_spotter.contracts import (
    EventEnvelope,
    EventType,
    PoseLandmark,
    PoseSample,
    Quality,
    Source,
)


BROWSER_VIDEO_SCHEMA_VERSION = 1
MAX_JAVASCRIPT_SAFE_INTEGER = (1 << 53) - 1

JavaScriptSafeInteger = Annotated[
    int,
    Field(ge=0, le=MAX_JAVASCRIPT_SAFE_INTEGER),
]


class BrowserVideoContract(BaseModel):
    """Strict base for untrusted browser-bound and browser-originated data."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        allow_inf_nan=False,
    )


class BrowserPoseSample(BrowserVideoContract):
    schema_version: Literal[1] = BROWSER_VIDEO_SCHEMA_VERSION
    message_type: Literal["pose_sample"] = "pose_sample"
    event_id: UUID
    frame_sequence: JavaScriptSafeInteger
    captured_monotonic_us: JavaScriptSafeInteger
    image_width: int = Field(gt=0, le=8192)
    image_height: int = Field(gt=0, le=8192)
    landmark_schema_version: int = Field(ge=0, le=0xFFFF)
    landmarks: tuple[PoseLandmark, ...] = Field(max_length=64)
    angles: dict[str, float] = Field(default_factory=dict, max_length=64)
    pose_confidence: float = Field(ge=0.0, le=1.0)
    quality: Quality
    processing_latency_us: JavaScriptSafeInteger
    frames_dropped_since_previous: int = Field(ge=0, le=0xFFFFFFFF)
    is_simulated: bool

    @model_validator(mode="after")
    def simulation_marker_matches_quality(self) -> "BrowserPoseSample":
        if self.is_simulated is not (self.quality is Quality.SIMULATED):
            raise ValueError("simulation marker must match pose quality")
        return self


class BrowserClockRequest(BrowserVideoContract):
    schema_version: Literal[1] = BROWSER_VIDEO_SCHEMA_VERSION
    message_type: Literal["clock_sync_request"] = "clock_sync_request"
    request_id: str = Field(
        min_length=1,
        max_length=64,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$",
    )
    client_sent_ms: float = Field(ge=0.0)


class BrowserClockResponse(BrowserVideoContract):
    schema_version: Literal[1] = BROWSER_VIDEO_SCHEMA_VERSION
    message_type: Literal["clock_sync_response"] = "clock_sync_response"
    request_id: str = Field(
        min_length=1,
        max_length=64,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$",
    )
    client_sent_ms: float = Field(ge=0.0)
    server_received_monotonic_us: JavaScriptSafeInteger
    server_sent_monotonic_us: JavaScriptSafeInteger

    @model_validator(mode="after")
    def sent_cannot_precede_received(self) -> "BrowserClockResponse":
        if self.server_sent_monotonic_us < self.server_received_monotonic_us:
            raise ValueError("server sent time cannot precede received time")
        return self


def pose_event_for_browser(event: EventEnvelope[PoseSample]) -> BrowserPoseSample:
    """Reduce a canonical vision event to the explicit browser overlay contract."""

    if (
        event.event_type is not EventType.POSE_SAMPLE
        or event.source is not Source.VISION
        or not isinstance(event.payload, PoseSample)
    ):
        raise ValueError("expected a canonical vision pose event")

    pose = event.payload
    return BrowserPoseSample(
        event_id=event.event_id,
        frame_sequence=pose.frame_sequence,
        captured_monotonic_us=int(pose.captured_monotonic_ns) // 1_000,
        image_width=pose.image_width,
        image_height=pose.image_height,
        landmark_schema_version=pose.landmark_schema_version,
        landmarks=pose.landmarks,
        angles=pose.angles,
        pose_confidence=pose.pose_confidence,
        quality=pose.quality,
        processing_latency_us=pose.processing_latency_ns // 1_000,
        frames_dropped_since_previous=pose.frames_dropped_since_previous,
        is_simulated=pose.quality is Quality.SIMULATED,
    )


def browser_clock_response(
    request: BrowserClockRequest,
    *,
    server_received_monotonic_ns: int,
    server_sent_monotonic_ns: int,
) -> BrowserClockResponse:
    """Build the server half of a four-timestamp monotonic clock exchange."""

    return BrowserClockResponse(
        request_id=request.request_id,
        client_sent_ms=request.client_sent_ms,
        server_received_monotonic_us=server_received_monotonic_ns // 1_000,
        server_sent_monotonic_us=server_sent_monotonic_ns // 1_000,
    )


__all__ = [
    "BROWSER_VIDEO_SCHEMA_VERSION",
    "MAX_JAVASCRIPT_SAFE_INTEGER",
    "BrowserClockRequest",
    "BrowserClockResponse",
    "BrowserPoseSample",
    "browser_clock_response",
    "pose_event_for_browser",
]
