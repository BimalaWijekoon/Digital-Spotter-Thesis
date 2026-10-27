from __future__ import annotations

import os
import socket
import struct
import threading
import time
from pathlib import Path

import pytest

from digital_spotter.contracts import (
    ComponentState,
    EventEnvelope,
    HealthState,
    MAX_EVENT_BYTES,
    ReasonCode,
    new_event_id,
)
from digital_spotter.imu.uds import decode_event_frame, encode_event_frame
from digital_spotter.vision import (
    BoundedVisionEventPublisher,
    UnixVisionEventTransport,
    VisionHealthSnapshot,
    VisionUDSError,
    build_vision_health_envelope,
)


def _health_event(sequence: int) -> EventEnvelope[HealthState]:
    return build_vision_health_envelope(
        snapshot=VisionHealthSnapshot(
            state=ComponentState.READY,
            reason_codes=(ReasonCode.OK,),
            since_monotonic_ns=1_000,
            last_success_monotonic_ns=1_000 + sequence,
            counters={"sequence": sequence},
            is_simulated=False,
        ),
        event_id=new_event_id(
            unix_time_ms=1_750_000_000_000,
            random_bits=sequence,
        ),
        created_monotonic_ns=1_000 + sequence,
        device_id="pi-camera-001",
    )


def _wait_until(predicate, *, timeout_s: float = 2.0) -> None:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.005)
    pytest.fail("timed out waiting for publisher state")


def _receive_frame(peer: socket.socket) -> bytes:
    prefix = b""
    while len(prefix) < 4:
        chunk = peer.recv(4 - len(prefix))
        if not chunk:
            raise AssertionError("peer closed before the frame prefix arrived")
        prefix += chunk
    length = struct.unpack(">I", prefix)[0]
    payload = b""
    while len(payload) < length:
        chunk = peer.recv(length - len(payload))
        if not chunk:
            raise AssertionError("peer closed before the frame payload arrived")
        payload += chunk
    return prefix + payload


class _BlockingTransport:
    def __init__(self) -> None:
        self.frames: list[bytes] = []
        self.first_send_entered = threading.Event()
        self.release_first_send = threading.Event()
        self.closed = False

    def send(self, frame: bytes) -> None:
        self.frames.append(frame)
        if len(self.frames) == 1:
            self.first_send_entered.set()
            if not self.release_first_send.wait(timeout=2.0):
                raise TimeoutError("test did not release blocked transport")

    def close(self) -> None:
        self.closed = True


class _FailOnceTransport:
    def __init__(self) -> None:
        self.attempts = 0
        self.frames: list[bytes] = []
        self.close_calls = 0

    def send(self, frame: bytes) -> None:
        self.attempts += 1
        if self.attempts == 1:
            raise ConnectionError("injected first-send failure")
        self.frames.append(frame)

    def close(self) -> None:
        self.close_calls += 1


def test_unix_transport_sends_one_bounded_frame_to_restricted_local_peer(tmp_path):
    socket_path = tmp_path / "vision.sock"
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(str(socket_path))
    os.chmod(socket_path, 0o600)
    server.listen(1)
    transport = UnixVisionEventTransport(
        socket_path,
        allowed_peer_uids=frozenset({os.getuid()}),
    )
    event = _health_event(1)

    try:
        transport.send(encode_event_frame(event))
        peer, _ = server.accept()
        with peer:
            frame = _receive_frame(peer)
    finally:
        transport.close()
        server.close()

    assert decode_event_frame(frame, EventEnvelope[HealthState]) == event


def test_unix_transport_rejects_non_socket_and_world_accessible_socket(tmp_path):
    non_socket = tmp_path / "not-a-socket"
    non_socket.write_text("not a socket", encoding="utf-8")
    with pytest.raises(VisionUDSError, match="not a Unix socket"):
        UnixVisionEventTransport(non_socket).send(encode_event_frame(_health_event(1)))

    socket_path = tmp_path / "world.sock"
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(str(socket_path))
    os.chmod(socket_path, 0o606)
    server.listen(1)
    try:
        with pytest.raises(PermissionError, match="other users"):
            UnixVisionEventTransport(socket_path).send(
                encode_event_frame(_health_event(2))
            )
    finally:
        server.close()


def test_unix_transport_rejects_unapproved_peer_uid(tmp_path):
    if not hasattr(socket, "SO_PEERCRED"):
        pytest.skip("Linux SO_PEERCRED is required by the target runtime")
    socket_path = tmp_path / "wrong-peer.sock"
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(str(socket_path))
    os.chmod(socket_path, 0o600)
    server.listen(1)
    transport = UnixVisionEventTransport(
        socket_path,
        allowed_peer_uids=frozenset({os.getuid() + 1}),
    )
    try:
        with pytest.raises(PermissionError, match="peer UID"):
            transport.send(encode_event_frame(_health_event(3)))
    finally:
        transport.close()
        server.close()


@pytest.mark.parametrize(
    "frame",
    (
        b"",
        b"\x00\x00\x00\x01",
        struct.pack(">I", 0) + b"x",
        struct.pack(">I", MAX_EVENT_BYTES + 1) + b"x",
        struct.pack(">I", 2) + b"x",
    ),
)
def test_unix_transport_rejects_invalid_frames_before_connect(tmp_path, frame):
    transport = UnixVisionEventTransport(tmp_path / "absent.sock")

    with pytest.raises(VisionUDSError):
        transport.send(frame)


def test_publisher_is_bounded_and_drops_oldest_queued_event():
    transport = _BlockingTransport()
    publisher = BoundedVisionEventPublisher(
        transport=transport,
        queue_size=1,
        reconnect_backoff_s=(0.0,),
    )
    publisher.start()
    publisher.publish(_health_event(1))
    assert transport.first_send_entered.wait(timeout=1.0)

    publisher.publish(_health_event(2))
    publisher.publish(_health_event(3))
    transport.release_first_send.set()
    _wait_until(lambda: publisher.counters().events_sent == 2)
    publisher.close()

    sent_sequences = [
        decode_event_frame(frame, EventEnvelope[HealthState]).payload.counters[
            "sequence"
        ]
        for frame in transport.frames
    ]
    assert sent_sequences == [1, 3]
    assert publisher.counters().events_enqueued == 3
    assert publisher.counters().queue_drops == 1
    assert publisher.counters().transport_drops == 0
    assert transport.closed is True


def test_publisher_records_failed_frame_and_reconnects_for_next_event():
    transport = _FailOnceTransport()
    publisher = BoundedVisionEventPublisher(
        transport=transport,
        queue_size=2,
        reconnect_backoff_s=(0.0,),
    )
    publisher.start()
    publisher.publish(_health_event(1))
    _wait_until(lambda: publisher.counters().transport_failures == 1)

    publisher.publish(_health_event(2))
    _wait_until(lambda: publisher.counters().events_sent == 1)
    publisher.close()

    sent = decode_event_frame(transport.frames[0], EventEnvelope[HealthState])
    assert sent.payload.counters["sequence"] == 2
    assert publisher.counters().transport_drops == 1
    assert transport.close_calls >= 2
