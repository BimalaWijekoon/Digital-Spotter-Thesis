"""SQLite migrations, repositories, backups, and durable outbox."""

from digital_spotter.persistence.backup import (
    BackupError,
    DatabaseSnapshot,
    backup_database,
    restore_database,
)
from digital_spotter.persistence.repository import (
    IdempotencyConflict,
    RepositoryError,
    SessionIMUSummary,
    SessionRecord,
    SQLiteRepository,
    SavedRep,
)
from digital_spotter.persistence.schema import (
    MigrationError,
    MigrationReport,
    current_schema_version,
    migrate_database,
)

__all__ = [
    "BackupError",
    "DatabaseSnapshot",
    "IdempotencyConflict",
    "MigrationError",
    "MigrationReport",
    "RepositoryError",
    "SessionIMUSummary",
    "SessionRecord",
    "SQLiteRepository",
    "SavedRep",
    "backup_database",
    "current_schema_version",
    "migrate_database",
    "restore_database",
]
