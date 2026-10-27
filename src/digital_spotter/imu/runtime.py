"""Reconnect-capable BlueZ runtime for the canonical IMU agent."""

from __future__ import annotations

import argparse
import asyncio
import logging
import signal
import sys
import time
from pathlib import Path

from digital_spotter.contracts import MonotonicNanoseconds
from digital_spotter.imu.agent import IMUAgentCore
from digital_spotter.imu.bleak_transport import BleakWearableTransport
from digital_spotter.imu.clock import SensorClockMapper
from digital_spotter.imu.control import load_device_key
from digital_spotter.imu.control_client import WearableControlClient
from digital_spotter.imu.protocol import DEVICE_INFO_UUID, IMU_STREAM_UUID, STATUS_UUID
from digital_spotter.imu.uds import UnixEventPublisher


LOGGER = logging.getLogger("digital_spotter.imu")


def read_provisioned_device_id(path: Path) -> str:
    try:
        if not path.is_file():
            raise ValueError("identity file does not exist")
        if path.stat().st_size > 128:
            raise ValueError("identity file is oversized")
        value = path.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeError) as exc:
        raise ValueError(f"cannot read wearable identity: {exc}") from exc
    if not value or len(value) > 64 or any(not (char.isalnum() or char in "._-") for char in value):
        raise ValueError("wearable identity is invalid")
    return value


class IMUAgentRuntime:
    def __init__(
        self,
        *,
        core: IMUAgentCore,
        transport: BleakWearableTransport,
        control: WearableControlClient,
        publisher: UnixEventPublisher,
        queue_size: int = 256,
        initial_clock_exchanges: int = 5,
        initial_clock_interval_s: float = 0.1,
        clock_sync_interval_s: float = 5.0,
    ):
        if not 1 <= queue_size <= 4096:
            raise ValueError("queue_size must be between 1 and 4096")
        self.core = core
        self.transport = transport
        self.control = control
        self.publisher = publisher
        self.queue: asyncio.Queue[tuple[str, bytes, int]] = asyncio.Queue(maxsize=queue_size)
        self.stop_event = asyncio.Event()
        self.notification_drops = 0
        self.reconnects = 0
        if not 1 <= initial_clock_exchanges <= 20:
            raise ValueError("initial clock exchanges must be between 1 and 20")
        if not 0 <= initial_clock_interval_s <= 5:
            raise ValueError("initial clock interval must be between 0 and 5 seconds")
        if not 1 <= clock_sync_interval_s <= 60:
            raise ValueError("clock sync interval must be between 1 and 60 seconds")
        self.initial_clock_exchanges = initial_clock_exchanges
        self.initial_clock_interval_s = initial_clock_interval_s
        self.clock_sync_interval_s = clock_sync_interval_s

    def _enqueue(self, kind: str, payload: bytes) -> None:
        item = (kind, payload, time.monotonic_ns())
        if self.queue.full():
            self.queue.get_nowait()
            self.queue.task_done()
            self.notification_drops += 1
        self.queue.put_nowait(item)

    async def _process_notifications(self) -> None:
        while not self.stop_event.is_set() and self.transport.is_connected:
            try:
                kind, payload, arrival = await asyncio.wait_for(self.queue.get(), timeout=1.0)
            except TimeoutError:
                continue
            try:
                if kind == "status":
                    self.core.accept_status(payload)
                else:
                    event = self.core.accept_packet(
                        payload,
                        arrival_monotonic_ns=MonotonicNanoseconds(arrival),
                    )
                    if event is not None:
                        await self.publisher.send(event)
            except Exception as exc:
                LOGGER.warning("rejected wearable notification: %s", exc)
            finally:
                self.queue.task_done()

    async def _maintain_clock(self) -> None:
        while not self.stop_event.is_set() and self.transport.is_connected:
            try:
                await asyncio.wait_for(
                    self.stop_event.wait(),
                    timeout=self.clock_sync_interval_s,
                )
            except TimeoutError:
                await self.control.time_sync()

    async def _connection(self) -> None:
        await self.transport.connect()
        tasks: list[asyncio.Task] = []
        try:
            self.core.accept_device_info(await self.transport.read(DEVICE_INFO_UUID))
            status = self.core.accept_status(await self.transport.read(STATUS_UUID))
            await self.control.open(status)
            await self.transport.start_notify(STATUS_UUID, lambda data: self._enqueue("status", data))
            await self.transport.start_notify(IMU_STREAM_UUID, lambda data: self._enqueue("imu", data))
            for exchange in range(self.initial_clock_exchanges):
                await self.control.time_sync()
                if exchange + 1 < self.initial_clock_exchanges and self.initial_clock_interval_s:
                    await asyncio.sleep(self.initial_clock_interval_s)
            await self.control.set_streaming(True)
            tasks = [
                asyncio.create_task(self._process_notifications()),
                asyncio.create_task(self.transport.wait_disconnected()),
                asyncio.create_task(self.stop_event.wait()),
                asyncio.create_task(self._maintain_clock()),
            ]
            await asyncio.wait(
                set(tasks),
                return_when=asyncio.FIRST_COMPLETED,
            )
        finally:
            for task in tasks:
                task.cancel()
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
            if self.transport.is_connected:
                try:
                    await self.control.set_streaming(False)
                except Exception as exc:
                    LOGGER.warning("wearable stop command failed during disconnect: %s", exc)
            try:
                await self.control.close()
            except Exception as exc:
                LOGGER.warning("wearable control cleanup failed: %s", exc)
            await self.transport.disconnect()

    async def run(self) -> None:
        delay = 0.5
        while not self.stop_event.is_set():
            try:
                await self._connection()
                delay = 0.5
            except Exception as exc:
                self.reconnects += 1
                LOGGER.warning("wearable connection failed: %s", exc)
            if not self.stop_event.is_set():
                try:
                    await asyncio.wait_for(self.stop_event.wait(), timeout=delay)
                except TimeoutError:
                    pass
                delay = min(delay * 2.0, 10.0)
        await self.publisher.close()

    def stop(self) -> None:
        self.stop_event.set()


async def _run(args) -> None:
    device_id = read_provisioned_device_id(args.device_id_file)
    device_key = load_device_key(args.device_key_file)
    clock_mapper = SensorClockMapper()
    transport = BleakWearableTransport(
        scan_timeout_s=args.scan_timeout,
        connect_timeout_s=args.connect_timeout,
    )
    runtime = IMUAgentRuntime(
        core=IMUAgentCore(
            expected_device_id=device_id,
            clock_mapper=clock_mapper,
        ),
        transport=transport,
        control=WearableControlClient(
            transport=transport,
            device_key=device_key,
            device_id=device_id,
            clock_mapper=clock_mapper,
        ),
        publisher=UnixEventPublisher(args.socket),
    )
    loop = asyncio.get_running_loop()
    for signum in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(signum, runtime.stop)
    await runtime.run()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ds-imu-agent")
    parser.add_argument("--device-id-file", type=Path, required=True)
    parser.add_argument("--device-key-file", type=Path, required=True)
    parser.add_argument("--socket", type=Path, required=True)
    parser.add_argument("--scan-timeout", type=float, default=10.0)
    parser.add_argument("--connect-timeout", type=float, default=30.0)
    return parser


def main(argv=None) -> int:
    args = _parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    try:
        asyncio.run(_run(args))
    except (ValueError, OSError) as exc:
        print(f"IMU agent startup failed: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
