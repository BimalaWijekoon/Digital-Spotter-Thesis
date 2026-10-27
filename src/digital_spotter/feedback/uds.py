"""Small same-user Unix-socket bridge from core feedback to the BLE owner."""

from __future__ import annotations

import asyncio
import socket
import stat
import struct
from collections.abc import Awaitable, Callable
from pathlib import Path

from .coordinator import DemoCue


MAX_CUE_LINE_BYTES = 32


class UnixWearableCueServer:
    def __init__(
        self,
        *,
        socket_path: Path,
        on_cue: Callable[[DemoCue], Awaitable[bytes]],
        allowed_uids: frozenset[int] | None = None,
    ) -> None:
        self.socket_path = socket_path.resolve(strict=False)
        self.on_cue = on_cue
        self.allowed_uids = allowed_uids
        self._server: asyncio.AbstractServer | None = None
        self._tasks: set[asyncio.Task] = set()
        self._writers: set[asyncio.StreamWriter] = set()
        self._owned_inode: int | None = None

    async def start(self) -> None:
        if self._server is not None:
            return
        self.socket_path.parent.mkdir(parents=True, exist_ok=True)
        if self.socket_path.exists() or self.socket_path.is_symlink():
            raise FileExistsError(
                f"wearable cue socket already exists: {self.socket_path}"
            )
        self._server = await asyncio.start_unix_server(
            self._handle, path=self.socket_path, limit=MAX_CUE_LINE_BYTES
        )
        self.socket_path.chmod(0o600)
        self._owned_inode = self.socket_path.stat().st_ino

    def _peer_allowed(self, writer: asyncio.StreamWriter) -> bool:
        if self.allowed_uids is None:
            return True
        peer = writer.get_extra_info("socket")
        if peer is None or not hasattr(socket, "SO_PEERCRED"):
            return False
        credentials = peer.getsockopt(
            socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("3i")
        )
        _pid, uid, _gid = struct.unpack("3i", credentials)
        return uid in self.allowed_uids

    async def _handle(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        if not self._peer_allowed(writer):
            writer.close()
            await writer.wait_closed()
            return
        task = asyncio.current_task()
        if task is not None:
            self._tasks.add(task)
        self._writers.add(writer)
        try:
            line = await asyncio.wait_for(reader.readline(), timeout=2.0)
            if not line.endswith(b"\n") or len(line) > MAX_CUE_LINE_BYTES:
                raise ValueError("invalid wearable cue frame")
            try:
                cue = DemoCue(line[:-1].decode("ascii"))
            except (UnicodeDecodeError, ValueError) as exc:
                raise ValueError("unknown wearable cue") from exc
            response = await asyncio.wait_for(self.on_cue(cue), timeout=2.0)
            if not response.startswith(b"ok:demo_") or len(response) > 24:
                raise RuntimeError("invalid wearable acknowledgement")
            writer.write(response + b"\n")
            await writer.drain()
        except Exception as exc:
            message = str(exc).replace("\n", " ")[:48]
            writer.write(f"error:{message}\n".encode("ascii", "replace"))
            try:
                await writer.drain()
            except (ConnectionError, OSError):
                pass
        finally:
            self._writers.discard(writer)
            if task is not None:
                self._tasks.discard(task)
            writer.close()
            try:
                await writer.wait_closed()
            except (ConnectionError, OSError):
                pass

    async def close(self) -> None:
        server, self._server = self._server, None
        if server is not None:
            server.close()
        for writer in tuple(self._writers):
            writer.close()
        tasks = tuple(self._tasks)
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        if server is not None:
            await server.wait_closed()
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
        self._writers.clear()
        self._tasks.clear()
        self._owned_inode = None


class UnixWearableCueClient:
    def __init__(self, socket_path: Path) -> None:
        self.socket_path = socket_path

    async def emit(self, cue: DemoCue) -> None:
        if not isinstance(cue, DemoCue):
            raise ValueError("invalid demo cue")
        reader, writer = await asyncio.wait_for(
            asyncio.open_unix_connection(self.socket_path), timeout=1.0
        )
        try:
            writer.write(cue.value.encode("ascii") + b"\n")
            await writer.drain()
            response = await asyncio.wait_for(reader.readline(), timeout=2.0)
            expected = b"ok:demo_" + (
                b"stop" if cue is DemoCue.COMPLETE else cue.value.encode("ascii")
            ) + b"\n"
            if response != expected:
                raise RuntimeError(
                    "wearable cue failed: "
                    + response.decode("ascii", "replace").strip()
                )
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except (ConnectionError, OSError):
                pass

    async def close(self) -> None:
        return None
