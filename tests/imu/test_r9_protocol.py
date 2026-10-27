from __future__ import annotations

import asyncio

import pytest

from digital_spotter.imu.protocol import IMUFlags, IMUProtocolError, encode_imu_packet
from digital_spotter.imu.r9_protocol import (
    EXPECTED_DEVICE_INFO,
    REQUIRED_CHARACTERISTIC_UUIDS,
    SERVICE_UUID,
    decode_stream_packet,
    parse_device_info,
    parse_status,
)
from digital_spotter.imu.r9_transport import (
    R9BleakTransport,
    R9TransportError,
    validate_device_identity,
    validate_gatt_contract,
)


def _packet(*, sequence: int = 1, flags: IMUFlags = IMUFlags(0)) -> bytes:
    return encode_imu_packet(
        flags=flags,
        sequence=sequence,
        sensor_time_us=20_000,
        acceleration_raw=(100, -200, 16_384),
        angular_velocity_raw=(10, -20, 30),
    )


def test_r9_device_info_and_status_are_exact_and_bounded():
    info = parse_device_info(EXPECTED_DEVICE_INFO)
    status = parse_status(
        b"state=streaming;i2c_errors=0;samples_sent=123;uptime_ms=4567"
    )

    assert info.firmware_version == "0.9.0-r9"
    assert info.imu_model == "mpu6500"
    assert status.state == "streaming"
    assert status.samples_sent == 123

    with pytest.raises(IMUProtocolError, match="frozen contract"):
        parse_device_info(EXPECTED_DEVICE_INFO + b";extra=1")
    with pytest.raises(IMUProtocolError, match="frozen schema"):
        parse_status(b"state=ready;i2c_errors=0;samples_sent=0;uptime_ms=1")
    with pytest.raises(IMUProtocolError, match="96 bytes"):
        parse_status(b"x" * 97)
    with pytest.raises(IMUProtocolError, match="outside u32"):
        parse_status(
            b"state=streaming;i2c_errors=0;samples_sent=0;uptime_ms=4294967296"
        )


def test_r9_stream_requires_exact_20_byte_unflagged_packet():
    decoded = decode_stream_packet(_packet(sequence=0x1234))

    assert decoded.sequence == 0x1234
    assert decoded.acceleration_raw == (100, -200, 16_384)
    assert decoded.angular_velocity_raw == (10, -20, 30)

    with pytest.raises(IMUProtocolError, match="exactly 20"):
        decode_stream_packet(_packet()[:-1])
    with pytest.raises(IMUProtocolError, match="flags must be zero"):
        decode_stream_packet(_packet(flags=IMUFlags.SENSOR_ERROR))


def test_pcb_firmware_identity_reports_actual_version_and_stays_strict():
    pcb_info = EXPECTED_DEVICE_INFO.replace(b"0.9.0-r9", b"0.9.1-pcb1")
    demo_info = EXPECTED_DEVICE_INFO.replace(b"0.9.0-r9", b"0.9.2-demo-feedback")

    info = parse_device_info(pcb_info)

    assert info.firmware_version == "0.9.1-pcb1"
    assert parse_device_info(demo_info).firmware_version == "0.9.2-demo-feedback"
    assert info.protocol_version == 1
    assert info.sample_rate_hz == 50
    assert parse_device_info(EXPECTED_DEVICE_INFO).firmware_version == "0.9.0-r9"
    for incompatible in (
        pcb_info.replace(b"0.9.1-pcb1", b"0.9.2-unknown"),
        pcb_info.replace(b"rate_hz=50", b"rate_hz=100"),
    ):
        with pytest.raises(IMUProtocolError, match="frozen contract"):
            parse_device_info(incompatible)


def test_r9_identity_and_gatt_contract_reject_near_matches():
    validate_device_identity(
        name="ESP32-C3-Test",
        address="50:78:7D:92:61:1A",
        expected_name="ESP32-C3-Test",
        expected_address="50:78:7d:92:61:1a",
    )
    validate_gatt_contract(
        service_uuids=[SERVICE_UUID],
        characteristic_uuids=REQUIRED_CHARACTERISTIC_UUIDS,
    )

    with pytest.raises(R9TransportError, match="name"):
        validate_device_identity(
            name="ESP32-C3-Other",
            address="50:78:7D:92:61:1A",
            expected_name="ESP32-C3-Test",
            expected_address="50:78:7D:92:61:1A",
        )
    with pytest.raises(R9TransportError, match="address"):
        validate_device_identity(
            name="ESP32-C3-Test",
            address="50:78:7D:92:61:1B",
            expected_name="ESP32-C3-Test",
            expected_address="50:78:7D:92:61:1A",
        )
    with pytest.raises(R9TransportError, match="characteristic"):
        validate_gatt_contract(
            service_uuids=[SERVICE_UUID],
            characteristic_uuids=set(REQUIRED_CHARACTERISTIC_UUIDS) - {
                next(iter(REQUIRED_CHARACTERISTIC_UUIDS))
            },
        )


def test_preconnection_bleak_retry_does_not_poison_disconnect_event():
    async def scenario() -> None:
        transport = R9BleakTransport()
        candidate = object()
        established = object()
        transport._client = established  # type: ignore[assignment]

        transport._record_disconnection(  # type: ignore[arg-type]
            candidate,
            asyncio.get_running_loop(),
        )
        await asyncio.sleep(0)
        assert transport._disconnected.is_set() is False

        transport._record_disconnection(  # type: ignore[arg-type]
            established,
            asyncio.get_running_loop(),
        )
        await asyncio.sleep(0)
        assert transport._disconnected.is_set() is True

    asyncio.run(scenario())
