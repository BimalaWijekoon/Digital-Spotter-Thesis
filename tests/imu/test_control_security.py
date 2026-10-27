from __future__ import annotations

import os

import msgpack
import pytest

from digital_spotter.imu.control import (
    AuthenticatedCommand,
    AuthenticatedResponse,
    CommandReplayGuard,
    ControlProtocolError,
    decode_command,
    decode_response,
    derive_session_key,
    encode_command,
    encode_response,
    load_device_key,
    require_fresh_sensor_window,
    sensor_window,
)


DEVICE_KEY = bytes(range(32))
SESSION_NONCE = bytes(range(16))


def test_command_golden_vector_round_trip_and_tamper_rejection():
    command = AuthenticatedCommand(
        command_id=0x0102030405060708,
        command="authenticate",
        session_nonce=SESSION_NONCE,
        issued_sensor_window=None,
        arguments={"boot_id": 0x1112131415161718},
    )
    encoded = encode_command(command, key=DEVICE_KEY)

    assert encoded.hex() == (
        "87b070726f746f636f6c5f76657273696f6e01aa636f6d6d616e645f6964"
        "cf0102030405060708a7636f6d6d616e64ac61757468656e746963617465"
        "ad73657373696f6e5f6e6f6e6365c410000102030405060708090a0b0c0d"
        "0e0fb46973737565645f73656e736f725f77696e646f77c0a9617267756d"
        "656e747381a7626f6f745f6964cf1112131415161718a8617574685f7461"
        "67c41055cbe8a2f6a2df32a1f4d8cc99559da9"
    )
    assert decode_command(encoded, key=DEVICE_KEY) == command

    tampered = bytearray(encoded)
    tampered[-1] ^= 1
    with pytest.raises(ControlProtocolError, match="authentication"):
        decode_command(bytes(tampered), key=DEVICE_KEY)


def test_noncanonical_command_key_order_and_integer_encoding_are_rejected():
    command = AuthenticatedCommand(1, "status", SESSION_NONCE, 2, {})
    canonical = encode_command(command, key=DEVICE_KEY)
    decoded = msgpack.unpackb(canonical, raw=False)
    reordered = {
        "command_id": decoded["command_id"],
        "protocol_version": decoded["protocol_version"],
        **{key: value for key, value in decoded.items() if key not in {"command_id", "protocol_version"}},
    }
    with pytest.raises(ControlProtocolError, match="canonical order"):
        decode_command(msgpack.packb(reordered, use_bin_type=True), key=DEVICE_KEY)


def test_authenticated_response_and_session_derivation_are_deterministic():
    response = AuthenticatedResponse(
        command_id=7,
        result="accepted",
        session_nonce=SESSION_NONCE,
        arguments={"boot_id": 9, "sensor_time_us": 25_000_000},
    )
    encoded = encode_response(response, key=DEVICE_KEY)
    assert decode_response(encoded, key=DEVICE_KEY) == response
    first = derive_session_key(
        device_key=DEVICE_KEY,
        session_nonce=SESSION_NONCE,
        device_id="ds-imu-001122334455",
        boot_id=9,
    )
    second = derive_session_key(
        device_key=DEVICE_KEY,
        session_nonce=SESSION_NONCE,
        device_id="ds-imu-001122334455",
        boot_id=9,
    )
    changed = derive_session_key(
        device_key=DEVICE_KEY,
        session_nonce=SESSION_NONCE,
        device_id="ds-imu-001122334455",
        boot_id=10,
    )
    assert len(first) == 32
    assert first == second
    assert first != changed


def test_sensor_freshness_and_bounded_replay_policy():
    assert sensor_window(25_000_000) == 5
    require_fresh_sensor_window(5, sensor_time_us=25_000_000)
    require_fresh_sensor_window(4, sensor_time_us=25_000_000)
    with pytest.raises(ControlProtocolError, match="stale"):
        require_fresh_sensor_window(3, sensor_time_us=25_000_000)

    guard = CommandReplayGuard(max_entries=16)
    guard.check_and_record(7)
    with pytest.raises(ControlProtocolError, match="replayed"):
        guard.check_and_record(7)
    for command_id in range(8, 24):
        guard.check_and_record(command_id)
    guard.check_and_record(7)  # oldest entry was evicted; memory remains bounded


def test_device_key_file_is_exact_owner_only_binary(tmp_path):
    key_path = tmp_path / "wearable.key"
    key_path.write_bytes(DEVICE_KEY)
    key_path.chmod(0o600)
    assert load_device_key(key_path) == DEVICE_KEY

    key_path.chmod(0o640)
    with pytest.raises(ValueError, match="permissions"):
        load_device_key(key_path)
    key_path.chmod(0o600)
    key_path.write_bytes(os.urandom(31))
    with pytest.raises(ValueError, match="exactly 32"):
        load_device_key(key_path)
    key_path.write_bytes(bytes(32))
    with pytest.raises(ValueError, match="all zero"):
        load_device_key(key_path)

    target = tmp_path / "target.key"
    target.write_bytes(DEVICE_KEY)
    target.chmod(0o600)
    link = tmp_path / "link.key"
    link.symlink_to(target)
    with pytest.raises(ValueError, match="non-symlink"):
        load_device_key(link)


@pytest.mark.parametrize(
    "command",
    [
        AuthenticatedCommand(1, "unknown", SESSION_NONCE, 0, {}),
        AuthenticatedCommand(1, "status", b"short", 0, {}),
        AuthenticatedCommand(1, "status", SESSION_NONCE, None, {"nested": {"bad": 1}}),
        AuthenticatedCommand(1, "status", SESSION_NONCE, 0, {"label": "not-ascii-\u2603"}),
    ],
)
def test_invalid_commands_fail_closed(command):
    with pytest.raises(ControlProtocolError):
        encode_command(command, key=DEVICE_KEY)


@pytest.mark.parametrize(
    "arguments",
    [{}, {"cue": "warning"}, {"cue": "good", "duration_ms": 100}],
)
def test_feedback_command_schema_fails_closed(arguments):
    with pytest.raises(ControlProtocolError, match="feedback"):
        encode_command(
            AuthenticatedCommand(2, "feedback", SESSION_NONCE, 1, arguments),
            key=DEVICE_KEY,
        )


def test_feedback_command_has_canonical_authenticated_vector():
    command = AuthenticatedCommand(2, "feedback", SESSION_NONCE, 1, {"cue": "bad"})
    encoded = encode_command(command, key=DEVICE_KEY)

    assert decode_command(encoded, key=DEVICE_KEY) == command
    assert encoded.hex() == (
        "87b070726f746f636f6c5f76657273696f6e01aa636f6d6d616e645f696402"
        "a7636f6d6d616e64a8666565646261636bad73657373696f6e5f6e6f6e6365"
        "c410000102030405060708090a0b0c0d0e0fb46973737565645f73656e736f"
        "725f77696e646f7701a9617267756d656e747381a3637565a3626164a86175"
        "74685f746167c410e1ad135a42f69a99ca97121ca4c440ef"
    )
