from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from uuid import UUID

import pytest

from digital_spotter.contracts import (
    AnalysisEvent,
    EventEnvelope,
    EventType,
    MonotonicNanoseconds,
    Quality,
    RepEvent,
    RepTransition,
    Source,
    UtcMilliseconds,
    new_event_id,
)
from digital_spotter.persistence import (
    BackupError,
    IdempotencyConflict,
    MigrationError,
    RepositoryError,
    SQLiteRepository,
    backup_database,
    current_schema_version,
    migrate_database,
    restore_database,
)
from digital_spotter.persistence.schema import connect_database


SESSION_ID = UUID("11111111-1111-4111-8111-111111111111")
REP_ID = UUID("22222222-2222-4222-8222-222222222222")
ANALYSIS_ID = UUID("33333333-3333-4333-8333-333333333333")
DEVICE_ID = "pi-test-001"


def _repository(tmp_path: Path) -> SQLiteRepository:
    path = tmp_path / "product.sqlite3"
    migrate_database(path)
    repository = SQLiteRepository(path)
    repository.create_session(
        session_uuid=SESSION_ID,
        device_id=DEVICE_ID,
        exercise_id=0,
        exercise_name="Barbell Back Squat",
        exercise_contract_version="squat-1.0.0",
        started_monotonic_ns=1_000_000,
        created_utc_ms=1_750_000_000_000,
        model_package_id="test-model",
    )
    return repository


def _events(*, quality: Quality = Quality.GOOD):
    rep_payload = RepEvent(
        rep_id=REP_ID,
        rep_number=1,
        exercise_contract_version="squat-1.0.0",
        event=RepTransition.COMPLETED,
        captured_monotonic_ns=MonotonicNanoseconds(2_000_000),
        quality=quality,
    )
    rep_event = EventEnvelope[RepEvent](
        event_type=EventType.REP_EVENT,
        event_id=new_event_id(unix_time_ms=1_750_000_000_001, random_bits=1),
        source=Source.CORE,
        device_id=DEVICE_ID,
        session_id=SESSION_ID,
        captured_monotonic_ns=MonotonicNanoseconds(2_000_000),
        created_monotonic_ns=MonotonicNanoseconds(2_010_000),
        created_utc_ms=UtcMilliseconds(1_750_000_000_001),
        quality=quality,
        payload=rep_payload,
    )
    analysis_payload = AnalysisEvent(
        analysis_id=ANALYSIS_ID,
        rep_id=REP_ID,
        model_package_id="test-model",
        model_version="1.0.0-test",
        feature_contract_version="1.0.0-test",
        input_hash="a" * 64,
        label="good_form",
        bad_form_probability=0.1,
        threshold=0.5,
        latency_ns=100_000,
        quality=quality,
    )
    analysis_event = EventEnvelope[AnalysisEvent](
        event_type=EventType.ANALYSIS_EVENT,
        event_id=new_event_id(unix_time_ms=1_750_000_000_002, random_bits=2),
        source=Source.CORE,
        device_id=DEVICE_ID,
        session_id=SESSION_ID,
        created_monotonic_ns=MonotonicNanoseconds(2_020_000),
        created_utc_ms=UtcMilliseconds(1_750_000_000_002),
        quality=quality,
        payload=analysis_payload,
    )
    return rep_event, analysis_event


def _create_legacy_database(path: Path) -> None:
    with sqlite3.connect(path) as connection:
        connection.executescript(
            (Path(__file__).parents[2] / "database" / "schema.sql").read_text(
                encoding="utf-8"
            )
        )
        connection.execute(
            "INSERT INTO sessions (exercise_id, exercise_name) VALUES (0, 'Legacy Squat')"
        )
        connection.execute(
            "INSERT INTO reps (session_id, rep_number, phase, timestamp_ms) "
            "VALUES (1, 1, 3, 1000)"
        )


def test_fresh_migration_is_numbered_idempotent_and_configures_sqlite(tmp_path):
    path = tmp_path / "fresh.sqlite3"

    first = migrate_database(path)
    second = migrate_database(path)

    assert first.applied_versions == (1, 2, 3)
    assert second.applied_versions == ()
    assert second.previous_version == 3
    assert current_schema_version(path) == 3
    connection = connect_database(path)
    try:
        assert connection.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        assert {
            "schema_migrations",
            "devices",
            "sessions",
            "reps",
            "analysis_events",
            "model_registry",
            "outbox",
            "audit_events",
            "session_imu_summaries",
        } <= tables
    finally:
        connection.close()


def test_copied_prototype_requires_backup_and_preserves_rows(tmp_path):
    path = tmp_path / "legacy.sqlite3"
    _create_legacy_database(path)

    with pytest.raises(MigrationError, match="requires backup_dir"):
        migrate_database(path)
    report = migrate_database(path, backup_dir=tmp_path / "backups")

    assert report.backup_path is not None
    assert report.backup_path.is_file()
    assert report.backup_path.with_suffix(
        report.backup_path.suffix + ".manifest.json"
    ).is_file()
    repository = SQLiteRepository(path)
    assert repository.counts() == {
        "sessions": 1,
        "session_imu_summaries": 0,
        "reps": 1,
        "analysis_events": 0,
        "outbox": 0,
    }
    connection = connect_database(path)
    try:
        assert connection.execute(
            "SELECT record_uuid FROM sessions"
        ).fetchone()[0]
        assert connection.execute("SELECT record_uuid FROM reps").fetchone()[0]
    finally:
        connection.close()


def test_completed_rep_analysis_and_outbox_commit_atomically_and_idempotently(tmp_path):
    repository = _repository(tmp_path)
    rep_event, analysis_event = _events()

    first = repository.save_completed_rep(
        rep_event=rep_event,
        analysis_event=analysis_event,
    )
    second = repository.save_completed_rep(
        rep_event=rep_event,
        analysis_event=analysis_event,
    )

    assert first.already_existed is False
    assert second.already_existed is True
    assert first.rep_row_id == second.rep_row_id
    assert repository.counts() == {
        "sessions": 1,
        "session_imu_summaries": 0,
        "reps": 1,
        "analysis_events": 1,
        "outbox": 1,
    }
    connection = connect_database(repository.database_path)
    try:
        outbox = connection.execute(
            "SELECT schema_version, event_type, payload_json FROM outbox"
        ).fetchone()
        payload = json.loads(outbox["payload_json"])
        assert outbox["schema_version"] == 1
        assert outbox["event_type"] == "completed_rep_analysis"
        assert payload["rep_event"]["payload"]["rep_id"] == str(REP_ID)
        assert payload["analysis_event"]["payload"]["analysis_id"] == str(ANALYSIS_ID)
    finally:
        connection.close()


def test_outbox_failure_rolls_back_rep_and_analysis(tmp_path):
    repository = _repository(tmp_path)
    connection = connect_database(repository.database_path)
    try:
        connection.execute(
            "CREATE TRIGGER reject_test_outbox BEFORE INSERT ON outbox "
            "BEGIN SELECT RAISE(ABORT, 'test outbox failure'); END"
        )
    finally:
        connection.close()

    rep_event, analysis_event = _events()
    with pytest.raises(RepositoryError, match="completed-rep transaction failed"):
        repository.save_completed_rep(rep_event=rep_event, analysis_event=analysis_event)

    assert repository.counts() == {
        "sessions": 1,
        "session_imu_summaries": 0,
        "reps": 0,
        "analysis_events": 0,
        "outbox": 0,
    }


def test_idempotency_conflict_and_simulated_data_fail_closed(tmp_path):
    repository = _repository(tmp_path)
    rep_event, analysis_event = _events()
    repository.save_completed_rep(rep_event=rep_event, analysis_event=analysis_event)
    raw = analysis_event.model_dump(mode="json")
    raw["payload"]["label"] = "different_label"
    conflicting = EventEnvelope[AnalysisEvent].model_validate(raw)

    with pytest.raises(IdempotencyConflict):
        repository.save_completed_rep(rep_event=rep_event, analysis_event=conflicting)

    simulated_rep, simulated_analysis = _events(quality=Quality.SIMULATED)
    with pytest.raises(RepositoryError, match="simulated events"):
        repository.save_completed_rep(
            rep_event=simulated_rep,
            analysis_event=simulated_analysis,
        )


def test_online_backup_restore_drill_preserves_schema_and_counts(tmp_path):
    repository = _repository(tmp_path)
    rep_event, analysis_event = _events()
    repository.save_completed_rep(rep_event=rep_event, analysis_event=analysis_event)
    backup = tmp_path / "backup" / "product.sqlite3"

    snapshot = backup_database(repository.database_path, backup)
    restored = restore_database(backup, tmp_path / "restored.sqlite3")

    assert restored.schema_version == snapshot.schema_version == 3
    assert restored.counts == snapshot.counts == repository.counts()
    with pytest.raises(BackupError, match="already exists"):
        restore_database(backup, tmp_path / "restored.sqlite3")


def test_restore_rejects_manifest_tampering(tmp_path):
    repository = _repository(tmp_path)
    backup = tmp_path / "backup.sqlite3"
    backup_database(repository.database_path, backup)
    manifest_path = backup.with_suffix(backup.suffix + ".manifest.json")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["counts"]["sessions"] = 999
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(BackupError, match="does not match"):
        restore_database(backup, tmp_path / "restored.sqlite3")


def test_migration_checksum_tampering_is_rejected(tmp_path):
    path = tmp_path / "product.sqlite3"
    migrate_database(path)
    connection = connect_database(path)
    try:
        connection.execute(
            "UPDATE schema_migrations SET checksum = ? WHERE version = 1",
            ("f" * 64,),
        )
    finally:
        connection.close()

    with pytest.raises(MigrationError, match="checksum mismatch"):
        migrate_database(path)
