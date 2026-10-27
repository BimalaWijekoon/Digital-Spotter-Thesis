from __future__ import annotations

from uuid import UUID

import pytest
from pydantic import ValidationError

from digital_spotter.api.video import (
    BROWSER_VIDEO_SCHEMA_VERSION,
    MAX_JAVASCRIPT_SAFE_INTEGER,
    BrowserClockRequest,
    browser_clock_response,
    pose_event_for_browser,
)
from digital_spotter.api.research_telemetry import ResearchPoseHub
from digital_spotter.contracts import (
    EventEnvelope,
    EventType,
    MonotonicNanoseconds,
    PoseLandmark,
    PoseSample,
    Quality,
    Source,
    new_event_id,
)
from digital_spotter.imu.uds import encode_event_frame


EVENT_ID = new_event_id(unix_time_ms=1_750_000_000_000, random_bits=43)


def _pose_event(*, quality: Quality = Quality.GOOD) -> EventEnvelope[PoseSample]:
    capture_ns = MonotonicNanoseconds(9_007_199_254_740_000)
    payload = PoseSample(
        camera_id="picam0",
        frame_sequence=41,
        captured_monotonic_ns=capture_ns,
        processed_monotonic_ns=MonotonicNanoseconds(capture_ns + 2_500_000),
        image_width=640,
        image_height=360,
        landmark_schema_version=1,
        landmarks=(PoseLandmark(x=0.25, y=0.75, z=-0.1, visibility=0.92),),
        angles={"left_knee": 91.25},
        pose_confidence=0.88,
        quality=quality,
        processing_latency_ns=2_500_000,
        frames_dropped_since_previous=2,
    )
    return EventEnvelope[PoseSample](
        event_type=EventType.POSE_SAMPLE,
        event_id=EVENT_ID,
        source=Source.VISION,
        captured_monotonic_ns=capture_ns,
        created_monotonic_ns=MonotonicNanoseconds(capture_ns + 2_600_000),
        quality=quality,
        payload=payload,
    )


def test_pose_event_is_reduced_to_a_browser_safe_versioned_payload():
    payload = pose_event_for_browser(_pose_event())
    encoded = payload.model_dump(mode="json")

    assert encoded == {
        "schema_version": BROWSER_VIDEO_SCHEMA_VERSION,
        "message_type": "pose_sample",
        "event_id": str(EVENT_ID),
        "frame_sequence": 41,
        "captured_monotonic_us": 9_007_199_254_740,
        "image_width": 640,
        "image_height": 360,
        "landmark_schema_version": 1,
        "landmarks": [{"x": 0.25, "y": 0.75, "z": -0.1, "visibility": 0.92}],
        "angles": {"left_knee": 91.25},
        "pose_confidence": 0.88,
        "quality": "good",
        "processing_latency_us": 2_500,
        "frames_dropped_since_previous": 2,
        "is_simulated": False,
    }
    assert encoded["captured_monotonic_us"] <= MAX_JAVASCRIPT_SAFE_INTEGER


def test_simulation_is_explicit_and_wrong_sources_are_rejected():
    simulated = pose_event_for_browser(_pose_event(quality=Quality.SIMULATED))
    assert simulated.is_simulated is True

    inconsistent = simulated.model_dump()
    inconsistent["quality"] = Quality.GOOD
    with pytest.raises(ValidationError, match="simulation marker"):
        type(simulated).model_validate(inconsistent)

    values = _pose_event().model_dump()
    values["source"] = Source.CORE
    wrong_source = EventEnvelope[PoseSample].model_validate(values)
    with pytest.raises(ValueError, match="vision pose event"):
        pose_event_for_browser(wrong_source)


def test_pose_timestamp_must_fit_exactly_in_a_javascript_integer():
    values = _pose_event().payload.model_dump()
    values["captured_monotonic_ns"] = (MAX_JAVASCRIPT_SAFE_INTEGER + 1) * 1_000
    values["processed_monotonic_ns"] = values["captured_monotonic_ns"] + 1_000
    values["processing_latency_ns"] = 1_000
    pose = PoseSample.model_validate(values)
    event_values = _pose_event().model_dump()
    event_values.update(
        payload=pose,
        captured_monotonic_ns=pose.captured_monotonic_ns,
        created_monotonic_ns=pose.processed_monotonic_ns,
    )
    event = EventEnvelope[PoseSample].model_validate(event_values)

    with pytest.raises(ValidationError):
        pose_event_for_browser(event)


def test_clock_response_echoes_request_and_preserves_monotonic_order():
    request = BrowserClockRequest(
        request_id="sync-0001",
        client_sent_ms=12_345.5,
    )
    response = browser_clock_response(
        request,
        server_received_monotonic_ns=10_000_100_000,
        server_sent_monotonic_ns=10_000_200_000,
    )

    assert response.model_dump(mode="json") == {
        "schema_version": BROWSER_VIDEO_SCHEMA_VERSION,
        "message_type": "clock_sync_response",
        "request_id": "sync-0001",
        "client_sent_ms": 12_345.5,
        "server_received_monotonic_us": 10_000_100,
        "server_sent_monotonic_us": 10_000_200,
    }

    with pytest.raises(ValueError, match="cannot precede"):
        browser_clock_response(
            request,
            server_received_monotonic_ns=10_000_200_000,
            server_sent_monotonic_ns=10_000_100_000,
        )


def test_clock_request_is_bounded_and_forbids_unknown_fields():
    with pytest.raises(ValidationError):
        BrowserClockRequest(request_id="bad space", client_sent_ms=1.0)
    with pytest.raises(ValidationError):
        BrowserClockRequest(
            request_id="sync-1",
            client_sent_ms=1.0,
            token="must-not-be-accepted",
        )


def test_research_hub_projects_canonical_frames_and_bounds_polling():
    hub = ResearchPoseHub(capacity=2)
    assert hub.snapshot(after=0) == {"cursor": 0, "events": []}
    assert hub.ingest_frame(encode_event_frame(_pose_event())) is True
    first = hub.snapshot(after=0)
    assert first["cursor"] == 1
    assert first["events"][0]["message_type"] == "pose_sample"
    assert first["events"][0]["captured_monotonic_us"] == 9_007_199_254_740
    assert hub.snapshot(after=1) == {"cursor": 1, "events": []}
    hub.ingest_frame(encode_event_frame(_pose_event(quality=Quality.VISION_DEGRADED)))
    hub.ingest_frame(encode_event_frame(_pose_event(quality=Quality.SIMULATED)))
    assert [event["quality"] for event in hub.snapshot(after=0)["events"]] == [
        "vision_degraded", "simulated",
    ]
