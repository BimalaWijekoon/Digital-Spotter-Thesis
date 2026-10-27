"""Reconnect-capable canonical Pi runtime for the frozen R9 wearable."""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import signal
import sys
import time
from pathlib import Path
from typing import Protocol

from digital_spotter.feedback import DemoCue
from digital_spotter.feedback.uds import UnixWearableCueServer
from digital_spotter.contracts import (
    ClockState,
    EventEnvelope,
    IMUSample,
    MonotonicNanoseconds,
)
from digital_spotter.imu.r9_agent import R9AgentCore
from digital_spotter.imu.r9_protocol import (
    CONTROL_UUID,
    DEVICE_ADDRESS,
    DEVICE_INFO_UUID,
    DEVICE_NAME,
    IMU_STREAM_UUID,
    RESEARCH_DEVICE_ID,
    STATUS_UUID,
)
from digital_spotter.imu.r9_transport import R9BleakTransport
from digital_spotter.imu.uds import UnixEventPublisher


LOGGER = logging.getLogger("digital_spotter.imu")


class EventPublisher(Protocol):
    async def send(self, event: EventEnvelope[IMUSample]) -> None: ...

    async def close(self) -> None: ...


class R9IMUAgentRuntime:
    """Own one BLE client and deliver only the newest pending notification."""

    def __init__(
        self,
        *,
        core: R9AgentCore,
        transport: R9BleakTransport,
        publisher: EventPublisher,
        queue_size: int = 16,
        status_interval_s: float = 1.0,
        reconnect_backoff_s: tuple[float, ...] = (2.0, 4.0, 8.0, 15.0),
    ) -> None:
        if not 1 <= queue_size <= 16:
            raise ValueError("queue_size must be between 1 and 16")
        if not 0.2 <= status_interval_s <= 60.0:
            raise ValueError("status_interval_s must be between 0.2 and 60 seconds")
        if not reconnect_backoff_s or any(
            value < 0 or value > 60 for value in reconnect_backoff_s
        ):
            raise ValueError("reconnect backoff must contain bounded non-negative values")
        self.core = core
        self.transport = transport
        self.publisher = publisher
        self.queue: asyncio.Queue[tuple[bytes, int]] = asyncio.Queue(maxsize=queue_size)
        self.demo_cues: asyncio.Queue[tuple[DemoCue, asyncio.Future[bytes]]] = (
            asyncio.Queue(maxsize=4)
        )
        self._control_lock = asyncio.Lock()
        self.status_interval_s = status_interval_s
        self.reconnect_backoff_s = reconnect_backoff_s
        self.stop_event = asyncio.Event()
        self._last_publisher_warning_ns = 0
        self._attempt_established = False

    def _enqueue(self, payload: bytes) -> None:
        item = (bytes(payload), time.monotonic_ns())
        if self.queue.full():
            self.queue.get_nowait()
            self.queue.task_done()
            self.core.note_notification_drop()
        self.queue.put_nowait(item)

    def _clear_queue(self) -> None:
        while not self.queue.empty():
            self.queue.get_nowait()
            self.queue.task_done()

    async def _send_control(self, request: bytes, expected_response: bytes) -> bytes:
        async with self._control_lock:
            await self.transport.write(CONTROL_UUID, request, response=True)
            response = await self.transport.read(CONTROL_UUID)
            if response != expected_response:
                raise RuntimeError(
                    f"R9 control {request!r} returned unexpected response {response!r}"
                )
            return response

    async def send_demo_cue(self, cue: DemoCue) -> bytes:
        """Queue one bounded cue through this runtime's sole BLE connection."""

        if not isinstance(cue, DemoCue):
            raise ValueError("invalid demo cue")
        if not self.transport.is_connected or not self._attempt_established:
            raise RuntimeError("wearable is not streaming")
        future = asyncio.get_running_loop().create_future()
        try:
            self.demo_cues.put_nowait((cue, future))
        except asyncio.QueueFull as exc:
            raise RuntimeError("wearable cue queue is full") from exc
        return await asyncio.wait_for(future, timeout=2.0)

    async def _process_demo_cues(self) -> None:
        command = {
            DemoCue.START: (b"demo:start", b"ok:demo_start"),
            DemoCue.GOOD: (b"demo:good", b"ok:demo_good"),
            DemoCue.BAD: (b"demo:bad", b"ok:demo_bad"),
            DemoCue.COMPLETE: (b"demo:stop", b"ok:demo_stop"),
        }
        while not self.stop_event.is_set() and self.transport.is_connected:
            cue, future = await self.demo_cues.get()
            try:
                request, expected = command[cue]
                response = await self._send_control(request, expected)
                if not future.done():
                    future.set_result(response)
            except Exception as exc:
                if not future.done():
                    future.set_exception(exc)
            finally:
                self.demo_cues.task_done()

    def _fail_pending_demo_cues(self, reason: str) -> None:
        while not self.demo_cues.empty():
            _cue, future = self.demo_cues.get_nowait()
            if not future.done():
                future.set_exception(RuntimeError(reason))
            self.demo_cues.task_done()

    async def _read_status_exchange(self) -> None:
        """Timestamp one on-demand R9 status read in the Pi monotonic domain."""

        t1_pi_ns = MonotonicNanoseconds(time.monotonic_ns())
        payload = await self.transport.read(STATUS_UUID)
        t4_pi_ns = MonotonicNanoseconds(time.monotonic_ns())
        self.core.accept_status_exchange(
            payload,
            t1_pi_ns=t1_pi_ns,
            t4_pi_ns=t4_pi_ns,
        )

    async def _process_notifications(self) -> None:
        while not self.stop_event.is_set() and self.transport.is_connected:
            try:
                payload, arrival_ns = await asyncio.wait_for(
                    self.queue.get(),
                    timeout=1.0,
                )
            except TimeoutError:
                continue
            try:
                event = self.core.accept_packet(
                    payload,
                    arrival_monotonic_ns=MonotonicNanoseconds(arrival_ns),
                )
                if event is not None:
                    if event.payload.clock_state is not ClockState.SYNCHRONIZED:
                        self.core.note_clock_gate_drop()
                        continue
                    try:
                        await self.publisher.send(event)
                    except (ConnectionError, OSError) as exc:
                        self.core.note_publisher_failure()
                        now_ns = time.monotonic_ns()
                        if now_ns - self._last_publisher_warning_ns >= 5_000_000_000:
                            LOGGER.warning("core event socket unavailable: %s", exc)
                            self._last_publisher_warning_ns = now_ns
            except Exception as exc:
                LOGGER.warning("rejected R9 notification: %s", exc)
            finally:
                self.queue.task_done()

    async def _poll_status(self) -> None:
        while not self.stop_event.is_set() and self.transport.is_connected:
            try:
                await asyncio.wait_for(
                    self.stop_event.wait(),
                    timeout=self.status_interval_s,
                )
            except TimeoutError:
                await self._read_status_exchange()

    async def _connection(self) -> None:
        self._attempt_established = False
        self._clear_queue()
        self.core.mark_connecting()
        await self.transport.connect()
        self.core.mark_connected()
        tasks: list[asyncio.Task] = []
        notification_started = False
        try:
            self.core.accept_device_info(await self.transport.read(DEVICE_INFO_UUID))
            await self._read_status_exchange()
            await self.transport.start_notify(IMU_STREAM_UUID, self._enqueue)
            notification_started = True
            await self._send_control(b"stream:start", b"ok:streaming")
            # BlueZ can deliver the characteristic's cached final value from the
            # previous R9 stream while CCCD setup and the start command overlap.
            # R9 resets its raw sequence for every accepted stream:start, so the
            # acknowledged command is the only safe epoch boundary.
            self._clear_queue()
            self.core.begin_stream()
            self.core.mark_streaming(True)
            tasks = [
                asyncio.create_task(
                    self._process_notifications(),
                    name="r9-notification-processor",
                ),
                asyncio.create_task(self._poll_status(), name="r9-status-poller"),
                asyncio.create_task(
                    self._process_demo_cues(), name="r9-demo-cue-processor"
                ),
                asyncio.create_task(
                    self.transport.wait_disconnected(),
                    name="r9-disconnect-waiter",
                ),
                asyncio.create_task(self.stop_event.wait(), name="r9-stop-waiter"),
            ]
            self._attempt_established = True
            done, _pending = await asyncio.wait(
                set(tasks),
                return_when=asyncio.FIRST_COMPLETED,
            )
            LOGGER.info(
                "R9 connection task completed: %s",
                ",".join(sorted(task.get_name() for task in done)),
            )
            for task in done:
                if task.cancelled():
                    continue
                error = task.exception()
                if error is not None:
                    raise error
        finally:
            self.core.mark_stopping()
            for task in tasks:
                task.cancel()
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
            if self.transport.is_connected:
                try:
                    await self._send_control(b"stream:stop", b"ok:idle")
                except Exception as exc:
                    LOGGER.warning("R9 stop command failed during cleanup: %s", exc)
                if notification_started:
                    try:
                        await self.transport.stop_notify(IMU_STREAM_UUID)
                    except Exception as exc:
                        LOGGER.warning("R9 notification cleanup failed: %s", exc)
            await self.transport.disconnect()
            self.core.mark_disconnected()
            self._clear_queue()
            self._fail_pending_demo_cues("wearable connection closed")

    async def run(self) -> None:
        failure_index = 0
        try:
            while not self.stop_event.is_set():
                try:
                    await self._connection()
                    failure_index = 0
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    LOGGER.warning("R9 connection failed: %s", exc)
                    if not self._attempt_established:
                        self.core.note_connection_failure()
                        self.core.mark_disconnected()
                if self.stop_event.is_set():
                    break
                if self._attempt_established:
                    self.core.note_reconnect()
                delay = self.reconnect_backoff_s[
                    min(failure_index, len(self.reconnect_backoff_s) - 1)
                ]
                failure_index += 1
                try:
                    await asyncio.wait_for(self.stop_event.wait(), timeout=delay)
                except TimeoutError:
                    pass
        finally:
            await self.publisher.close()

    def stop(self) -> None:
        self.stop_event.set()


async def _run(args: argparse.Namespace) -> None:
    runtime = R9IMUAgentRuntime(
        core=R9AgentCore(device_id=args.device_id),
        transport=R9BleakTransport(
            expected_name=args.device_name,
            expected_address=args.device_address,
            scan_timeout_s=args.scan_timeout,
            connect_timeout_s=args.connect_timeout,
        ),
        publisher=UnixEventPublisher(args.socket),
    )
    cue_server = None
    if args.control_socket is not None:
        cue_server = UnixWearableCueServer(
            socket_path=args.control_socket,
            on_cue=runtime.send_demo_cue,
            allowed_uids=frozenset({os.getuid()}),
        )
        await cue_server.start()
    loop = asyncio.get_running_loop()
    for signum in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(signum, runtime.stop)
    try:
        await runtime.run()
    finally:
        if cue_server is not None:
            await cue_server.close()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ds-imu-agent")
    parser.add_argument("--device-id", default=RESEARCH_DEVICE_ID)
    parser.add_argument("--device-name", default=DEVICE_NAME)
    parser.add_argument("--device-address", default=DEVICE_ADDRESS)
    parser.add_argument("--socket", type=Path, required=True)
    parser.add_argument("--control-socket", type=Path)
    parser.add_argument("--scan-timeout", type=float, default=15.0)
    parser.add_argument("--connect-timeout", type=float, default=20.0)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s %(name)s %(message)s",
    )
    try:
        asyncio.run(_run(args))
    except (ValueError, OSError) as exc:
        print(f"IMU agent startup failed: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
