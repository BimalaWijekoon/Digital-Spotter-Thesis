"""Version 1 internal event payloads and common envelope."""

from __future__ import annotations

import secrets
import time
from enum import Enum
from typing import Annotated, Any, Generic, TypeVar
from uuid import UUID

import msgpack
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from digital_spotter.contracts.time import MonotonicNanoseconds, UtcMilliseconds


SCHEMA_VERSION_V1 = 0x0100
MAX_EVENT_BYTES = 64 * 1024

U16 = Annotated[int, Field(ge=0, le=0xFFFF)]
U32 = Annotated[int, Field(ge=0, le=0xFFFFFFFF)]
U64 = Annotated[int, Field(ge=0, le=0xFFFFFFFFFFFFFFFF)]
MonotonicNs = Annotated[MonotonicNanoseconds, Field(ge=0)]
UtcMs = Annotated[UtcMilliseconds, Field(ge=0)]
Vector3 = tuple[float, float, float]


class ContractDecodeError(ValueError):
    """Raised when a serialized event is malformed, oversized, or incompatible."""


class Source(str, Enum):
    IMU = "imu"
    VISION = "vision"
    CORE = "core"
    API = "api"
    SYNC = "sync"


class EventType(str, Enum):
    IMU_SAMPLE = "imu_sample"
    POSE_SAMPLE = "pose_sample"
    FUSED_SAMPLE = "fused_sample"
    REP_EVENT = "rep_event"
    ANALYSIS_EVENT = "analysis_event"
    HEALTH_STATE = "health_state"


class Quality(str, Enum):
    GOOD = "good"
    VISION_DEGRADED = "vision_degraded"
    IMU_DEGRADED = "imu_degraded"
    UNSYNCHRONIZED = "unsynchronized"
    UNAVAILABLE = "unavailable"
    SIMULATED = "simulated"


class ReasonCode(str, Enum):
    OK = "ok"
    STARTING = "starting"
    SIMULATED = "simulated"
    CAMERA_UNAVAILABLE = "camera_unavailable"
    POSE_NOT_FOUND = "pose_not_found"
    POSE_LOW_VISIBILITY = "pose_low_visibility"
    POSE_STALE = "pose_stale"
    IMU_UNAVAILABLE = "imu_unavailable"
    IMU_STALE = "imu_stale"
    IMU_GAP_RATE_HIGH = "imu_gap_rate_high"
    IMU_SATURATED = "imu_saturated"
    CALIBRATION_REQUIRED = "calibration_required"
    CLOCK_ACQUIRING = "clock_acquiring"
    CLOCK_UNSYNCHRONIZED = "clock_unsynchronized"
    MODEL_UNAVAILABLE = "model_unavailable"
    MODEL_CONTRACT_MISMATCH = "model_contract_mismatch"
    STORAGE_UNAVAILABLE = "storage_unavailable"
    STORAGE_PRESSURE = "storage_pressure"
    CLOUD_OFFLINE = "cloud_offline"
    UNAUTHORIZED = "unauthorized"
    PROTOCOL_MISMATCH = "protocol_mismatch"
    INTERNAL_ERROR = "internal_error"


class ClockState(str, Enum):
    ACQUIRING = "acquiring"
    SYNCHRONIZED = "synchronized"
    DEGRADED = "degraded"
    RESET = "reset"


class RepTransition(str, Enum):
    STARTED = "started"
    PHASE = "phase"
    COMPLETED = "completed"
    ABORTED = "aborted"


class RepPhase(str, Enum):
    ECCENTRIC = "eccentric"
    BOTTOM = "bottom"
    CONCENTRIC = "concentric"
    LOCKOUT = "lockout"


class ComponentState(str, Enum):
    STARTING = "starting"
    READY = "ready"
    DEGRADED = "degraded"
    STOPPING = "stopping"


class ContractModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        allow_inf_nan=False,
        protected_namespaces=(),
    )


class IMUSample(ContractModel):
    device_id: str = Field(min_length=3, max_length=64, pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]+$")
    boot_id: U64
    sequence: U16
    sensor_time_us: U32
    captured_monotonic_ns: MonotonicNs
    arrival_monotonic_ns: MonotonicNs
    acceleration_m_s2: Vector3
    angular_velocity_rad_s: Vector3
    calibration_version: U32
    quality: Quality
    gap_count_since_previous: U16 = 0
    estimated_clock_error_ns: U64
    clock_state: ClockState

    @model_validator(mode="after")
    def arrival_cannot_precede_capture(self) -> "IMUSample":
        if self.arrival_monotonic_ns < self.captured_monotonic_ns:
            raise ValueError("arrival_monotonic_ns cannot precede captured_monotonic_ns")
        return self


class PoseLandmark(ContractModel):
    x: float
    y: float
    z: float
    visibility: float = Field(ge=0.0, le=1.0)


class PoseSample(ContractModel):
    camera_id: str = Field(min_length=1, max_length=64)
    frame_sequence: U64
    captured_monotonic_ns: MonotonicNs
    processed_monotonic_ns: MonotonicNs
    image_width: int = Field(gt=0, le=8192)
    image_height: int = Field(gt=0, le=8192)
    landmark_schema_version: U16
    landmarks: tuple[PoseLandmark, ...] = Field(max_length=64)
    angles: dict[str, float] = Field(default_factory=dict, max_length=64)
    pose_confidence: float = Field(ge=0.0, le=1.0)
    quality: Quality
    processing_latency_ns: U64
    frames_dropped_since_previous: U32 = 0

    @field_validator("angles")
    @classmethod
    def bound_angle_names(cls, value: dict[str, float]) -> dict[str, float]:
        if any(not key or len(key) > 64 for key in value):
            raise ValueError("angle names must contain 1-64 characters")
        return value

    @model_validator(mode="after")
    def processing_cannot_precede_capture(self) -> "PoseSample":
        if self.processed_monotonic_ns < self.captured_monotonic_ns:
            raise ValueError("processed_monotonic_ns cannot precede captured_monotonic_ns")
        return self


class InterpolatedIMU(ContractModel):
    acceleration_m_s2: Vector3
    angular_velocity_rad_s: Vector3


class FusedSample(ContractModel):
    pose_event_id: UUID
    captured_monotonic_ns: MonotonicNs
    interpolated_imu: InterpolatedIMU
    imu_before_sequence: U16
    imu_after_sequence: U16
    alignment_error_ns: U64
    calibration_version: U32
    quality: Quality
    quality_reasons: tuple[ReasonCode, ...] = Field(default_factory=tuple, max_length=16)


class RepEvent(ContractModel):
    rep_id: UUID
    rep_number: int = Field(ge=1, le=10000)
    exercise_contract_version: str = Field(min_length=1, max_length=64)
    event: RepTransition
    phase: RepPhase | None = None
    captured_monotonic_ns: MonotonicNs
    quality: Quality
    phase_snapshot_refs: tuple[UUID, ...] = Field(default_factory=tuple, max_length=8)

    @model_validator(mode="after")
    def phase_transition_requires_phase(self) -> "RepEvent":
        if self.event is RepTransition.PHASE and self.phase is None:
            raise ValueError("phase transition requires phase")
        return self


class AnalysisEvent(ContractModel):
    analysis_id: UUID
    rep_id: UUID
    model_package_id: str = Field(min_length=1, max_length=128)
    model_version: str = Field(min_length=1, max_length=64)
    feature_contract_version: str = Field(min_length=1, max_length=64)
    input_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    label: str = Field(min_length=1, max_length=128)
    bad_form_probability: float = Field(ge=0.0, le=1.0)
    threshold: float = Field(ge=0.0, le=1.0)
    latency_ns: U64
    quality: Quality
    quality_reasons: tuple[ReasonCode, ...] = Field(default_factory=tuple, max_length=16)


class HealthState(ContractModel):
    component: str = Field(min_length=1, max_length=64)
    state: ComponentState
    reason_codes: tuple[ReasonCode, ...] = Field(default_factory=tuple, max_length=32)
    since_monotonic_ns: MonotonicNs
    versions: dict[str, str] = Field(default_factory=dict, max_length=32)
    last_success_monotonic_ns: MonotonicNs | None = None
    counters: dict[str, int] = Field(default_factory=dict, max_length=64)
    is_simulated: bool

    @field_validator("versions")
    @classmethod
    def bound_versions(cls, value: dict[str, str]) -> dict[str, str]:
        if any(not key or len(key) > 64 or len(version) > 128 for key, version in value.items()):
            raise ValueError("version names/values exceed contract limits")
        return value

    @field_validator("counters")
    @classmethod
    def bound_counters(cls, value: dict[str, int]) -> dict[str, int]:
        if any(not key or len(key) > 64 or count < 0 for key, count in value.items()):
            raise ValueError("counter names/counts exceed contract limits")
        return value


PayloadT = TypeVar("PayloadT", bound=ContractModel)


class EventEnvelope(ContractModel, Generic[PayloadT]):
    schema_version: U16 = SCHEMA_VERSION_V1
    event_type: EventType
    event_id: UUID
    source: Source
    device_id: str | None = Field(default=None, max_length=64)
    session_id: UUID | None = None
    captured_monotonic_ns: MonotonicNs | None = None
    created_monotonic_ns: MonotonicNs
    created_utc_ms: UtcMs | None = None
    quality: Quality
    trace_id: UUID | None = None
    payload: PayloadT

    @field_validator("schema_version")
    @classmethod
    def require_supported_schema(cls, value: int) -> int:
        if value != SCHEMA_VERSION_V1:
            raise ValueError("unsupported event schema version")
        return value

    @field_validator("event_id")
    @classmethod
    def require_uuid7(cls, value: UUID) -> UUID:
        if value.version != 7:
            raise ValueError("event_id must be UUIDv7")
        return value

    @model_validator(mode="after")
    def event_type_matches_payload(self) -> "EventEnvelope[PayloadT]":
        expected = EVENT_TYPE_BY_PAYLOAD.get(type(self.payload))
        if expected is None or self.event_type is not expected:
            raise ValueError("event_type does not match payload contract")
        if self.captured_monotonic_ns is not None:
            if self.created_monotonic_ns < self.captured_monotonic_ns:
                raise ValueError("created_monotonic_ns cannot precede capture time")
            payload_capture = getattr(self.payload, "captured_monotonic_ns", None)
            if payload_capture is not None and payload_capture != self.captured_monotonic_ns:
                raise ValueError("envelope and payload capture timestamps differ")
        payload_quality = getattr(self.payload, "quality", None)
        if payload_quality is not None and payload_quality is not self.quality:
            raise ValueError("envelope and payload quality differ")
        return self

    def to_messagepack(self) -> bytes:
        encoded = msgpack.packb(self.model_dump(mode="json"), use_bin_type=True)
        if len(encoded) > MAX_EVENT_BYTES:
            raise ContractDecodeError(f"serialized event exceeds {MAX_EVENT_BYTES} bytes")
        return encoded

    @classmethod
    def from_messagepack(cls, encoded: bytes) -> "EventEnvelope[PayloadT]":
        if not isinstance(encoded, bytes) or not encoded:
            raise ContractDecodeError("event must be non-empty bytes")
        if len(encoded) > MAX_EVENT_BYTES:
            raise ContractDecodeError(f"serialized event exceeds {MAX_EVENT_BYTES} bytes")
        try:
            unpacked = msgpack.unpackb(
                encoded,
                raw=False,
                strict_map_key=True,
                max_str_len=8192,
                max_bin_len=MAX_EVENT_BYTES,
                max_array_len=256,
                max_map_len=128,
                max_ext_len=0,
            )
            if not isinstance(unpacked, dict):
                raise ContractDecodeError("event root must be a map")
            return cls.model_validate(unpacked)
        except ContractDecodeError:
            raise
        except Exception as exc:
            raise ContractDecodeError(f"invalid event: {exc}") from exc


EVENT_TYPE_BY_PAYLOAD: dict[type[ContractModel], EventType] = {
    IMUSample: EventType.IMU_SAMPLE,
    PoseSample: EventType.POSE_SAMPLE,
    FusedSample: EventType.FUSED_SAMPLE,
    RepEvent: EventType.REP_EVENT,
    AnalysisEvent: EventType.ANALYSIS_EVENT,
    HealthState: EventType.HEALTH_STATE,
}


def new_event_id(*, unix_time_ms: int | None = None, random_bits: int | None = None) -> UUID:
    """Create an RFC 9562 UUIDv7 with injectable time/randomness for tests."""
    timestamp = int(time.time_ns() // 1_000_000) if unix_time_ms is None else unix_time_ms
    if not 0 <= timestamp < (1 << 48):
        raise ValueError("UUIDv7 timestamp must fit 48 bits")
    randomness = secrets.randbits(74) if random_bits is None else random_bits
    if not 0 <= randomness < (1 << 74):
        raise ValueError("UUIDv7 randomness must fit 74 bits")
    rand_a = randomness >> 62
    rand_b = randomness & ((1 << 62) - 1)
    value = (
        (timestamp << 80)
        | (0x7 << 76)
        | (rand_a << 64)
        | (0b10 << 62)
        | rand_b
    )
    return UUID(int=value)
