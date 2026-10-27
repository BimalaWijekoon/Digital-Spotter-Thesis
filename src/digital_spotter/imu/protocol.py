"""Strict host-side implementation of the BLE GATT protocol v1."""

from __future__ import annotations

import math
import struct
from collections import deque
from dataclasses import dataclass
from enum import IntFlag
from typing import Literal

import msgpack
from pydantic import BaseModel, ConfigDict, Field


PROTOCOL_VERSION = 1
IMU_PACKET_SIZE = 20
MAX_GATT_PAYLOAD = 512
STANDARD_GRAVITY_M_S2 = 9.80665
SERVICE_UUID = "fba6b009-755a-53f9-9743-4d1850269448"
CONTROL_UUID = "5ba3693b-d04c-5d40-b401-c1cbd3b784e5"
IMU_STREAM_UUID = "3b5fb866-8fbd-5372-852e-8c8cae226147"
STATUS_UUID = "4f2ea3db-11c9-5c87-8b87-7804251cd817"
DEVICE_INFO_UUID = "3945c1a8-87c7-5ec7-9c9e-5c3906fa3cb7"
_PACKET = struct.Struct("<BBHIhhhhhh")


class IMUProtocolError(ValueError):
    """Raised when BLE data violates the frozen v1 wire contract."""


class IMUFlags(IntFlag):
    CALIBRATED = 1 << 0
    SATURATED = 1 << 1
    LOW_BATTERY = 1 << 2
    SENSOR_ERROR = 1 << 3


KNOWN_FLAGS = sum(flag.value for flag in IMUFlags)


@dataclass(frozen=True)
class ScaleProfile:
    version: int
    acceleration_lsb_per_g: float
    gyroscope_lsb_per_degree_s: float
    sample_rate_hz: int


SCALE_PROFILES = {
    1: ScaleProfile(
        version=1,
        acceleration_lsb_per_g=16_384.0,
        gyroscope_lsb_per_degree_s=131.0,
        sample_rate_hz=50,
    )
}


@dataclass(frozen=True)
class DecodedIMUSample:
    protocol_version: int
    flags: IMUFlags
    sequence: int
    sensor_time_us: int
    acceleration_raw: tuple[int, int, int]
    angular_velocity_raw: tuple[int, int, int]
    acceleration_m_s2: tuple[float, float, float]
    angular_velocity_rad_s: tuple[float, float, float]
    scale_profile_version: int


def _validate_flags(flags: int) -> IMUFlags:
    if flags < 0 or flags > 0xFF or flags & ~KNOWN_FLAGS:
        raise IMUProtocolError("IMU packet contains unknown flag bits")
    return IMUFlags(flags)


def decode_imu_packet(packet: bytes, *, scale_profile_version: int) -> DecodedIMUSample:
    if not isinstance(packet, bytes):
        raise IMUProtocolError("IMU packet must be bytes")
    if len(packet) != IMU_PACKET_SIZE:
        raise IMUProtocolError(f"IMU packet must be exactly {IMU_PACKET_SIZE} bytes")
    profile = SCALE_PROFILES.get(scale_profile_version)
    if profile is None:
        raise IMUProtocolError("unknown scale profile")
    version, raw_flags, sequence, sensor_time_us, *raw_axes = _PACKET.unpack(packet)
    if version != PROTOCOL_VERSION:
        raise IMUProtocolError("unsupported IMU protocol version")
    flags = _validate_flags(raw_flags)
    acceleration_raw = tuple(raw_axes[:3])
    angular_velocity_raw = tuple(raw_axes[3:])
    acceleration = tuple(
        value / profile.acceleration_lsb_per_g * STANDARD_GRAVITY_M_S2
        for value in acceleration_raw
    )
    angular_velocity = tuple(
        math.radians(value / profile.gyroscope_lsb_per_degree_s)
        for value in angular_velocity_raw
    )
    return DecodedIMUSample(
        protocol_version=version,
        flags=flags,
        sequence=sequence,
        sensor_time_us=sensor_time_us,
        acceleration_raw=acceleration_raw,
        angular_velocity_raw=angular_velocity_raw,
        acceleration_m_s2=acceleration,
        angular_velocity_rad_s=angular_velocity,
        scale_profile_version=scale_profile_version,
    )


def encode_imu_packet(
    *,
    flags: IMUFlags,
    sequence: int,
    sensor_time_us: int,
    acceleration_raw: tuple[int, int, int],
    angular_velocity_raw: tuple[int, int, int],
) -> bytes:
    _validate_flags(int(flags))
    if not 0 <= sequence <= 0xFFFF:
        raise IMUProtocolError("sequence is outside u16")
    if not 0 <= sensor_time_us <= 0xFFFFFFFF:
        raise IMUProtocolError("sensor_time_us is outside u32")
    if len(acceleration_raw) != 3 or len(angular_velocity_raw) != 3:
        raise IMUProtocolError("IMU vectors must contain exactly three axes")
    axes = (*acceleration_raw, *angular_velocity_raw)
    if any(value < -0x8000 or value > 0x7FFF for value in axes):
        raise IMUProtocolError("raw axis is outside i16")
    return _PACKET.pack(
        PROTOCOL_VERSION,
        int(flags),
        sequence,
        sensor_time_us,
        *axes,
    )


@dataclass(frozen=True)
class SequenceObservation:
    gap_count: int
    clock_reset: bool
    duplicate: bool


class IMUSequenceTracker:
    """Track u16 packet sequence across wrap and explicit device boots."""

    def __init__(self) -> None:
        self._boot_id: int | None = None
        self._sequence: int | None = None

    def observe(self, *, boot_id: int, sequence: int) -> SequenceObservation:
        if not 0 <= boot_id <= 0xFFFFFFFFFFFFFFFF:
            raise IMUProtocolError("boot_id is outside u64")
        if not 0 <= sequence <= 0xFFFF:
            raise IMUProtocolError("sequence is outside u16")
        if self._boot_id is None:
            self._boot_id = boot_id
            self._sequence = sequence
            return SequenceObservation(gap_count=0, clock_reset=False, duplicate=False)
        if boot_id != self._boot_id:
            self._boot_id = boot_id
            self._sequence = sequence
            return SequenceObservation(gap_count=0, clock_reset=True, duplicate=False)
        delta = (sequence - self._sequence) & 0xFFFF
        if delta == 0:
            return SequenceObservation(gap_count=0, clock_reset=False, duplicate=True)
        if delta > 0x8000:
            raise IMUProtocolError("IMU sequence moved backward")
        self._sequence = sequence
        return SequenceObservation(gap_count=delta - 1, clock_reset=False, duplicate=False)


class BoundedIMUBuffer:
    def __init__(self, max_samples: int):
        if not 1 <= max_samples <= 10_000:
            raise ValueError("max_samples must be between 1 and 10000")
        self._samples: deque[DecodedIMUSample] = deque(maxlen=max_samples)
        self.evicted_count = 0

    def append(self, sample: DecodedIMUSample) -> None:
        if len(self._samples) == self._samples.maxlen:
            self.evicted_count += 1
        self._samples.append(sample)

    def snapshot(self) -> tuple[DecodedIMUSample, ...]:
        return tuple(self._samples)

    def __len__(self) -> int:
        return len(self._samples)


class _GattModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, protected_namespaces=())


class WearableStatus(_GattModel):
    protocol_version: Literal[1]
    device_id: str = Field(min_length=3, max_length=64)
    boot_id: int = Field(ge=0, le=0xFFFFFFFFFFFFFFFF)
    state: Literal[
        "booting", "unprovisioned", "pairing", "idle", "calibrating", "streaming", "error", "updating"
    ]
    firmware_version: str = Field(min_length=1, max_length=32)
    hardware_revision: str = Field(min_length=1, max_length=32)
    imu_model: Literal["MPU6500"]
    scale_profile_version: int = Field(ge=1, le=0xFFFF)
    calibration_version: int = Field(ge=0, le=0xFFFFFFFF)
    battery_mv: int = Field(ge=0, le=0xFFFF)
    battery_percent: int | None = Field(default=None, ge=0, le=100)
    sample_rate_hz: int = Field(ge=1, le=1000)
    samples_sent: int = Field(ge=0, le=0xFFFFFFFFFFFFFFFF)
    sensor_errors: int = Field(ge=0, le=0xFFFFFFFF)
    sensor_retries: int = Field(ge=0, le=0xFFFFFFFF)
    actuator_commands: int = Field(default=0, ge=0, le=0xFFFFFFFF)
    actuator_rejections: int = Field(default=0, ge=0, le=0xFFFFFFFF)
    actuator_rate_limits: int = Field(default=0, ge=0, le=0xFFFFFFFF)
    actuator_driver_errors: int = Field(default=0, ge=0, le=0xFFFFFFFF)
    last_error_code: str | None = Field(default=None, max_length=64)
    heap_free_bytes: int = Field(ge=0, le=0xFFFFFFFF)
    heap_minimum_free_bytes: int = Field(ge=0, le=0xFFFFFFFF)
    uptime_ms: int = Field(ge=0, le=0xFFFFFFFF)


class DeviceInfo(_GattModel):
    protocol_version: Literal[1]
    device_id: str = Field(min_length=3, max_length=64)
    firmware_version: str = Field(min_length=1, max_length=32)
    hardware_revision: str = Field(min_length=1, max_length=32)
    imu_model: Literal["MPU6500"]
    service_uuid: Literal[SERVICE_UUID]
    scale_profile_version: int = Field(ge=1, le=0xFFFF)
    acceleration_lsb_per_g: int = Field(gt=0, le=0xFFFF)
    gyroscope_lsb_per_degree_s: int = Field(gt=0, le=0xFFFF)
    sample_rate_hz: int = Field(ge=1, le=1000)


def _unpack_map(encoded: bytes) -> dict:
    if not isinstance(encoded, bytes) or not encoded:
        raise IMUProtocolError("GATT value must be non-empty bytes")
    if len(encoded) > MAX_GATT_PAYLOAD:
        raise IMUProtocolError("GATT value exceeds 512 bytes")
    try:
        value = msgpack.unpackb(
            encoded,
            raw=False,
            strict_map_key=True,
            max_str_len=128,
            max_bin_len=64,
            max_array_len=32,
            max_map_len=32,
            max_ext_len=0,
        )
    except Exception as exc:
        raise IMUProtocolError(f"malformed GATT MessagePack: {exc}") from exc
    if not isinstance(value, dict):
        raise IMUProtocolError("GATT MessagePack root must be a map")
    return value


def parse_wearable_status(encoded: bytes) -> WearableStatus:
    try:
        return WearableStatus.model_validate(_unpack_map(encoded))
    except IMUProtocolError:
        raise
    except Exception as exc:
        raise IMUProtocolError(f"invalid wearable status: {exc}") from exc


def parse_device_info(encoded: bytes) -> DeviceInfo:
    try:
        info = DeviceInfo.model_validate(_unpack_map(encoded))
    except IMUProtocolError:
        raise
    except Exception as exc:
        raise IMUProtocolError(f"invalid device info: {exc}") from exc
    if info.scale_profile_version not in SCALE_PROFILES:
        raise IMUProtocolError("device advertises an unsupported scale profile")
    return info
