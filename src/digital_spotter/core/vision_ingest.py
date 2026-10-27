"""Validated local receiver for canonical vision pose and health events."""

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
    HealthState,
    MAX_EVENT_BYTES,
    PoseSample,
    Source,
)
from digital_spotter.core.sessions import SessionInputError


@dataclass(frozen=True)
class VisionIngestCounters:
    connections_accepted: int
    connections_rejected: int
    frames_received: int
    poses_accepted: int
    poses_ignored: int
    health_ignored: int
    events_rejected: int


class UnixVisionEventServer:
    """Consume the worker's existing bounded UDS frames; never write a database."""

    def __init__(
        self,
        *,
        socket_path: Path,
        on_pose: Callable[[EventEnvelope[PoseSample]], bool],
        allowed_uids: frozenset[int] | None = None,
        socket_mode: int = 0o600,
    ) -> None:
        if socket_mode & ~0o777 or socket_mode & 0o007:
            raise ValueError("vision socket must not grant access to other users")
        self.socket_path = socket_path.resolve(strict=False)
        self.on_pose = on_pose
        self.allowed_uids = allowed_uids
        self.socket_mode = socket_mode
        self._server: asyncio.AbstractServer | None = None
        self._owned_inode: int | None = None
        self._clients: set[asyncio.StreamWriter] = set()
        self._tasks: set[asyncio.Task[None]] = set()
        self._connections_accepted = 0
        self._connections_rejected = 0
        self._frames_received = 0
        self._poses_accepted = 0
        self._poses_ignored = 0
        self._health_ignored = 0
        self._events_rejected = 0

    async def start(self) -> None:
        if self._server is not None:
            return
        self.socket_path.parent.mkdir(parents=True, exist_ok=True)
        if self.socket_path.exists() or self.socket_path.is_symlink():
            raise FileExistsError(f"vision event socket path already exists: {self.socket_path}")
        self._server = await asyncio.start_unix_server(
            self._handle_client,
            path=self.socket_path,
            limit=MAX_EVENT_BYTES + 4,
        )
        self.socket_path.chmod(self.socket_mode)
        self._owned_inode = self.socket_path.stat().st_ino

    async def close(self) -> None:
        server, self._server = self._server, None
        if server is not None:
            server.close()
        for writer in tuple(self._clients):
            writer.close()
        tasks = tuple(self._tasks)
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        if server is not None:
            await server.wait_closed()
        self._clients.clear()
        self._tasks.clear()
        try:
            metadata = self.socket_path.lstat()
        except FileNotFoundError:
            metadata = None
        if (
            metadata is not None
            and stat.S_ISSOCK(metadata.st_mode)
            and metadata.st_ino == self._owned_inode
        ):
            self.socket_path.unlink()
        self._owned_inode = None

    def counters(self) -> VisionIngestCounters:
        return VisionIngestCounters(
            connections_accepted=self._connections_accepted,
            connections_rejected=self._connections_rejected,
            frames_received=self._frames_received,
            poses_accepted=self._poses_accepted,
            poses_ignored=self._poses_ignored,
            health_ignored=self._health_ignored,
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

    def _accept_payload(self, payload: bytes) -> None:
        try:
            event = EventEnvelope[PoseSample].from_messagepack(payload)
        except ContractDecodeError:
            try:
                health = EventEnvelope[HealthState].from_messagepack(payload)
            except ContractDecodeError:
                self._events_rejected += 1
            else:
                if health.source is Source.VISION:
                    self._health_ignored += 1
                else:
                    self._events_rejected += 1
            return
        try:
            accepted = self.on_pose(event)
        except (SessionInputError, ValueError):
            self._events_rejected += 1
        else:
            if accepted:
                self._poses_accepted += 1
            else:
                self._poses_ignored += 1

    async def _handle_client(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        if self._clients or not self._peer_allowed(writer):
            self._connections_rejected += 1
            writer.close()
            await writer.wait_closed()
            return
        self._connections_accepted += 1
        self._clients.add(writer)
        task = asyncio.current_task()
        if task is not None:
            self._tasks.add(task)
        try:
            while True:
                try:
                    header = await reader.readexactly(4)
                except asyncio.IncompleteReadError as exc:
                    if exc.partial:
                        self._events_rejected += 1
                    return
                declared = struct.unpack(">I", header)[0]
                if not 1 <= declared <= MAX_EVENT_BYTES:
                    self._events_rejected += 1
                    return
                try:
                    payload = await reader.readexactly(declared)
                except asyncio.IncompleteReadError:
                    self._events_rejected += 1
                    return
                self._frames_received += 1
                self._accept_payload(payload)
        finally:
            self._clients.discard(writer)
            if task is not None:
                self._tasks.discard(task)
            writer.close()
            try:
                await writer.wait_closed()
            except (ConnectionError, OSError):
                pass
