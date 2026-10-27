"""Strict one-time wearable claim import for trusted Pi provisioning."""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import os
import re
import secrets
import stat
from dataclasses import dataclass
from pathlib import Path

import msgpack

from digital_spotter.imu.control import DEVICE_KEY_BYTES


CLAIM_PREFIX = "DSIMU1:"
CLAIM_NONCE_BYTES = 16
MAX_CLAIM_TEXT_BYTES = 1024
_CLAIM_KEYS = ("version", "device_id", "device_key", "claim_nonce", "claim_tag")
_DEVICE_ID = re.compile(r"dsimu-[0-9a-f]{12}\Z")
_CLAIM_DOMAIN = b"DS-WEARABLE-CLAIM-V1\x00"
_CLAIM_TAG_BYTES = 16


class ProvisioningError(ValueError):
    """A claim or destination violates the one-time provisioning contract."""


@dataclass(frozen=True)
class WearableClaim:
    device_id: str
    device_key: bytes
    claim_nonce: bytes


@dataclass(frozen=True)
class ProvisioningReceipt:
    device_id: str
    identity_directory: Path
    claim_fingerprint: str


@dataclass(frozen=True)
class ClaimIssueReceipt:
    device_id: str
    bundle_directory: Path
    claim_fingerprint: str


def encode_claim(claim: WearableClaim) -> str:
    """Encode manufacturing/onboarding data for a confidential QR artifact."""

    validated = _validate_claim(claim)
    claim_tag = _claim_tag(validated)
    payload = msgpack.packb(
        {
            "version": 1,
            "device_id": validated.device_id,
            "device_key": validated.device_key,
            "claim_nonce": validated.claim_nonce,
            "claim_tag": claim_tag,
        },
        use_bin_type=True,
    )
    token = base64.urlsafe_b64encode(payload).rstrip(b"=").decode("ascii")
    return CLAIM_PREFIX + token


def decode_claim(text: str) -> WearableClaim:
    if not isinstance(text, str):
        raise ProvisioningError("wearable claim must be text")
    value = text.strip()
    if len(value.encode("utf-8")) > MAX_CLAIM_TEXT_BYTES or not value.startswith(CLAIM_PREFIX):
        raise ProvisioningError("wearable claim prefix or length is invalid")
    encoded = value[len(CLAIM_PREFIX) :]
    if not encoded or any(character.isspace() for character in encoded):
        raise ProvisioningError("wearable claim encoding is invalid")
    padding = "=" * (-len(encoded) % 4)
    try:
        payload = base64.b64decode(encoded + padding, altchars=b"-_", validate=True)
        unpacked = msgpack.unpackb(
            payload,
            raw=False,
            strict_map_key=True,
            max_map_len=5,
            max_str_len=64,
            max_bin_len=DEVICE_KEY_BYTES,
            max_array_len=0,
            max_ext_len=0,
        )
    except (binascii.Error, ValueError, TypeError, msgpack.ExtraData) as exc:
        raise ProvisioningError("wearable claim is not valid bounded data") from exc
    if not isinstance(unpacked, dict) or tuple(unpacked) != _CLAIM_KEYS:
        raise ProvisioningError("wearable claim fields are missing, extra, or reordered")
    if unpacked["version"] != 1:
        raise ProvisioningError("wearable claim version is unsupported")
    claim = _validate_claim(
        WearableClaim(
            device_id=unpacked["device_id"],
            device_key=unpacked["device_key"],
            claim_nonce=unpacked["claim_nonce"],
        )
    )
    supplied_tag = unpacked["claim_tag"]
    if (
        not isinstance(supplied_tag, bytes)
        or len(supplied_tag) != _CLAIM_TAG_BYTES
        or not hmac.compare_digest(supplied_tag, _claim_tag(claim))
    ):
        raise ProvisioningError("wearable claim integrity check failed")
    if encode_claim(claim) != value:
        raise ProvisioningError("wearable claim encoding is not canonical")
    return claim


def _validate_claim(claim: WearableClaim) -> WearableClaim:
    if not isinstance(claim.device_id, str) or _DEVICE_ID.fullmatch(claim.device_id) is None:
        raise ProvisioningError("wearable claim device_id is invalid")
    if not isinstance(claim.device_key, bytes) or len(claim.device_key) != DEVICE_KEY_BYTES:
        raise ProvisioningError("wearable claim key must be exactly 32 bytes")
    if not any(claim.device_key):
        raise ProvisioningError("wearable claim key must not be all zero")
    if not isinstance(claim.claim_nonce, bytes) or len(claim.claim_nonce) != CLAIM_NONCE_BYTES:
        raise ProvisioningError("wearable claim nonce must be exactly 16 bytes")
    return claim


def _claim_tag(claim: WearableClaim) -> bytes:
    transcript = (
        _CLAIM_DOMAIN
        + b"\x01"
        + claim.device_id.encode("ascii")
        + b"\x00"
        + claim.claim_nonce
    )
    return hmac.new(claim.device_key, transcript, hashlib.sha256).digest()[:_CLAIM_TAG_BYTES]


def _secure_directory(path: Path) -> None:
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        path.mkdir(mode=0o700, parents=True)
        metadata = path.lstat()
    if not stat.S_ISDIR(metadata.st_mode) or path.is_symlink():
        raise ProvisioningError("identity destination must be a non-symlink directory")
    if metadata.st_mode & (stat.S_IRWXG | stat.S_IRWXO):
        raise ProvisioningError("identity directory must not grant group or other access")
    if hasattr(os, "geteuid") and metadata.st_uid != os.geteuid():
        raise ProvisioningError("identity directory must be owned by the current user")


def _exclusive_write(path: Path, data: bytes) -> None:
    flags = (
        os.O_WRONLY
        | os.O_CREAT
        | os.O_EXCL
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    descriptor = os.open(path, flags, 0o600)
    try:
        offset = 0
        while offset < len(data):
            offset += os.write(descriptor, data[offset:])
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def issue_claim_bundle(device_id: str, bundle_directory: Path) -> ClaimIssueReceipt:
    """Issue one unique confidential claim and transient ESP-IDF NVS input."""

    claim = _validate_claim(
        WearableClaim(
            device_id=device_id,
            device_key=secrets.token_bytes(DEVICE_KEY_BYTES),
            claim_nonce=secrets.token_bytes(CLAIM_NONCE_BYTES),
        )
    )
    destination = Path(os.path.abspath(bundle_directory))
    _secure_directory(destination)
    claim_text = encode_claim(claim)
    fingerprint = hashlib.sha256(
        claim.claim_nonce + claim.device_id.encode("ascii") + claim.device_key
    ).hexdigest()
    outputs = {
        destination / "wearable.claim": claim_text.encode("ascii") + b"\n",
        destination / "provisioning-nvs.csv": (
            "key,type,encoding,value\n"
            "ds_identity,namespace,,\n"
            f"device_id,data,string,{claim.device_id}\n"
            f"device_key,data,hex2bin,{claim.device_key.hex()}\n"
        ).encode("ascii"),
        destination / "issuance-receipt": (
            f"version=1\ndevice_id={claim.device_id}\nclaim_sha256={fingerprint}\n"
        ).encode("ascii"),
    }
    if any(path.exists() or path.is_symlink() for path in outputs):
        raise ProvisioningError("claim bundle destination is already issued")
    created: list[Path] = []
    try:
        for path, data in outputs.items():
            _exclusive_write(path, data)
            created.append(path)
        directory_fd = os.open(destination, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except OSError as exc:
        for path in reversed(created):
            try:
                path.unlink()
            except OSError:
                pass
        raise ProvisioningError("wearable claim bundle could not be stored atomically") from exc
    return ClaimIssueReceipt(claim.device_id, destination, fingerprint)


def import_claim(text: str, identity_directory: Path) -> ProvisioningReceipt:
    """Claim one wearable without overwriting an existing owner binding."""

    claim = decode_claim(text)
    destination = Path(os.path.abspath(identity_directory))
    _secure_directory(destination)
    outputs = {
        destination / "wearable-device-id": claim.device_id.encode("ascii") + b"\n",
        destination / "wearable-device-key": claim.device_key,
    }
    receipt_path = destination / "wearable-claim-receipt"
    if any(path.exists() or path.is_symlink() for path in (*outputs, receipt_path)):
        raise ProvisioningError("identity destination is already claimed")
    fingerprint = hashlib.sha256(
        claim.claim_nonce + claim.device_id.encode("ascii") + claim.device_key
    ).hexdigest()
    outputs[receipt_path] = (
        f"version=1\ndevice_id={claim.device_id}\nclaim_sha256={fingerprint}\n"
    ).encode("ascii")
    created: list[Path] = []
    try:
        for path, data in outputs.items():
            _exclusive_write(path, data)
            created.append(path)
        directory_fd = os.open(destination, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except (OSError, ProvisioningError) as exc:
        for path in reversed(created):
            try:
                path.unlink()
            except OSError:
                pass
        raise ProvisioningError("wearable claim could not be stored atomically") from exc
    return ProvisioningReceipt(claim.device_id, destination, fingerprint)


def read_confidential_claim_file(path: Path) -> str:
    """Read a bounded owner-only claim without following a symlink."""

    claim_path = Path(path)
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(claim_path, flags)
    except OSError as exc:
        raise ProvisioningError("claim file must be an owner-only regular file") from exc
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise ProvisioningError("claim file must be an owner-only regular file")
        if metadata.st_mode & (stat.S_IRWXG | stat.S_IRWXO):
            raise ProvisioningError("claim file must not grant group or other access")
        if hasattr(os, "geteuid") and metadata.st_uid != os.geteuid():
            raise ProvisioningError("claim file must be owned by the current user")
        if metadata.st_size > MAX_CLAIM_TEXT_BYTES:
            raise ProvisioningError("claim file is too large")
        with os.fdopen(descriptor, "r", encoding="ascii", closefd=False) as stream:
            text = stream.read(MAX_CLAIM_TEXT_BYTES + 1)
        if len(text.encode("ascii")) > MAX_CLAIM_TEXT_BYTES:
            raise ProvisioningError("claim file is too large")
        return text
    except (OSError, UnicodeError) as exc:
        raise ProvisioningError("claim file could not be read safely") from exc
    finally:
        os.close(descriptor)
