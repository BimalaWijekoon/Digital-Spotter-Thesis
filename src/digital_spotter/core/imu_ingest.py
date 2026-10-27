"""Validated local UDS receiver for canonical R11 IMU events."""

from __future__ import annotations

import asyncio
import socket
import stat
import struct
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from digital_spotter.contracts import (
    ContractDecodeError,
    EventEnvelope,
    IMUSample,
    MAX_EVENT_BYTES,
)
from digital_spotter.core.sessions import SessionInputError


@dataclass(frozen=True)
class IMUIngestCounters:
    connections_accepted: int
    connections_rejected: int
    frames_received: int
    events_accepted: int
    events_ignored: int
    events_rejected: int


class UnixIMUEventServer:
    """Read length-prefixed R11 events without performing persistence inline."""

    def __init__(
        self,
        *,
        socket_path: Path,
        on_event: Callable[[EventEnvelope[IMUSample]], bool],
        allowed_uids: frozenset[int] | None = None,
        socket_mode: int = 0o660,
        max_clients: int = 1,
    ) -> None:
        if not 1 <= max_clients <= 8:
            raise ValueError("max_clients must be between 1 and 8")
        if socket_mode & ~0o777:
            raise ValueError("socket_mode contains unsupported bits")
        self.socket_path = socket_path.resolve()
        self.on_event = on_event
        self.allowed_uids = allowed_uids
        self.socket_mode = socket_mode
        self.max_clients = max_clients
        self._server: asyncio.AbstractServer | None = None
        self._clients: set[asyncio.StreamWriter] = set()
        self._client_tasks: set[asyncio.Task[None]] = set()
        self._connections_accepted = 0
        self._connections_rejected = 0
        self._frames_received = 0
        self._events_accepted = 0
        self._events_ignored = 0
        self._events_rejected = 0

    async def start(self) -> None:
        if self._server is not None:
            return
        self.socket_path.parent.mkdir(parents=True, exist_ok=True)
        if self.socket_path.exists():
            mode = self.socket_path.stat().st_mode
            if not stat.S_ISSOCK(mode):
                raise OSError(f"refusing to replace non-socket path: {self.socket_path}")
            self.socket_path.unlink()
        self._server = await asyncio.start_unix_server(
            self._handle_client,
            path=self.socket_path,
            limit=MAX_EVENT_BYTES + 4,
        )
        self.socket_path.chmod(self.socket_mode)

    async def close(self) -> None:
        server, self._server = self._server, None
        if server is not None:
            server.close()
        for writer in tuple(self._clients):
            writer.close()
        tasks = tuple(self._client_tasks)
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        if server is not None:
            await server.wait_closed()
        self._clients.clear()
        self._client_tasks.clear()
        if self.socket_path.exists() and stat.S_ISSOCK(self.socket_path.stat().st_mode):
            self.socket_path.unlink()

    def counters(self) -> IMUIngestCounters:
        return IMUIngestCounters(
            connections_accepted=self._connections_accepted,
            connections_rejected=self._connections_rejected,
            frames_received=self._frames_received,
            events_accepted=self._events_accepted,
            events_ignored=self._events_ignored,
            events_rejected=self._events_rejected,
        )

    def _peer_allowed(self, writer: asyncio.StreamWriter) -> bool:
        if self.allowed_uids is None:
            return True
        peer_socket = writer.get_extra_info("socket")
        if peer_socket is None or not hasattr(socket, "SO_PEERCRED"):
            return False
        credentials = peer_socket.getsockopt(
            socket.SOL_SOCKET,
            socket.SO_PEERCRED,
            struct.calcsize("3i"),
        )
        _pid, uid, _gid = struct.unpack("3i", credentials)
        return uid in self.allowed_uids

    async def _handle_client(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        if len(self._clients) >= self.max_clients or not self._peer_allowed(writer):
            self._connections_rejected += 1
            writer.close()
            await writer.wait_closed()
            return
        self._connections_accepted += 1
        self._clients.add(writer)
        client_task = asyncio.current_task()
        if client_task is not None:
            self._client_tasks.add(client_task)
        try:
            while True:
                try:
                    header = await reader.readexactly(4)
                except asyncio.IncompleteReadError as exc:
                    if exc.partial:
                        self._events_rejected += 1
                    return
                declared = struct.unpack(">I", header)[0]
                if declared == 0 or declared > MAX_EVENT_BYTES:
                    self._events_rejected += 1
                    return
                try:
                    payload = await reader.readexactly(declared)
                except asyncio.IncompleteReadError:
                    self._events_rejected += 1
                    return
                self._frames_received += 1
                try:
                    event = EventEnvelope[IMUSample].from_messagepack(payload)
                    accepted = self.on_event(event)
                except (ContractDecodeError, SessionInputError, ValueError):
                    self._events_rejected += 1
                    continue
                if accepted:
                    self._events_accepted += 1
                else:
                    self._events_ignored += 1
        finally:
            self._clients.discard(writer)
            if client_task is not None:
                self._client_tasks.discard(client_task)
            writer.close()
            try:
                await writer.wait_closed()
            except (ConnectionError, OSError):
                pass
