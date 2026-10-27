"""Canonical authenticated BLE control protocol shared with the wearable contract."""

from __future__ import annotations

import hashlib
import hmac
import os
import stat
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Final

import msgpack


PROTOCOL_VERSION: Final = 1
MAX_CONTROL_BYTES: Final = 512
DEVICE_KEY_BYTES: Final = 32
SESSION_NONCE_BYTES: Final = 16
AUTH_TAG_BYTES: Final = 16
SENSOR_WINDOW_US: Final = 5_000_000
MAX_SENSOR_WINDOW: Final = 0xFFFFFFFF // SENSOR_WINDOW_US

COMMAND_DOMAIN: Final = b"DS-BLE-CMD-V1\x00"
RESPONSE_DOMAIN: Final = b"DS-BLE-RSP-V1\x00"
SESSION_INFO_DOMAIN: Final = b"DS-BLE-SESSION-V1\x00"

COMMANDS: Final = frozenset(
    {
        "authenticate",
        "start",
        "stop",
        "calibrate",
        "time_sync",
        "set_rate",
        "identify",
        "feedback",
        "sleep",
        "status",
    }
)
RESULTS: Final = frozenset(
    {
        "accepted",
        "already_applied",
        "unauthorized",
        "replayed",
        "stale",
        "rate_limited",
        "invalid",
        "unsupported",
        "internal_error",
    }
)

_COMMAND_KEYS: Final = (
    "protocol_version",
    "command_id",
    "command",
    "session_nonce",
    "issued_sensor_window",
    "arguments",
    "auth_tag",
)
_RESPONSE_KEYS: Final = (
    "protocol_version",
    "command_id",
    "result",
    "session_nonce",
    "arguments",
    "auth_tag",
)


class ControlProtocolError(ValueError):
    """The control payload is malformed, non-canonical, stale, or unauthenticated."""


@dataclass(frozen=True)
class AuthenticatedCommand:
    command_id: int
    command: str
    session_nonce: bytes
    issued_sensor_window: int | None
    arguments: dict[str, int | str | bytes | None]


@dataclass(frozen=True)
class AuthenticatedResponse:
    command_id: int
    result: str
    session_nonce: bytes
    arguments: dict[str, int | str | bytes | None]


def _u64(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 0xFFFFFFFFFFFFFFFF:
        raise ControlProtocolError(f"{name} must be an unsigned 64-bit integer")
    return value


def _fixed_bytes(value: object, size: int, name: str) -> bytes:
    if not isinstance(value, bytes) or len(value) != size:
        raise ControlProtocolError(f"{name} must be exactly {size} bytes")
    return value


def _key(value: bytes) -> bytes:
    if not isinstance(value, bytes) or len(value) != DEVICE_KEY_BYTES:
        raise ControlProtocolError("authentication key must be exactly 32 bytes")
    if not any(value):
        raise ControlProtocolError("authentication key must not be all zero")
    return value


def _arguments(value: object) -> dict[str, int | str | bytes | None]:
    if not isinstance(value, dict) or len(value) > 8:
        raise ControlProtocolError("arguments must be a map with at most 8 entries")
    keys = list(value)
    if any(
        not isinstance(key, str)
        or not key
        or len(key) > 32
        or not key.isascii()
        for key in keys
    ):
        raise ControlProtocolError("argument keys must be 1-32 character strings")
    if keys != sorted(keys):
        raise ControlProtocolError("argument keys are not in canonical order")
    output: dict[str, int | str | bytes | None] = {}
    for name, item in value.items():
        if item is None:
            output[name] = None
        elif isinstance(item, bool):
            raise ControlProtocolError(f"argument {name} has an unsupported boolean value")
        elif isinstance(item, int):
            output[name] = _u64(item, f"argument {name}")
        elif isinstance(item, str) and len(item) <= 64 and item.isascii():
            output[name] = item
        elif isinstance(item, bytes) and len(item) <= 64:
            output[name] = item
        else:
            raise ControlProtocolError(f"argument {name} has an unsupported value")
    return output


def _unpack(encoded: bytes) -> dict:
    if not isinstance(encoded, bytes) or not encoded or len(encoded) > MAX_CONTROL_BYTES:
        raise ControlProtocolError("control payload length is invalid")
    try:
        value = msgpack.unpackb(
            encoded,
            raw=False,
            strict_map_key=True,
            max_map_len=8,
            max_array_len=0,
            max_str_len=64,
            max_bin_len=64,
            max_ext_len=0,
        )
    except (ValueError, TypeError, msgpack.ExtraData, msgpack.FormatError, msgpack.StackError) as exc:
        raise ControlProtocolError("control payload is not valid bounded MessagePack") from exc
    if not isinstance(value, dict):
        raise ControlProtocolError("control payload must be a map")
    return value


def _command_signing_bytes(command: AuthenticatedCommand) -> bytes:
    return msgpack.packb(
        {
            "protocol_version": PROTOCOL_VERSION,
            "command_id": command.command_id,
            "command": command.command,
            "session_nonce": command.session_nonce,
            "issued_sensor_window": command.issued_sensor_window,
            "arguments": command.arguments,
        },
        use_bin_type=True,
    )


def _response_signing_bytes(response: AuthenticatedResponse) -> bytes:
    return msgpack.packb(
        {
            "protocol_version": PROTOCOL_VERSION,
            "command_id": response.command_id,
            "result": response.result,
            "session_nonce": response.session_nonce,
            "arguments": response.arguments,
        },
        use_bin_type=True,
    )


def _tag(key: bytes, domain: bytes, signing_bytes: bytes) -> bytes:
    return hmac.new(_key(key), domain + signing_bytes, hashlib.sha256).digest()[:AUTH_TAG_BYTES]


def encode_command(command: AuthenticatedCommand, *, key: bytes) -> bytes:
    validated = _validate_command(command)
    tag = _tag(key, COMMAND_DOMAIN, _command_signing_bytes(validated))
    encoded = msgpack.packb(
        {
            "protocol_version": PROTOCOL_VERSION,
            "command_id": validated.command_id,
            "command": validated.command,
            "session_nonce": validated.session_nonce,
            "issued_sensor_window": validated.issued_sensor_window,
            "arguments": validated.arguments,
            "auth_tag": tag,
        },
        use_bin_type=True,
    )
    if len(encoded) > MAX_CONTROL_BYTES:
        raise ControlProtocolError("encoded command exceeds 512 bytes")
    return encoded


def decode_command(encoded: bytes, *, key: bytes) -> AuthenticatedCommand:
    value = _unpack(encoded)
    if tuple(value) != _COMMAND_KEYS:
        raise ControlProtocolError("command fields are missing, extra, or out of canonical order")
    if value["protocol_version"] != PROTOCOL_VERSION:
        raise ControlProtocolError("unsupported control protocol version")
    command = _validate_command(
        AuthenticatedCommand(
            command_id=_u64(value["command_id"], "command_id"),
            command=value["command"],
            session_nonce=_fixed_bytes(value["session_nonce"], SESSION_NONCE_BYTES, "session_nonce"),
            issued_sensor_window=value["issued_sensor_window"],
            arguments=_arguments(value["arguments"]),
        )
    )
    supplied_tag = _fixed_bytes(value["auth_tag"], AUTH_TAG_BYTES, "auth_tag")
    expected_tag = _tag(key, COMMAND_DOMAIN, _command_signing_bytes(command))
    if not hmac.compare_digest(supplied_tag, expected_tag):
        raise ControlProtocolError("command authentication failed")
    if not hmac.compare_digest(encoded, encode_command(command, key=key)):
        raise ControlProtocolError("command is not canonical MessagePack")
    return command


def _validate_command(command: AuthenticatedCommand) -> AuthenticatedCommand:
    command_id = _u64(command.command_id, "command_id")
    if not isinstance(command.command, str) or command.command not in COMMANDS:
        raise ControlProtocolError("command is unsupported")
    nonce = _fixed_bytes(command.session_nonce, SESSION_NONCE_BYTES, "session_nonce")
    window = command.issued_sensor_window
    if window is not None:
        window = _u64(window, "issued_sensor_window")
        if window > MAX_SENSOR_WINDOW:
            raise ControlProtocolError("issued_sensor_window is outside the sensor counter range")
    arguments = _arguments(command.arguments)
    if command.command == "identify" and arguments:
        raise ControlProtocolError("identify command does not accept arguments")
    if command.command == "feedback":
        if tuple(arguments) != ("cue",) or arguments["cue"] not in {"good", "bad"}:
            raise ControlProtocolError("feedback command requires cue=good or cue=bad")
    return AuthenticatedCommand(command_id, command.command, nonce, window, arguments)


def encode_response(response: AuthenticatedResponse, *, key: bytes) -> bytes:
    validated = _validate_response(response)
    tag = _tag(key, RESPONSE_DOMAIN, _response_signing_bytes(validated))
    encoded = msgpack.packb(
        {
            "protocol_version": PROTOCOL_VERSION,
            "command_id": validated.command_id,
            "result": validated.result,
            "session_nonce": validated.session_nonce,
            "arguments": validated.arguments,
            "auth_tag": tag,
        },
        use_bin_type=True,
    )
    if len(encoded) > MAX_CONTROL_BYTES:
        raise ControlProtocolError("encoded response exceeds 512 bytes")
    return encoded


def decode_response(encoded: bytes, *, key: bytes) -> AuthenticatedResponse:
    value = _unpack(encoded)
    if tuple(value) != _RESPONSE_KEYS:
        raise ControlProtocolError("response fields are missing, extra, or out of canonical order")
    if value["protocol_version"] != PROTOCOL_VERSION:
        raise ControlProtocolError("unsupported control protocol version")
    response = _validate_response(
        AuthenticatedResponse(
            command_id=_u64(value["command_id"], "command_id"),
            result=value["result"],
            session_nonce=_fixed_bytes(value["session_nonce"], SESSION_NONCE_BYTES, "session_nonce"),
            arguments=_arguments(value["arguments"]),
        )
    )
    supplied_tag = _fixed_bytes(value["auth_tag"], AUTH_TAG_BYTES, "auth_tag")
    expected_tag = _tag(key, RESPONSE_DOMAIN, _response_signing_bytes(response))
    if not hmac.compare_digest(supplied_tag, expected_tag):
        raise ControlProtocolError("response authentication failed")
    if not hmac.compare_digest(encoded, encode_response(response, key=key)):
        raise ControlProtocolError("response is not canonical MessagePack")
    return response


def _validate_response(response: AuthenticatedResponse) -> AuthenticatedResponse:
    command_id = _u64(response.command_id, "command_id")
    if not isinstance(response.result, str) or response.result not in RESULTS:
        raise ControlProtocolError("response result is unsupported")
    nonce = _fixed_bytes(response.session_nonce, SESSION_NONCE_BYTES, "session_nonce")
    arguments = _arguments(response.arguments)
    return AuthenticatedResponse(command_id, response.result, nonce, arguments)


def derive_session_key(*, device_key: bytes, session_nonce: bytes, device_id: str, boot_id: int) -> bytes:
    """HKDF-SHA-256 for a session bound to one device identity and boot."""

    key = _key(device_key)
    nonce = _fixed_bytes(session_nonce, SESSION_NONCE_BYTES, "session_nonce")
    boot = _u64(boot_id, "boot_id")
    if not isinstance(device_id, str) or not device_id or len(device_id) > 64:
        raise ControlProtocolError("device_id is invalid for session derivation")
    try:
        encoded_id = device_id.encode("ascii")
    except UnicodeEncodeError as exc:
        raise ControlProtocolError("device_id must be ASCII") from exc
    pseudorandom_key = hmac.new(nonce, key, hashlib.sha256).digest()
    info = SESSION_INFO_DOMAIN + encoded_id + boot.to_bytes(8, "big")
    return hmac.new(pseudorandom_key, info + b"\x01", hashlib.sha256).digest()


def sensor_window(sensor_time_us: int) -> int:
    value = _u64(sensor_time_us, "sensor_time_us")
    if value > 0xFFFFFFFF:
        raise ControlProtocolError("sensor_time_us is outside u32")
    return value // SENSOR_WINDOW_US


def require_fresh_sensor_window(issued: int | None, *, sensor_time_us: int) -> None:
    if issued is None:
        raise ControlProtocolError("authenticated command has no sensor freshness window")
    current = sensor_window(sensor_time_us)
    previous = MAX_SENSOR_WINDOW if current == 0 else current - 1
    if issued not in (current, previous):
        raise ControlProtocolError("authenticated command is stale")


class CommandReplayGuard:
    """Bounded per-boot command-ID replay cache."""

    def __init__(self, max_entries: int = 128):
        if not 16 <= max_entries <= 1024:
            raise ValueError("replay cache size must be between 16 and 1024")
        self._order: deque[int] = deque()
        self._seen: set[int] = set()
        self._max_entries = max_entries

    def check_and_record(self, command_id: int) -> None:
        value = _u64(command_id, "command_id")
        if value in self._seen:
            raise ControlProtocolError("command_id was replayed")
        if len(self._order) == self._max_entries:
            self._seen.remove(self._order.popleft())
        self._order.append(value)
        self._seen.add(value)

    def clear(self) -> None:
        self._order.clear()
        self._seen.clear()


def load_device_key(path: Path) -> bytes:
    """Load an owner-only raw 32-byte per-device key without following symlinks."""

    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise ValueError("wearable key must be a readable regular non-symlink file") from exc
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise ValueError("wearable key must be a regular file")
        if metadata.st_mode & (stat.S_IRWXG | stat.S_IRWXO):
            raise ValueError("wearable key permissions must not grant group or other access")
        if hasattr(os, "geteuid") and metadata.st_uid != os.geteuid():
            raise ValueError("wearable key must be owned by the service user")
        if metadata.st_size != DEVICE_KEY_BYTES:
            raise ValueError("wearable key must contain exactly 32 raw bytes")
        value = b""
        while len(value) < DEVICE_KEY_BYTES:
            chunk = os.read(descriptor, DEVICE_KEY_BYTES - len(value))
            if not chunk:
                break
            value += chunk
    except OSError as exc:
        raise ValueError(f"cannot read wearable key: {exc}") from exc
    finally:
        os.close(descriptor)
    if len(value) != DEVICE_KEY_BYTES:
        raise ValueError("wearable key must contain exactly 32 raw bytes")
    if not any(value):
        raise ValueError("wearable key must not be all zero")
    return value
