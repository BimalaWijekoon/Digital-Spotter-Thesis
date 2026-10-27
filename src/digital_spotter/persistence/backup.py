"""Online SQLite backup and fail-closed restore helpers."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4


MAX_MANIFEST_BYTES = 64 * 1024
COUNTED_TABLES = (
    "sessions",
    "session_imu_summaries",
    "reps",
    "analysis_events",
    "outbox",
)


class BackupError(RuntimeError):
    """Raised when backup or restore integrity cannot be established."""


@dataclass(frozen=True)
class DatabaseSnapshot:
    database_path: Path
    sha256: str
    size_bytes: int
    schema_version: int
    counts: dict[str, int]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _inspect(path: Path) -> DatabaseSnapshot:
    try:
        uri = f"file:{path.resolve().as_posix()}?mode=ro"
        with sqlite3.connect(uri, uri=True) as connection:
            if connection.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                raise BackupError("database quick_check failed")
            tables = {
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                )
            }
            counts = {
                table: connection.execute(f'SELECT count(*) FROM "{table}"').fetchone()[0]
                for table in COUNTED_TABLES
                if table in tables
            }
            schema_version = 0
            if "schema_migrations" in tables:
                schema_version = int(
                    connection.execute("SELECT max(version) FROM schema_migrations").fetchone()[0]
                    or 0
                )
    except sqlite3.Error as exc:
        raise BackupError(f"cannot inspect database: {exc}") from exc
    return DatabaseSnapshot(
        database_path=path.resolve(),
        sha256=_sha256(path),
        size_bytes=path.stat().st_size,
        schema_version=schema_version,
        counts=counts,
    )


def _manifest_path(backup_path: Path) -> Path:
    return backup_path.with_suffix(backup_path.suffix + ".manifest.json")


def backup_database(source_path: Path, backup_path: Path) -> DatabaseSnapshot:
    source_path = source_path.resolve()
    backup_path = backup_path.resolve()
    if not source_path.is_file():
        raise BackupError(f"database not found: {source_path}")
    if backup_path.exists() or _manifest_path(backup_path).exists():
        raise BackupError("backup target already exists")
    backup_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        source_uri = f"file:{source_path.as_posix()}?mode=ro"
        with sqlite3.connect(source_uri, uri=True) as source:
            if source.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                raise BackupError("source database quick_check failed")
            with sqlite3.connect(backup_path) as destination:
                source.backup(destination)
    except (sqlite3.Error, OSError) as exc:
        if backup_path.exists():
            backup_path.unlink()
        raise BackupError(f"online backup failed: {exc}") from exc

    snapshot = _inspect(backup_path)
    manifest = {
        "schema_version": 1,
        "database_sha256": snapshot.sha256,
        "database_size_bytes": snapshot.size_bytes,
        "database_schema_version": snapshot.schema_version,
        "counts": snapshot.counts,
    }
    manifest_path = _manifest_path(backup_path)
    manifest_path.write_text(
        json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    return snapshot


def restore_database(backup_path: Path, target_path: Path) -> DatabaseSnapshot:
    backup_path = backup_path.resolve()
    target_path = target_path.resolve()
    manifest_path = _manifest_path(backup_path)
    if target_path.exists():
        raise BackupError("restore target already exists")
    if not backup_path.is_file() or not manifest_path.is_file():
        raise BackupError("backup or manifest not found")
    if manifest_path.stat().st_size > MAX_MANIFEST_BYTES:
        raise BackupError("backup manifest is oversized")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise BackupError(f"invalid backup manifest: {exc}") from exc
    if manifest.get("schema_version") != 1:
        raise BackupError("unsupported backup manifest schema")
    backup_snapshot = _inspect(backup_path)
    if (
        backup_snapshot.sha256 != manifest.get("database_sha256")
        or backup_snapshot.size_bytes != manifest.get("database_size_bytes")
        or backup_snapshot.schema_version != manifest.get("database_schema_version")
        or backup_snapshot.counts != manifest.get("counts")
    ):
        raise BackupError("backup does not match its manifest")

    target_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = target_path.with_name(f".{target_path.name}.restore-{uuid4().hex}")
    try:
        source_uri = f"file:{backup_path.as_posix()}?mode=ro"
        with sqlite3.connect(source_uri, uri=True) as source:
            with sqlite3.connect(temporary) as destination:
                source.backup(destination)
        restored = _inspect(temporary)
        if (
            restored.schema_version != backup_snapshot.schema_version
            or restored.counts != backup_snapshot.counts
        ):
            raise BackupError("restored database does not preserve schema/counts")
        os.replace(temporary, target_path)
        return _inspect(target_path)
    except Exception:
        if temporary.exists():
            temporary.unlink()
        raise
