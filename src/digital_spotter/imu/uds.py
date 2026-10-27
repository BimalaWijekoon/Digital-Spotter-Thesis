"""Bounded length-prefixed UDS framing for IMU-to-core event delivery."""

from __future__ import annotations

import asyncio
import struct
from pathlib import Path

from digital_spotter.contracts import EventEnvelope, MAX_EVENT_BYTES


class UDSFrameError(ValueError):
    pass


def encode_event_frame(envelope: EventEnvelope) -> bytes:
    payload = envelope.to_messagepack()
    return struct.pack(">I", len(payload)) + payload


def decode_event_frame(frame: bytes, envelope_type) -> EventEnvelope:
    if not isinstance(frame, bytes) or len(frame) < 5:
        raise UDSFrameError("UDS frame is truncated")
    declared = struct.unpack(">I", frame[:4])[0]
    if declared == 0 or declared > MAX_EVENT_BYTES:
        raise UDSFrameError("UDS frame length is invalid")
    if len(frame) != 4 + declared:
        raise UDSFrameError("UDS frame length does not match payload")
    return envelope_type.from_messagepack(frame[4:])


class UnixEventPublisher:
    """Serialize writes and reconnect without buffering an unbounded backlog."""

    def __init__(self, socket_path: Path):
        self.socket_path = socket_path
        self._writer: asyncio.StreamWriter | None = None
        self._lock = asyncio.Lock()

    async def _connect(self) -> asyncio.StreamWriter:
        if self._writer is None or self._writer.is_closing():
            _, self._writer = await asyncio.open_unix_connection(self.socket_path)
        return self._writer

    async def send(self, envelope: EventEnvelope) -> None:
        frame = encode_event_frame(envelope)
        async with self._lock:
            try:
                writer = await self._connect()
                writer.write(frame)
                await writer.drain()
            except (ConnectionError, OSError):
                await self.close()
                raise

    async def close(self) -> None:
        writer, self._writer = self._writer, None
        if writer is not None:
            writer.close()
            try:
                await writer.wait_closed()
            except (ConnectionError, OSError):
                pass
