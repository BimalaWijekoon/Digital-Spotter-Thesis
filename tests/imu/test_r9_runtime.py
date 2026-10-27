from __future__ import annotations

import asyncio
import time
from pathlib import Path

from digital_spotter.imu.clock import SensorClockMapper
from digital_spotter.imu.protocol import IMUFlags, encode_imu_packet
from digital_spotter.imu.r9_agent import R9AgentCore
from digital_spotter.imu.r9_protocol import (
    CONTROL_UUID,
    DEVICE_INFO_UUID,
    EXPECTED_DEVICE_INFO,
    IMU_STREAM_UUID,
    STATUS_UUID,
)
from digital_spotter.imu.r9_runtime import R9IMUAgentRuntime
from digital_spotter.feedback import DemoCue


def _packet(sequence: int = 1, *, sensor_time_us: int | None = None) -> bytes:
    return encode_imu_packet(
        flags=IMUFlags(0),
        sequence=sequence,
        sensor_time_us=(
            sequence * 20_000 if sensor_time_us is None else sensor_time_us
        ),
        acceleration_raw=(0, 16_384, 0),
        angular_velocity_raw=(0, 0, 0),
    )


class FakeR9Transport:
    def __init__(self) -> None:
        self.is_connected = False
        self.connect_count = 0
        self.callbacks = {}
        self.disconnected = asyncio.Event()
        self.control_response = b"ok:idle"
        self.state = "idle"
        self.samples_sent = 0
        self.started_monotonic = time.monotonic()
        self.uptime_ms = 1000
        self.last_reported_uptime_ms = self.uptime_ms
        self.stream_sequence = 0
        self.requests: list[bytes] = []
        self.notification_stopped = False

    def sensor_time_us(self) -> int:
        elapsed_us = round((time.monotonic() - self.started_monotonic) * 1_000_000)
        return 1_000_000 + elapsed_us

    async def connect(self) -> None:
        self.connect_count += 1
        self.is_connected = True
        self.disconnected.clear()

    async def disconnect(self) -> None:
        self.is_connected = False
        self.disconnected.set()

    async def read(self, uuid: str) -> bytes:
        if uuid == DEVICE_INFO_UUID:
            return EXPECTED_DEVICE_INFO
        if uuid == STATUS_UUID:
            self.uptime_ms = self.sensor_time_us() // 1000
            self.last_reported_uptime_ms = self.uptime_ms
            payload = (
                f"state={self.state};i2c_errors=0;samples_sent={self.samples_sent};"
                f"uptime_ms={self.uptime_ms}"
            ).encode("ascii")
            if self.state == "streaming":
                self.samples_sent += 1
                sequence = self.stream_sequence
                self.stream_sequence += 1
                asyncio.get_running_loop().call_soon(
                    self.callbacks[IMU_STREAM_UUID],
                    _packet(
                        sequence,
                        sensor_time_us=self.last_reported_uptime_ms * 1000,
                    ),
                )
            return payload
        if uuid == CONTROL_UUID:
            return self.control_response
        raise AssertionError(uuid)

    async def write(self, uuid: str, data: bytes, *, response: bool) -> None:
        assert uuid == CONTROL_UUID and response is True
        self.requests.append(data)
        if data == b"stream:start":
            self.state = "streaming"
            self.control_response = b"ok:streaming"
            self.stream_sequence = 2
            self.samples_sent += 2
            loop = asyncio.get_running_loop()
            sensor_time_us = self.sensor_time_us()
            loop.call_soon(
                self.callbacks[IMU_STREAM_UUID],
                _packet(0, sensor_time_us=sensor_time_us),
            )
            loop.call_later(
                0.02,
                self.callbacks[IMU_STREAM_UUID],
                _packet(1, sensor_time_us=sensor_time_us + 20_000),
            )
        elif data == b"stream:stop":
            self.state = "idle"
            self.control_response = b"ok:idle"
        elif data in (b"demo:start", b"demo:good", b"demo:bad", b"demo:stop"):
            self.control_response = b"ok:" + data.replace(b":", b"_")
        else:
            raise AssertionError(data)

    async def start_notify(self, uuid: str, callback) -> None:
        self.callbacks[uuid] = callback

    async def stop_notify(self, uuid: str) -> None:
        assert uuid == IMU_STREAM_UUID
        self.notification_stopped = True

    async def wait_disconnected(self) -> None:
        await self.disconnected.wait()

    def force_disconnect(self) -> None:
        self.is_connected = False
        self.state = "idle"
        self.control_response = b"ok:idle"
        self.disconnected.set()


class FailFirstConnectTransport(FakeR9Transport):
    async def connect(self) -> None:
        self.connect_count += 1
        if self.connect_count == 1:
            raise RuntimeError("synthetic initial connection failure")
        self.is_connected = True
        self.disconnected.clear()


class RecordingPublisher:
    def __init__(self) -> None:
        self.events = []
        self.received = asyncio.Event()
        self.closed = False

    async def send(self, event) -> None:
        self.events.append(event)
        self.received.set()

    async def close(self) -> None:
        self.closed = True


def test_r9_runtime_connects_streams_and_stops_cleanly():
    async def scenario() -> None:
        transport = FakeR9Transport()
        publisher = RecordingPublisher()
        runtime = R9IMUAgentRuntime(
            core=R9AgentCore(
                device_id="dsimu-r9-test",
                initial_boot_id=1,
                clock_mapper=SensorClockMapper(min_exchanges=3),
            ),
            transport=transport,
            publisher=publisher,
            status_interval_s=0.2,
            reconnect_backoff_s=(0.01,),
        )
        task = asyncio.create_task(runtime.run())
        await asyncio.wait_for(publisher.received.wait(), timeout=1.0)
        runtime.stop()
        await asyncio.wait_for(task, timeout=1.0)

        assert transport.connect_count == 1
        assert transport.requests == [b"stream:start", b"stream:stop"]
        assert transport.notification_stopped is True
        assert len(publisher.events) == 1
        assert publisher.closed is True
        assert runtime.core.counters().packets_rejected == 0
        assert runtime.core.counters().notification_drops == 0
        assert runtime.core.counters().clock_exchanges_accepted == 3
        assert runtime.core.counters().clock_gate_drops > 0
        assert publisher.events[0].payload.clock_state.value == "synchronized"

    asyncio.run(scenario())


def test_r9_runtime_queue_keeps_only_latest_pending_packet():
    core = R9AgentCore(device_id="dsimu-r9-test", initial_boot_id=1)
    runtime = R9IMUAgentRuntime(
        core=core,
        transport=FakeR9Transport(),
        publisher=RecordingPublisher(),
        queue_size=1,
    )

    runtime._enqueue(_packet(1))
    runtime._enqueue(_packet(2))
    runtime._enqueue(_packet(3))

    assert runtime.queue.qsize() == 1
    assert core.counters().notification_drops == 2
    payload, _arrival = runtime.queue.get_nowait()
    assert payload == _packet(3)


def test_r9_runtime_serializes_demo_cue_through_the_existing_ble_owner():
    async def scenario() -> None:
        transport = FakeR9Transport()
        publisher = RecordingPublisher()
        runtime = R9IMUAgentRuntime(
            core=R9AgentCore(
                device_id="dsimu-r9-test",
                initial_boot_id=1,
                clock_mapper=SensorClockMapper(min_exchanges=3),
            ),
            transport=transport,
            publisher=publisher,
            status_interval_s=0.2,
            reconnect_backoff_s=(0.01,),
        )
        task = asyncio.create_task(runtime.run())
        await asyncio.wait_for(publisher.received.wait(), timeout=1.0)

        response = await runtime.send_demo_cue(DemoCue.BAD)

        assert response == b"ok:demo_bad"
        assert transport.requests[-1] == b"demo:bad"
        runtime.stop()
        await asyncio.wait_for(task, timeout=1.0)

    asyncio.run(scenario())


def test_r9_runtime_reconnects_after_established_link_disconnect():
    async def scenario() -> None:
        transport = FakeR9Transport()
        publisher = RecordingPublisher()
        runtime = R9IMUAgentRuntime(
            core=R9AgentCore(
                device_id="dsimu-r9-test",
                initial_boot_id=1,
                clock_mapper=SensorClockMapper(min_exchanges=3),
            ),
            transport=transport,
            publisher=publisher,
            status_interval_s=0.2,
            reconnect_backoff_s=(0.01,),
        )
        task = asyncio.create_task(runtime.run())
        await asyncio.wait_for(publisher.received.wait(), timeout=1.0)
        publisher.received.clear()

        transport.force_disconnect()
        await asyncio.wait_for(publisher.received.wait(), timeout=1.0)

        runtime.stop()
        await asyncio.wait_for(task, timeout=1.0)

        assert transport.connect_count == 2
        assert transport.requests == [b"stream:start", b"stream:start", b"stream:stop"]
        assert len(publisher.events) == 2
        assert runtime.core.counters().reconnects == 1
        assert runtime.core.counters().connection_failures == 0

    asyncio.run(scenario())


def test_r9_runtime_counts_initial_failure_separately_from_reconnect():
    async def scenario() -> None:
        transport = FailFirstConnectTransport()
        publisher = RecordingPublisher()
        runtime = R9IMUAgentRuntime(
            core=R9AgentCore(
                device_id="dsimu-r9-test",
                initial_boot_id=1,
                clock_mapper=SensorClockMapper(min_exchanges=3),
            ),
            transport=transport,
            publisher=publisher,
            status_interval_s=0.2,
            reconnect_backoff_s=(0.01,),
        )
        task = asyncio.create_task(runtime.run())
        await asyncio.wait_for(publisher.received.wait(), timeout=1.0)

        runtime.stop()
        await asyncio.wait_for(task, timeout=1.0)

        assert transport.connect_count == 2
        assert len(publisher.events) == 1
        assert runtime.core.counters().connection_failures == 1
        assert runtime.core.counters().reconnects == 0

    asyncio.run(scenario())


def test_systemd_unit_activates_only_r9_plain_ble_agent():
    unit = (Path(__file__).parents[2] / "scripts" / "ds-imu.service").read_text(
        encoding="utf-8"
    )

    assert "User=digital-spotter" in unit
    assert "NoNewPrivileges=true" in unit
    assert "ProtectSystem=strict" in unit
    assert "ESP32-C3-Test" in unit
    assert "50:78:7D:92:61:1A" in unit
    assert "core-events.sock" in unit
    assert "device-key" not in unit
    assert "mqtt" not in unit.lower()
