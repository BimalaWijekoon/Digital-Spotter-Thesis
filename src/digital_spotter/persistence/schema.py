"""Transactional, checksum-bound SQLite schema migration runner."""

from __future__ import annotations

import hashlib
import inspect
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Sequence


class MigrationError(RuntimeError):
    """Raised when a database cannot be migrated without losing safety guarantees."""


@dataclass(frozen=True)
class Migration:
    version: int
    name: str
    definition: str
    apply: Callable[[sqlite3.Connection], None]

    @property
    def checksum(self) -> str:
        material = (
            f"{self.version}\n{self.name}\n{self.definition}\n"
            f"{inspect.getsource(self.apply)}"
        ).encode()
        return hashlib.sha256(material).hexdigest()


@dataclass(frozen=True)
class MigrationReport:
    database_path: Path
    previous_version: int
    current_version: int
    applied_versions: tuple[int, ...]
    backup_path: Path | None


def connect_database(path: Path) -> sqlite3.Connection:
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=5.0, isolation_level=None)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA busy_timeout=5000")
    connection.execute("PRAGMA foreign_keys=ON")
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA synchronous=FULL")
    return connection


def add_column_if_missing(
    connection: sqlite3.Connection,
    table: str,
    column: str,
    definition: str,
) -> None:
    if not table.replace("_", "").isalnum() or not column.replace("_", "").isalnum():
        raise MigrationError("unsafe migration identifier")
    columns = {row[1] for row in connection.execute(f'PRAGMA table_info("{table}")')}
    if column not in columns:
        connection.execute(f'ALTER TABLE "{table}" ADD COLUMN "{column}" {definition}')


def _validate_migrations(migrations: Sequence[Migration]) -> None:
    versions = [migration.version for migration in migrations]
    if versions != list(range(1, len(migrations) + 1)):
        raise MigrationError("migration versions must be contiguous and start at 1")
    if len({migration.name for migration in migrations}) != len(migrations):
        raise MigrationError("migration names must be unique")


def _read_applied(connection: sqlite3.Connection) -> dict[int, sqlite3.Row]:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER PRIMARY KEY,
            name TEXT NOT NULL UNIQUE,
            checksum TEXT NOT NULL CHECK (length(checksum) = 64),
            applied_utc_ms INTEGER NOT NULL
        ) STRICT
        """
    )
    return {
        row["version"]: row
        for row in connection.execute(
            "SELECT version, name, checksum, applied_utc_ms FROM schema_migrations"
        )
    }


def _database_needs_migration(path: Path, latest_version: int) -> bool:
    if not path.is_file() or path.stat().st_size == 0:
        return latest_version > 0
    try:
        uri = f"file:{path.resolve().as_posix()}?mode=ro"
        with sqlite3.connect(uri, uri=True) as connection:
            versions = {
                int(row[0])
                for row in connection.execute("SELECT version FROM schema_migrations")
            }
            return versions != set(range(1, latest_version + 1))
    except sqlite3.Error:
        return True


def migrate_database(
    path: Path,
    *,
    backup_dir: Path | None = None,
    migrations: Sequence[Migration] | None = None,
) -> MigrationReport:
    if migrations is None:
        from digital_spotter.persistence.migrations import MIGRATIONS

        migrations = MIGRATIONS
    migrations = tuple(migrations)
    _validate_migrations(migrations)
    latest_version = migrations[-1].version if migrations else 0
    path = path.resolve()
    existing = path.is_file() and path.stat().st_size > 0
    needs_migration = _database_needs_migration(path, latest_version)
    backup_path = None
    if existing and needs_migration:
        if backup_dir is None:
            raise MigrationError("existing database migration requires backup_dir")
        from digital_spotter.persistence.backup import backup_database

        backup_dir = backup_dir.resolve()
        backup_dir.mkdir(parents=True, exist_ok=True)
        stamp = time.time_ns()
        backup_path = backup_dir / f"{path.stem}.pre-migration-{stamp}.sqlite3"
        backup_database(path, backup_path)

    connection = connect_database(path)
    applied_now: list[int] = []
    try:
        applied = _read_applied(connection)
        unknown = sorted(set(applied) - {migration.version for migration in migrations})
        if unknown:
            raise MigrationError(f"database contains unknown migration versions: {unknown}")
        ordered_applied = sorted(applied)
        if ordered_applied and ordered_applied != list(range(1, ordered_applied[-1] + 1)):
            raise MigrationError("applied migrations are not a contiguous prefix")
        previous_version = max(applied, default=0)
        for migration in migrations:
            existing_row = applied.get(migration.version)
            if existing_row is not None:
                if (
                    existing_row["name"] != migration.name
                    or existing_row["checksum"] != migration.checksum
                ):
                    raise MigrationError(
                        f"migration {migration.version} identity/checksum mismatch"
                    )
                continue
            connection.execute("BEGIN IMMEDIATE")
            try:
                migration.apply(connection)
                connection.execute(
                    "INSERT INTO schema_migrations "
                    "(version, name, checksum, applied_utc_ms) VALUES (?, ?, ?, ?)",
                    (
                        migration.version,
                        migration.name,
                        migration.checksum,
                        time.time_ns() // 1_000_000,
                    ),
                )
                connection.commit()
            except Exception:
                connection.rollback()
                raise
            applied_now.append(migration.version)

        quick_check = connection.execute("PRAGMA quick_check").fetchone()[0]
        if quick_check != "ok":
            raise MigrationError(f"database quick_check failed: {quick_check}")
        foreign_key_errors = connection.execute("PRAGMA foreign_key_check").fetchall()
        if foreign_key_errors:
            raise MigrationError("database foreign_key_check failed after migration")
        current_version = max(_read_applied(connection), default=0)
        return MigrationReport(
            database_path=path,
            previous_version=previous_version,
            current_version=current_version,
            applied_versions=tuple(applied_now),
            backup_path=backup_path,
        )
    except MigrationError:
        raise
    except sqlite3.Error as exc:
        raise MigrationError(f"SQLite migration failed: {exc}") from exc
    finally:
        connection.close()


def current_schema_version(path: Path) -> int:
    if not path.is_file():
        return 0
    try:
        uri = f"file:{path.resolve().as_posix()}?mode=ro"
        with sqlite3.connect(uri, uri=True) as connection:
            row = connection.execute("SELECT max(version) FROM schema_migrations").fetchone()
            return int(row[0] or 0)
    except sqlite3.Error as exc:
        raise MigrationError(f"cannot read schema version: {exc}") from exc
