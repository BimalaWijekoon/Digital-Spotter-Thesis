from __future__ import annotations

import asyncio

import pytest

from digital_spotter.imu import FakeWearable, SensorClockMapper
from digital_spotter.imu.control import (
    AuthenticatedResponse,
    ControlProtocolError,
    decode_command,
    derive_session_key,
    encode_response,
)
from digital_spotter.imu.control_client import WearableControlClient
from digital_spotter.imu.protocol import CONTROL_UUID, parse_wearable_status


DEVICE_KEY = bytes(range(32))


class EmulatedFirmwareControl:
    def __init__(self, *, device_id: str, boot_id: int, response_key: bytes | None = None):
        self.device_id = device_id
        self.boot_id = boot_id
        self.response_key = response_key
        self.callback = None
        self.session_key = None
        self.session_nonce = None
        self.sensor_time_us = 25_000_000
        self.commands = []
        self.stopped = False

    async def start_notify(self, uuid, callback):
        assert uuid == CONTROL_UUID
        self.callback = callback

    async def stop_notify(self, uuid):
        assert uuid == CONTROL_UUID
        self.stopped = True

    async def write(self, uuid, data, *, response):
        assert uuid == CONTROL_UUID
        assert response is True
        assert self.callback is not None
        if self.session_key is None:
            command = decode_command(data, key=DEVICE_KEY)
            assert command.command == "authenticate"
            assert command.arguments == {"boot_id": self.boot_id}
            self.session_nonce = command.session_nonce
            reply = AuthenticatedResponse(
                command_id=command.command_id,
                result="accepted",
                session_nonce=command.session_nonce,
                arguments={"boot_id": self.boot_id, "sensor_time_us": self.sensor_time_us},
            )
            key = self.response_key or DEVICE_KEY
            self.callback(encode_response(reply, key=key))
            self.session_key = derive_session_key(
                device_key=DEVICE_KEY,
                session_nonce=command.session_nonce,
                device_id=self.device_id,
                boot_id=self.boot_id,
            )
            return

        command = decode_command(data, key=self.session_key)
        self.commands.append(command.command)
        arguments = {}
        if command.command == "time_sync":
            request_nonce = command.arguments["request_nonce"]
            receive = self.sensor_time_us + 100
            send = receive
            self.sensor_time_us = send
            arguments = {
                "boot_id": self.boot_id,
                "request_nonce": request_nonce,
                "sensor_receive_us": receive,
                "sensor_send_us": send,
            }
        self.callback(
            encode_response(
                AuthenticatedResponse(
                    command_id=command.command_id,
                    result="accepted",
                    session_nonce=command.session_nonce,
                    arguments=arguments,
                ),
                key=self.session_key,
            )
        )


def test_control_client_authenticates_syncs_and_controls_streaming():
    async def scenario():
        wearable = FakeWearable(boot_id=9)
        status = parse_wearable_status(wearable.status(state="idle"))
        transport = EmulatedFirmwareControl(device_id=wearable.device_id, boot_id=9)
        mapper = SensorClockMapper()
        client = WearableControlClient(
            transport=transport,
            device_key=DEVICE_KEY,
            device_id=wearable.device_id,
            clock_mapper=mapper,
        )

        await client.open(status)
        assert await client.time_sync() is True
        await client.set_streaming(True)
        await client.identify()
        assert await client.send_feedback(
            "bad",
            source_is_real=True,
            quality_gate_passed=True,
            clock_synchronized=True,
        ) is True
        await client.set_streaming(False)
        await client.close()

        assert transport.commands == ["time_sync", "start", "identify", "feedback", "stop"]
        assert transport.stopped is True

    asyncio.run(scenario())


def test_control_client_blocks_mock_stale_or_low_quality_feedback_locally():
    async def scenario():
        wearable = FakeWearable(boot_id=15)
        status = parse_wearable_status(wearable.status(state="idle"))
        transport = EmulatedFirmwareControl(device_id=wearable.device_id, boot_id=15)
        client = WearableControlClient(
            transport=transport,
            device_key=DEVICE_KEY,
            device_id=wearable.device_id,
            clock_mapper=SensorClockMapper(),
        )
        await client.open(status)
        for flags in (
            {"source_is_real": False, "quality_gate_passed": True, "clock_synchronized": True},
            {"source_is_real": True, "quality_gate_passed": False, "clock_synchronized": True},
            {"source_is_real": True, "quality_gate_passed": True, "clock_synchronized": False},
        ):
            with pytest.raises(ControlProtocolError, match="quality gate"):
                await client.send_feedback("bad", **flags)
        await client.close()
        assert transport.commands == []

    asyncio.run(scenario())


def test_control_client_rejects_forged_authentication_response():
    async def scenario():
        wearable = FakeWearable(boot_id=11)
        status = parse_wearable_status(wearable.status(state="idle"))
        transport = EmulatedFirmwareControl(
            device_id=wearable.device_id,
            boot_id=11,
            response_key=bytes(reversed(range(32))),
        )
        client = WearableControlClient(
            transport=transport,
            device_key=DEVICE_KEY,
            device_id=wearable.device_id,
            clock_mapper=SensorClockMapper(),
        )

        with pytest.raises(ControlProtocolError, match="authentication"):
            await client.open(status)
        assert transport.stopped is True

    asyncio.run(scenario())


def test_control_client_refuses_unprovisioned_status_before_writing():
    async def scenario():
        wearable = FakeWearable(boot_id=12)
        status = parse_wearable_status(wearable.status(state="unprovisioned"))
        transport = EmulatedFirmwareControl(device_id=wearable.device_id, boot_id=12)
        client = WearableControlClient(
            transport=transport,
            device_key=DEVICE_KEY,
            device_id=wearable.device_id,
            clock_mapper=SensorClockMapper(),
        )

        with pytest.raises(ControlProtocolError, match="unprovisioned"):
            await client.open(status)
        assert transport.callback is None

    asyncio.run(scenario())
