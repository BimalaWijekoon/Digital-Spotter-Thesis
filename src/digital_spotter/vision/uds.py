"""Bounded, background Unix-socket publication for vision events."""

from __future__ import annotations

import os
import queue
import socket
import stat
import struct
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Protocol

from digital_spotter.contracts import EventEnvelope, MAX_EVENT_BYTES
from digital_spotter.imu.uds import encode_event_frame


MAX_UNIX_PATH_BYTES = 107


class VisionUDSError(OSError):
    """A local vision event cannot be delivered safely."""


class VisionEventTransport(Protocol):
    def send(self, frame: bytes) -> None: ...
    def close(self) -> None: ...


@dataclass(frozen=True)
class VisionPublisherCounters:
    events_enqueued: int
    events_sent: int
    queue_drops: int
    transport_drops: int
    transport_failures: int
    permission_rejections: int


class UnixVisionEventTransport:
    """One reusable AF_UNIX stream with local permission and peer checks."""

    def __init__(
        self,
        socket_path: Path,
        *,
        allowed_peer_uids: frozenset[int] | None = None,
        connect_timeout_s: float = 0.2,
        send_timeout_s: float = 0.2,
    ) -> None:
        if connect_timeout_s <= 0 or send_timeout_s <= 0:
            raise ValueError("UDS timeouts must be positive")
        resolved = socket_path.expanduser().resolve(strict=False)
        if len(os.fsencode(resolved)) > MAX_UNIX_PATH_BYTES:
            raise ValueError("vision UDS path exceeds the Linux AF_UNIX limit")
        self.socket_path = resolved
        self.allowed_peer_uids = allowed_peer_uids
        self.connect_timeout_s = connect_timeout_s
        self.send_timeout_s = send_timeout_s
        self._socket: socket.socket | None = None

    @staticmethod
    def _validate_frame(frame: bytes) -> None:
        if not isinstance(frame, bytes) or len(frame) < 5:
            raise VisionUDSError("vision UDS frame is truncated")
        declared = struct.unpack(">I", frame[:4])[0]
        if declared == 0 or declared > MAX_EVENT_BYTES:
            raise VisionUDSError("vision UDS frame length is invalid")
        if len(frame) != declared + 4:
            raise VisionUDSError("vision UDS frame length does not match payload")

    def _connect(self) -> socket.socket:
        try:
            metadata = self.socket_path.lstat()
        except OSError as exc:
            raise VisionUDSError("vision event socket is unavailable") from exc
        if not stat.S_ISSOCK(metadata.st_mode):
            raise VisionUDSError("vision event path is not a Unix socket")
        if stat.S_IMODE(metadata.st_mode) & 0o007:
            raise PermissionError("vision event socket grants permissions to other users")

        connection = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        connection.settimeout(self.connect_timeout_s)
        try:
            connection.connect(str(self.socket_path))
            if self.allowed_peer_uids is not None:
                if not hasattr(socket, "SO_PEERCRED"):
                    raise PermissionError("Unix peer credentials are unavailable")
                credentials = connection.getsockopt(
                    socket.SOL_SOCKET,
                    socket.SO_PEERCRED,
                    struct.calcsize("3i"),
                )
                _pid, uid, _gid = struct.unpack("3i", credentials)
                if uid not in self.allowed_peer_uids:
                    raise PermissionError("vision event socket peer UID is not allowed")
            connection.settimeout(self.send_timeout_s)
            self._socket = connection
            return connection
        except Exception:
            connection.close()
            raise

    def send(self, frame: bytes) -> None:
        self._validate_frame(frame)
        connection = self._socket or self._connect()
        try:
            connection.sendall(frame)
        except (ConnectionError, OSError):
            self.close()
            raise

    def close(self) -> None:
        connection, self._socket = self._socket, None
        if connection is not None:
            connection.close()


class BoundedVisionEventPublisher:
    """Keep the worker non-blocking with a fixed drop-oldest sender queue."""

    def __init__(
        self,
        *,
        transport: VisionEventTransport,
        queue_size: int = 4,
        reconnect_backoff_s: tuple[float, ...] = (0.1, 0.5, 1.0, 2.0),
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        if not 1 <= queue_size <= 16:
            raise ValueError("vision publisher queue size must be between 1 and 16")
        if not reconnect_backoff_s or any(
            delay < 0 or delay > 30 for delay in reconnect_backoff_s
        ):
            raise ValueError("vision reconnect backoff must be bounded and non-negative")
        self.transport = transport
        self.queue: queue.Queue[bytes] = queue.Queue(maxsize=queue_size)
        self.reconnect_backoff_s = reconnect_backoff_s
        self._monotonic = monotonic
        self._stop_requested = threading.Event()
        self._thread: threading.Thread | None = None
        self._counter_lock = threading.Lock()
        self._enqueue_lock = threading.Lock()
        self._events_enqueued = 0
        self._events_sent = 0
        self._queue_drops = 0
        self._transport_drops = 0
        self._transport_failures = 0
        self._permission_rejections = 0

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        if self._thread is not None:
            raise RuntimeError("vision publisher instances can start only once")
        self._stop_requested.clear()
        self._thread = threading.Thread(
            target=self._send_loop,
            name="vision-uds-publisher",
            daemon=True,
        )
        self._thread.start()

    def publish(self, event: EventEnvelope) -> None:
        if not self.is_running or self._stop_requested.is_set():
            raise RuntimeError("vision publisher is not running")
        frame = encode_event_frame(event)
        with self._enqueue_lock:
            with self._counter_lock:
                self._events_enqueued += 1
            if self.queue.full():
                try:
                    self.queue.get_nowait()
                    self.queue.task_done()
                except queue.Empty:
                    pass
                else:
                    with self._counter_lock:
                        self._queue_drops += 1
            self.queue.put_nowait(frame)

    def counters(self) -> VisionPublisherCounters:
        with self._counter_lock:
            return VisionPublisherCounters(
                events_enqueued=self._events_enqueued,
                events_sent=self._events_sent,
                queue_drops=self._queue_drops,
                transport_drops=self._transport_drops,
                transport_failures=self._transport_failures,
                permission_rejections=self._permission_rejections,
            )

    def _send_loop(self) -> None:
        failure_index = 0
        next_attempt_at = 0.0
        while not self._stop_requested.is_set() or not self.queue.empty():
            try:
                frame = self.queue.get(timeout=0.05)
            except queue.Empty:
                continue
            try:
                now = self._monotonic()
                if now < next_attempt_at:
                    with self._counter_lock:
                        self._transport_drops += 1
                    continue
                try:
                    self.transport.send(frame)
                except PermissionError:
                    with self._counter_lock:
                        self._permission_rejections += 1
                        self._transport_failures += 1
                        self._transport_drops += 1
                    self.transport.close()
                    delay = self.reconnect_backoff_s[
                        min(failure_index, len(self.reconnect_backoff_s) - 1)
                    ]
                    failure_index += 1
                    next_attempt_at = now + delay
                except (ConnectionError, OSError):
                    with self._counter_lock:
                        self._transport_failures += 1
                        self._transport_drops += 1
                    self.transport.close()
                    delay = self.reconnect_backoff_s[
                        min(failure_index, len(self.reconnect_backoff_s) - 1)
                    ]
                    failure_index += 1
                    next_attempt_at = now + delay
                else:
                    with self._counter_lock:
                        self._events_sent += 1
                    failure_index = 0
                    next_attempt_at = 0.0
            finally:
                self.queue.task_done()

    def close(self, *, timeout_s: float = 1.0) -> None:
        if timeout_s <= 0:
            raise ValueError("vision publisher close timeout must be positive")
        self._stop_requested.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout=timeout_s)
            if thread.is_alive():
                raise TimeoutError("vision publisher did not stop within its timeout")
        self.transport.close()
        while True:
            try:
                self.queue.get_nowait()
            except queue.Empty:
                break
            else:
                self.queue.task_done()
                with self._counter_lock:
                    self._transport_drops += 1
