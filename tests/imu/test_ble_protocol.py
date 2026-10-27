from __future__ import annotations

import math

import msgpack
import pytest

from digital_spotter.imu import (
    BoundedIMUBuffer,
    IMUFlags,
    IMUProtocolError,
    IMUSequenceTracker,
    decode_imu_packet,
    encode_imu_packet,
    parse_device_info,
    parse_wearable_status,
)
from digital_spotter.imu.protocol import SERVICE_UUID


GOLDEN_PACKET = bytes.fromhex(
    "01 05 34 12 ef cd ab 89 00 80 ff ff ff 7f 2e fb 00 00 d2 04"
)


def test_python_codec_matches_portable_firmware_golden_bytes():
    encoded = encode_imu_packet(
        flags=IMUFlags.CALIBRATED | IMUFlags.LOW_BATTERY,
        sequence=0x1234,
        sensor_time_us=0x89ABCDEF,
        acceleration_raw=(-32768, -1, 32767),
        angular_velocity_raw=(-1234, 0, 1234),
    )
    decoded = decode_imu_packet(encoded, scale_profile_version=1)

    assert encoded == GOLDEN_PACKET
    assert decoded.sequence == 0x1234
    assert decoded.acceleration_raw == (-32768, -1, 32767)
    assert decoded.angular_velocity_raw == (-1234, 0, 1234)
    assert decoded.acceleration_m_s2[1] == pytest.approx(-9.80665 / 16384)
    assert decoded.angular_velocity_rad_s[2] == pytest.approx(math.radians(1234 / 131))


@pytest.mark.parametrize("packet", [b"", GOLDEN_PACKET[:-1], GOLDEN_PACKET + b"x"])
def test_wrong_packet_lengths_are_rejected(packet):
    with pytest.raises(IMUProtocolError, match="exactly 20"):
        decode_imu_packet(packet, scale_profile_version=1)


def test_unknown_version_flags_profile_and_ranges_are_rejected():
    wrong_version = bytes([2]) + GOLDEN_PACKET[1:]
    wrong_flags = GOLDEN_PACKET[:1] + bytes([0x80]) + GOLDEN_PACKET[2:]
    with pytest.raises(IMUProtocolError, match="version"):
        decode_imu_packet(wrong_version, scale_profile_version=1)
    with pytest.raises(IMUProtocolError, match="flag"):
        decode_imu_packet(wrong_flags, scale_profile_version=1)
    with pytest.raises(IMUProtocolError, match="scale profile"):
        decode_imu_packet(GOLDEN_PACKET, scale_profile_version=999)
    with pytest.raises(IMUProtocolError, match="outside i16"):
        encode_imu_packet(
            flags=IMUFlags.CALIBRATED,
            sequence=1,
            sensor_time_us=1,
            acceleration_raw=(40000, 0, 0),
            angular_velocity_raw=(0, 0, 0),
        )


def test_sequence_tracker_handles_gap_wrap_duplicate_reset_and_backward():
    tracker = IMUSequenceTracker()
    assert tracker.observe(boot_id=1, sequence=65534).gap_count == 0
    assert tracker.observe(boot_id=1, sequence=1).gap_count == 2
    assert tracker.observe(boot_id=1, sequence=1).duplicate is True
    assert tracker.observe(boot_id=2, sequence=0).clock_reset is True
    with pytest.raises(IMUProtocolError, match="backward"):
        tracker.observe(boot_id=2, sequence=65535)


def test_imu_buffer_is_bounded_and_counts_evictions():
    sample = decode_imu_packet(GOLDEN_PACKET, scale_profile_version=1)
    buffer = BoundedIMUBuffer(max_samples=2)
    buffer.append(sample)
    buffer.append(sample)
    buffer.append(sample)

    assert len(buffer) == 2
    assert buffer.evicted_count == 1
    assert len(buffer.snapshot()) == 2


def test_status_and_device_info_are_strict_bounded_messagepack():
    status = {
        "protocol_version": 1,
        "device_id": "imu-test-001",
        "boot_id": 7,
        "state": "idle",
        "firmware_version": "4.0.0-dev",
        "hardware_revision": "esp32-c3-mpu6500-r1",
        "imu_model": "MPU6500",
        "scale_profile_version": 1,
        "calibration_version": 0,
        "battery_mv": 3900,
        "battery_percent": None,
        "sample_rate_hz": 50,
        "samples_sent": 0,
        "sensor_errors": 0,
        "sensor_retries": 0,
        "actuator_commands": 1,
        "actuator_rejections": 2,
        "actuator_rate_limits": 1,
        "actuator_driver_errors": 0,
        "last_error_code": None,
        "heap_free_bytes": 200_000,
        "heap_minimum_free_bytes": 190_000,
        "uptime_ms": 10,
    }
    parsed = parse_wearable_status(msgpack.packb(status, use_bin_type=True))
    assert parsed.device_id == "imu-test-001"

    info = {
        "protocol_version": 1,
        "device_id": "imu-test-001",
        "firmware_version": "4.0.0-dev",
        "hardware_revision": "esp32-c3-mpu6500-r1",
        "imu_model": "MPU6500",
        "service_uuid": SERVICE_UUID,
        "scale_profile_version": 1,
        "acceleration_lsb_per_g": 16384,
        "gyroscope_lsb_per_degree_s": 131,
        "sample_rate_hz": 50,
    }
    assert parse_device_info(msgpack.packb(info, use_bin_type=True)).sample_rate_hz == 50

    status["secret"] = "must fail"
    with pytest.raises(IMUProtocolError, match="invalid wearable status"):
        parse_wearable_status(msgpack.packb(status, use_bin_type=True))
    with pytest.raises(IMUProtocolError, match="exceeds"):
        parse_wearable_status(b"x" * 513)
