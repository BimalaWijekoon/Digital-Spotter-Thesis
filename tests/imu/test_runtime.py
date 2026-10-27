from __future__ import annotations

import asyncio

import pytest

from digital_spotter.imu import FakeWearable, IMUAgentCore
from digital_spotter.imu.protocol import DEVICE_INFO_UUID, IMU_STREAM_UUID, STATUS_UUID
from digital_spotter.imu.runtime import IMUAgentRuntime, read_provisioned_device_id


class FakeTransport:
    def __init__(self, wearable: FakeWearable):
        self.wearable = wearable
        self.is_connected = False
        self.connect_count = 0
        self.callbacks = {}
        self.disconnected = asyncio.Event()

    async def connect(self):
        self.connect_count += 1
        self.is_connected = True

    async def disconnect(self):
        self.is_connected = False
        self.disconnected.set()

    async def read(self, uuid):
        if uuid == DEVICE_INFO_UUID:
            return self.wearable.device_info()
        if uuid == STATUS_UUID:
            return self.wearable.status()
        raise AssertionError(uuid)

    async def start_notify(self, uuid, callback):
        self.callbacks[uuid] = callback
        if uuid == IMU_STREAM_UUID:
            asyncio.get_running_loop().call_soon(
                callback,
                self.wearable.packet(sequence=1, sensor_time_us=20_000),
            )

    async def wait_disconnected(self):
        await self.disconnected.wait()


class RecordingPublisher:
    def __init__(self):
        self.events = []
        self.received = asyncio.Event()
        self.closed = False

    async def send(self, event):
        self.events.append(event)
        self.received.set()

    async def close(self):
        self.closed = True


class FakeControl:
    def __init__(self):
        self.opened = False
        self.streaming = False
        self.closed = False
        self.sync_count = 0

    async def open(self, status):
        assert status.device_id == "imu-fake-001"
        self.opened = True

    async def time_sync(self):
        self.sync_count += 1
        return True

    async def set_streaming(self, enabled):
        assert self.opened
        self.streaming = enabled

    async def close(self):
        self.closed = True


def test_runtime_processes_fake_transport_and_stops_cleanly():
    async def scenario():
        wearable = FakeWearable()
        transport = FakeTransport(wearable)
        publisher = RecordingPublisher()
        control = FakeControl()
        runtime = IMUAgentRuntime(
            core=IMUAgentCore(expected_device_id=wearable.device_id),
            transport=transport,
            control=control,
            publisher=publisher,
            initial_clock_exchanges=1,
            initial_clock_interval_s=0,
        )
        task = asyncio.create_task(runtime.run())
        await asyncio.wait_for(publisher.received.wait(), timeout=1.0)
        runtime.stop()
        await asyncio.wait_for(task, timeout=1.0)
        assert transport.connect_count == 1
        assert len(publisher.events) == 1
        assert publisher.closed is True
        assert control.sync_count == 1
        assert control.streaming is False
        assert control.closed is True

    asyncio.run(scenario())


def test_notification_queue_drops_oldest_instead_of_growing():
    wearable = FakeWearable()
    runtime = IMUAgentRuntime(
        core=IMUAgentCore(expected_device_id=wearable.device_id),
        transport=FakeTransport(wearable),
        control=FakeControl(),
        publisher=RecordingPublisher(),
        queue_size=2,
    )
    runtime._enqueue("imu", b"one")
    runtime._enqueue("imu", b"two")
    runtime._enqueue("imu", b"three")

    assert runtime.queue.qsize() == 2
    assert runtime.notification_drops == 1


def test_provisioned_identity_file_is_bounded_and_strict(tmp_path):
    path = tmp_path / "wearable-id"
    path.write_text("imu-device-001\n", encoding="utf-8")
    assert read_provisioned_device_id(path) == "imu-device-001"

    path.write_text("bad identity", encoding="utf-8")
    with pytest.raises(ValueError, match="invalid"):
        read_provisioned_device_id(path)
    path.write_text("x" * 129, encoding="utf-8")
    with pytest.raises(ValueError, match="oversized"):
        read_provisioned_device_id(path)
