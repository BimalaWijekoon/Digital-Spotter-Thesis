"""Strict R9 wire contract, including the assembled-PCB firmware revision."""

from __future__ import annotations

import re
from dataclasses import dataclass

from digital_spotter.imu.protocol import (
    IMUFlags,
    IMUProtocolError,
    DecodedIMUSample,
    decode_imu_packet,
)


DEVICE_NAME = "ESP32-C3-Test"
DEVICE_ADDRESS = "50:78:7D:92:61:1A"
RESEARCH_DEVICE_ID = "dsimu-r9-50787d92611a"

SERVICE_UUID = "4fafc201-1fb5-459e-8fcc-c5c9c331914b"
DEVICE_INFO_UUID = "e193acb8-25ef-422c-b3e5-972eae75b8ea"
CONTROL_UUID = "7f725422-d560-4852-96d8-3407f417b1d8"
IMU_STREAM_UUID = "772af3c3-f1f9-43b0-8230-4dff401446ea"
STATUS_UUID = "7f07eb06-7be4-49a1-b952-1ed033b0dfc7"

REQUIRED_CHARACTERISTIC_UUIDS = frozenset(
    {DEVICE_INFO_UUID, CONTROL_UUID, IMU_STREAM_UUID, STATUS_UUID}
)
EXPECTED_DEVICE_INFO = (
    b"protocol=1;firmware=0.9.0-r9;hardware=esp32-c3;"
    b"imu=mpu6500;rate_hz=50"
)
PCB_DEVICE_INFO = (
    b"protocol=1;firmware=0.9.1-pcb1;hardware=esp32-c3;"
    b"imu=mpu6500;rate_hz=50"
)
_SUPPORTED_DEVICE_INFO = {
    EXPECTED_DEVICE_INFO: "0.9.0-r9",
    PCB_DEVICE_INFO: "0.9.1-pcb1",
}
STATUS_MAX_VALUE_BYTES = 96
_STATUS_PATTERN = re.compile(
    rb"^state=(idle|streaming|error);i2c_errors=(\d+);"
    rb"samples_sent=(\d+);uptime_ms=(\d+)$"
)


@dataclass(frozen=True)
class R9DeviceInfo:
    protocol_version: int = 1
    firmware_version: str = "0.9.0-r9"
    hardware: str = "esp32-c3"
    imu_model: str = "mpu6500"
    sample_rate_hz: int = 50


@dataclass(frozen=True)
class R9Status:
    state: str
    i2c_errors: int
    samples_sent: int
    uptime_ms: int


def parse_device_info(payload: bytes) -> R9DeviceInfo:
    """Accept only the explicit firmware identities sharing the frozen contract."""

    if not isinstance(payload, bytes):
        raise IMUProtocolError("R9 device info must be bytes")
    version = _SUPPORTED_DEVICE_INFO.get(payload)
    if version is None:
        raise IMUProtocolError("R9 device info does not match the frozen contract")
    return R9DeviceInfo(firmware_version=version)


def parse_status(payload: bytes) -> R9Status:
    """Parse the bounded ASCII status emitted by R9."""

    if not isinstance(payload, bytes):
        raise IMUProtocolError("R9 status must be bytes")
    if len(payload) > STATUS_MAX_VALUE_BYTES:
        raise IMUProtocolError("R9 status exceeds 96 bytes")
    match = _STATUS_PATTERN.fullmatch(payload)
    if match is None:
        raise IMUProtocolError("R9 status does not match the frozen schema")
    counters = tuple(int(match.group(index)) for index in (2, 3, 4))
    if any(value > 0xFFFFFFFF for value in counters):
        raise IMUProtocolError("R9 status counter is outside u32")
    return R9Status(
        state=match.group(1).decode("ascii"),
        i2c_errors=counters[0],
        samples_sent=counters[1],
        uptime_ms=counters[2],
    )


def decode_stream_packet(payload: bytes) -> DecodedIMUSample:
    """Decode one exact R9 packet without inventing calibration or status flags."""

    decoded = decode_imu_packet(payload, scale_profile_version=1)
    if decoded.flags != IMUFlags(0):
        raise IMUProtocolError("R9 stream flags must be zero")
    return decoded
