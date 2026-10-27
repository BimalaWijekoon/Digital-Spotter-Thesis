"""Canonical SQLite repositories and atomic completed-rep/outbox transaction."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from digital_spotter.contracts import (
    AnalysisEvent,
    EventEnvelope,
    Quality,
    RepEvent,
    RepTransition,
)
from digital_spotter.persistence.schema import connect_database, current_schema_version


LATEST_SCHEMA_VERSION = 3


class RepositoryError(RuntimeError):
    """Base class for durable repository errors."""


class IdempotencyConflict(RepositoryError):
    """Raised when an existing stable ID is reused with different content."""


@dataclass(frozen=True)
class SavedRep:
    rep_row_id: int
    analysis_id: UUID
    outbox_event_id: UUID
    already_existed: bool


@dataclass(frozen=True)
class SessionRecord:
    row_id: int
    session_uuid: UUID
    device_id: str
    exercise_id: int
    exercise_name: str
    exercise_contract_version: str
    state: str
    started_monotonic_ns: int
    ended_monotonic_ns: int | None
    created_utc_ms: int | None
    model_package_id: str | None
    privacy_mode: str


@dataclass(frozen=True)
class SessionIMUSummary:
    imu_device_id: str
    sample_count: int
    gap_count: int
    degraded_sample_count: int
    clock_reset_count: int
    distinct_boot_count: int
    ring_eviction_count: int
    duplicate_event_count: int
    last_boot_id: int | None
    first_sequence: int | None
    last_sequence: int | None
    first_captured_monotonic_ns: int | None
    last_captured_monotonic_ns: int | None
    updated_monotonic_ns: int


def _session_from_row(row: sqlite3.Row) -> SessionRecord:
    return SessionRecord(
        row_id=int(row["id"]),
        session_uuid=UUID(row["record_uuid"]),
        device_id=row["device_id"],
        exercise_id=int(row["exercise_id"]),
        exercise_name=row["exercise_name"],
        exercise_contract_version=row["exercise_contract_version"],
        state=row["state"],
        started_monotonic_ns=int(row["started_monotonic_ns"]),
        ended_monotonic_ns=(
            int(row["ended_monotonic_ns"])
            if row["ended_monotonic_ns"] is not None
            else None
        ),
        created_utc_ms=(
            int(row["created_utc_ms"]) if row["created_utc_ms"] is not None else None
        ),
        model_package_id=row["model_package_id"],
        privacy_mode=row["privacy_mode"],
    )


def _summary_from_row(row: sqlite3.Row) -> SessionIMUSummary:
    return SessionIMUSummary(
        imu_device_id=row["imu_device_id"],
        sample_count=int(row["sample_count"]),
        gap_count=int(row["gap_count"]),
        degraded_sample_count=int(row["degraded_sample_count"]),
        clock_reset_count=int(row["clock_reset_count"]),
        distinct_boot_count=int(row["distinct_boot_count"]),
        ring_eviction_count=int(row["ring_eviction_count"]),
        duplicate_event_count=int(row["duplicate_event_count"]),
        last_boot_id=(
            int(row["last_boot_id"]) if row["last_boot_id"] is not None else None
        ),
        first_sequence=(
            int(row["first_sequence"]) if row["first_sequence"] is not None else None
        ),
        last_sequence=(
            int(row["last_sequence"]) if row["last_sequence"] is not None else None
        ),
        first_captured_monotonic_ns=(
            int(row["first_captured_monotonic_ns"])
            if row["first_captured_monotonic_ns"] is not None
            else None
        ),
        last_captured_monotonic_ns=(
            int(row["last_captured_monotonic_ns"])
            if row["last_captured_monotonic_ns"] is not None
            else None
        ),
        updated_monotonic_ns=int(row["updated_monotonic_ns"]),
    )


def _validate_summary(summary: SessionIMUSummary) -> None:
    if not summary.imu_device_id or len(summary.imu_device_id) > 64:
        raise RepositoryError("IMU device ID must contain 1-64 characters")
    counters = (
        summary.sample_count,
        summary.gap_count,
        summary.degraded_sample_count,
        summary.clock_reset_count,
        summary.distinct_boot_count,
        summary.ring_eviction_count,
        summary.duplicate_event_count,
        summary.updated_monotonic_ns,
    )
    if any(value < 0 for value in counters):
        raise RepositoryError("session IMU summary counters cannot be negative")
    if (
        summary.last_boot_id is not None
        and not 0 <= summary.last_boot_id <= 0xFFFFFFFFFFFFFFFF
    ):
        raise RepositoryError("session IMU boot ID is outside u64")
    for sequence in (summary.first_sequence, summary.last_sequence):
        if sequence is not None and not 0 <= sequence <= 0xFFFF:
            raise RepositoryError("session IMU sequence is outside u16")
    for timestamp in (
        summary.first_captured_monotonic_ns,
        summary.last_captured_monotonic_ns,
    ):
        if timestamp is not None and timestamp < 0:
            raise RepositoryError("session IMU timestamps cannot be negative")


def _upsert_summary(
    connection: sqlite3.Connection,
    session_uuid: UUID,
    summary: SessionIMUSummary,
) -> None:
    _validate_summary(summary)
    connection.execute(
        """
        INSERT INTO session_imu_summaries (
            session_uuid, imu_device_id, sample_count, gap_count,
            degraded_sample_count, clock_reset_count, distinct_boot_count,
            ring_eviction_count, duplicate_event_count, first_sequence,
            last_boot_id, last_sequence, first_captured_monotonic_ns,
            last_captured_monotonic_ns, updated_monotonic_ns
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(session_uuid) DO UPDATE SET
            imu_device_id = excluded.imu_device_id,
            sample_count = excluded.sample_count,
            gap_count = excluded.gap_count,
            degraded_sample_count = excluded.degraded_sample_count,
            clock_reset_count = excluded.clock_reset_count,
            distinct_boot_count = excluded.distinct_boot_count,
            ring_eviction_count = excluded.ring_eviction_count,
            duplicate_event_count = excluded.duplicate_event_count,
            first_sequence = excluded.first_sequence,
            last_boot_id = excluded.last_boot_id,
            last_sequence = excluded.last_sequence,
            first_captured_monotonic_ns = excluded.first_captured_monotonic_ns,
            last_captured_monotonic_ns = excluded.last_captured_monotonic_ns,
            updated_monotonic_ns = excluded.updated_monotonic_ns
        """,
        (
            str(session_uuid),
            summary.imu_device_id,
            summary.sample_count,
            summary.gap_count,
            summary.degraded_sample_count,
            summary.clock_reset_count,
            summary.distinct_boot_count,
            summary.ring_eviction_count,
            summary.duplicate_event_count,
            summary.first_sequence,
            str(summary.last_boot_id) if summary.last_boot_id is not None else None,
            summary.last_sequence,
            summary.first_captured_monotonic_ns,
            summary.last_captured_monotonic_ns,
            summary.updated_monotonic_ns,
        ),
    )


def _canonical_event(envelope: EventEnvelope) -> tuple[str, str]:
    payload_json = json.dumps(
        envelope.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    return payload_json, hashlib.sha256(payload_json.encode()).hexdigest()


def _iso_utc(utc_ms: int | None) -> str:
    if utc_ms is None:
        return datetime.now(UTC).isoformat()
    return datetime.fromtimestamp(utc_ms / 1000, tz=UTC).isoformat()


class SQLiteRepository:
    def __init__(self, database_path: Path):
        self.database_path = database_path.resolve()
        version = current_schema_version(self.database_path)
        if version != LATEST_SCHEMA_VERSION:
            raise RepositoryError(
                f"database schema {version} is not current ({LATEST_SCHEMA_VERSION})"
            )

    def save_workout_context(self, *, session_uuid: UUID, load_kg: float,
                             rep_count: int, model_version: str) -> None:
        """Save explicit unscored workout context; never invent analysis rows."""
        import math
        if not math.isfinite(load_kg) or load_kg < 0 or rep_count < 0:
            raise RepositoryError('invalid workout summary')
        notes = json.dumps({'load_kg': load_kg, 'rep_count': rep_count,
                            'analysis_validated': False, 'model_version': model_version})
        with connect_database(self.database_path) as connection:
            changed = connection.execute(
                'UPDATE sessions SET notes=?, total_reps=? WHERE record_uuid=?',
                (notes, rep_count, str(session_uuid)),
            )
            if changed.rowcount != 1:
                raise RepositoryError('workout session does not exist')
            connection.commit()

    def create_session(
        self,
        *,
        session_uuid: UUID,
        device_id: str,
        exercise_id: int,
        exercise_name: str,
        exercise_contract_version: str,
        started_monotonic_ns: int,
        created_utc_ms: int | None,
        model_package_id: str | None,
        privacy_mode: str = "summary_only",
        initial_imu_summary: SessionIMUSummary | None = None,
    ) -> int:
        if started_monotonic_ns < 0:
            raise RepositoryError("started_monotonic_ns cannot be negative")
        if not device_id or len(device_id) > 64:
            raise RepositoryError("device_id must contain 1-64 characters")
        if not exercise_name or len(exercise_name) > 128:
            raise RepositoryError("exercise_name must contain 1-128 characters")
        if not exercise_contract_version or len(exercise_contract_version) > 64:
            raise RepositoryError("exercise contract version is invalid")
        connection = connect_database(self.database_path)
        try:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                "SELECT id, device_id, exercise_id, exercise_name, "
                "started_monotonic_ns, model_package_id, exercise_contract_version, "
                "privacy_mode "
                "FROM sessions WHERE record_uuid = ?",
                (str(session_uuid),),
            ).fetchone()
            expected = (
                device_id,
                exercise_id,
                exercise_name,
                started_monotonic_ns,
                model_package_id,
                exercise_contract_version,
                privacy_mode,
            )
            if existing is not None:
                actual = tuple(existing[key] for key in (
                    "device_id",
                    "exercise_id",
                    "exercise_name",
                    "started_monotonic_ns",
                    "model_package_id",
                    "exercise_contract_version",
                    "privacy_mode",
                ))
                if actual != expected:
                    raise IdempotencyConflict(
                        "session UUID already exists with different content"
                    )
                if initial_imu_summary is not None:
                    stored_summary = connection.execute(
                        "SELECT imu_device_id FROM session_imu_summaries "
                        "WHERE session_uuid = ?",
                        (str(session_uuid),),
                    ).fetchone()
                    if stored_summary is None:
                        _upsert_summary(connection, session_uuid, initial_imu_summary)
                    elif stored_summary["imu_device_id"] != initial_imu_summary.imu_device_id:
                        raise IdempotencyConflict(
                            "session UUID already exists for a different IMU device"
                        )
                connection.commit()
                return int(existing["id"])
            cursor = connection.execute(
                """
                INSERT INTO sessions (
                    exercise_id, exercise_name, started_at, exercise_contract_version,
                    record_uuid,
                    device_id, schema_version, state, started_monotonic_ns,
                    model_package_id, created_utc_ms, privacy_mode
                ) VALUES (?, ?, ?, ?, ?, ?, 1, 'active', ?, ?, ?, ?)
                """,
                (
                    exercise_id,
                    exercise_name,
                    _iso_utc(created_utc_ms),
                    exercise_contract_version,
                    str(session_uuid),
                    device_id,
                    started_monotonic_ns,
                    model_package_id,
                    created_utc_ms,
                    privacy_mode,
                ),
            )
            if initial_imu_summary is not None:
                _upsert_summary(connection, session_uuid, initial_imu_summary)
            connection.commit()
            return int(cursor.lastrowid)
        except RepositoryError:
            connection.rollback()
            raise
        except sqlite3.Error as exc:
            connection.rollback()
            raise RepositoryError(f"session transaction failed: {exc}") from exc
        finally:
            connection.close()

    def get_session(self, session_uuid: UUID) -> SessionRecord | None:
        connection = connect_database(self.database_path)
        try:
            row = connection.execute(
                "SELECT * FROM sessions WHERE record_uuid = ?",
                (str(session_uuid),),
            ).fetchone()
            return _session_from_row(row) if row is not None else None
        finally:
            connection.close()

    def get_active_session(self) -> SessionRecord | None:
        connection = connect_database(self.database_path)
        try:
            rows = connection.execute(
                "SELECT * FROM sessions WHERE state = 'active' ORDER BY id"
            ).fetchall()
            if len(rows) > 1:
                raise RepositoryError("database contains more than one active session")
            return _session_from_row(rows[0]) if rows else None
        finally:
            connection.close()

    def get_session_imu_summary(
        self,
        session_uuid: UUID,
    ) -> SessionIMUSummary | None:
        connection = connect_database(self.database_path)
        try:
            row = connection.execute(
                "SELECT * FROM session_imu_summaries WHERE session_uuid = ?",
                (str(session_uuid),),
            ).fetchone()
            return _summary_from_row(row) if row is not None else None
        finally:
            connection.close()

    def checkpoint_session_imu(
        self,
        *,
        session_uuid: UUID,
        summary: SessionIMUSummary,
    ) -> None:
        connection = connect_database(self.database_path)
        try:
            connection.execute("BEGIN IMMEDIATE")
            session = connection.execute(
                "SELECT state FROM sessions WHERE record_uuid = ?",
                (str(session_uuid),),
            ).fetchone()
            if session is None:
                raise RepositoryError("session does not exist")
            if session["state"] != "active":
                raise RepositoryError("only an active session can be checkpointed")
            _upsert_summary(connection, session_uuid, summary)
            connection.commit()
        except RepositoryError:
            connection.rollback()
            raise
        except sqlite3.Error as exc:
            connection.rollback()
            raise RepositoryError(f"session checkpoint transaction failed: {exc}") from exc
        finally:
            connection.close()

    def complete_session(
        self,
        *,
        session_uuid: UUID,
        ended_monotonic_ns: int,
        ended_utc_ms: int | None,
        summary: SessionIMUSummary,
    ) -> SessionRecord:
        if ended_monotonic_ns < 0:
            raise RepositoryError("ended_monotonic_ns cannot be negative")
        connection = connect_database(self.database_path)
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM sessions WHERE record_uuid = ?",
                (str(session_uuid),),
            ).fetchone()
            if row is None:
                raise RepositoryError("session does not exist")
            if row["state"] == "completed":
                connection.commit()
                return _session_from_row(row)
            if row["state"] != "active":
                raise RepositoryError(f"session cannot complete from state {row['state']}")
            if ended_monotonic_ns < int(row["started_monotonic_ns"]):
                raise RepositoryError("session cannot end before it started")
            if (
                summary.last_captured_monotonic_ns is not None
                and ended_monotonic_ns < summary.last_captured_monotonic_ns
            ):
                raise RepositoryError("session cannot end before its latest IMU sample")
            _upsert_summary(connection, session_uuid, summary)
            connection.execute(
                """
                UPDATE sessions
                SET state = 'completed', ended_at = ?, ended_monotonic_ns = ?
                WHERE record_uuid = ?
                """,
                (_iso_utc(ended_utc_ms), ended_monotonic_ns, str(session_uuid)),
            )
            completed = connection.execute(
                "SELECT * FROM sessions WHERE record_uuid = ?",
                (str(session_uuid),),
            ).fetchone()
            connection.commit()
            return _session_from_row(completed)
        except RepositoryError:
            connection.rollback()
            raise
        except sqlite3.Error as exc:
            connection.rollback()
            raise RepositoryError(f"session completion transaction failed: {exc}") from exc
        finally:
            connection.close()

    def save_completed_rep(
        self,
        *,
        rep_event: EventEnvelope[RepEvent],
        analysis_event: EventEnvelope[AnalysisEvent],
    ) -> SavedRep:
        rep = rep_event.payload
        analysis = analysis_event.payload
        if rep.event is not RepTransition.COMPLETED:
            raise RepositoryError("only completed rep events are durable")
        if rep.quality is Quality.SIMULATED or analysis.quality is Quality.SIMULATED:
            raise RepositoryError("simulated events cannot be durably persisted")
        if rep.rep_id != analysis.rep_id:
            raise RepositoryError("rep and analysis IDs differ")
        if rep_event.session_id is None or rep_event.session_id != analysis_event.session_id:
            raise RepositoryError("rep and analysis session IDs differ or are missing")
        if analysis_event.device_id is None or rep_event.device_id != analysis_event.device_id:
            raise RepositoryError("rep and analysis device IDs differ or are missing")

        rep_json, rep_hash = _canonical_event(rep_event)
        analysis_json, analysis_hash = _canonical_event(analysis_event)
        outbox_json = json.dumps(
            {
                "schema_version": 1,
                "rep_event": json.loads(rep_json),
                "analysis_event": json.loads(analysis_json),
            },
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        )
        outbox_hash = hashlib.sha256(outbox_json.encode()).hexdigest()
        session_uuid = str(rep_event.session_id)
        rep_uuid = str(rep.rep_id)
        connection = connect_database(self.database_path)
        try:
            connection.execute("BEGIN IMMEDIATE")
            session = connection.execute(
                "SELECT id FROM sessions WHERE record_uuid = ?",
                (session_uuid,),
            ).fetchone()
            if session is None:
                raise RepositoryError("session does not exist")
            existing = connection.execute(
                "SELECT id, payload_hash, analysis_id FROM reps WHERE record_uuid = ?",
                (rep_uuid,),
            ).fetchone()
            if existing is not None:
                outbox = connection.execute(
                    "SELECT payload_hash FROM outbox WHERE event_id = ?",
                    (str(analysis_event.event_id),),
                ).fetchone()
                if (
                    existing["payload_hash"] != rep_hash
                    or existing["analysis_id"] != str(analysis.analysis_id)
                    or outbox is None
                    or outbox["payload_hash"] != outbox_hash
                ):
                    raise IdempotencyConflict("rep UUID already exists with different content")
                connection.commit()
                return SavedRep(
                    rep_row_id=int(existing["id"]),
                    analysis_id=analysis.analysis_id,
                    outbox_event_id=analysis_event.event_id,
                    already_existed=True,
                )

            cursor = connection.execute(
                """
                INSERT INTO reps (
                    session_id, rep_number, phase, timestamp_ms,
                    inference_label, inference_confidence, record_uuid,
                    rep_event_id, completed_monotonic_ns, quality, analysis_id,
                    payload_hash
                ) VALUES (?, ?, 3, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session["id"],
                    rep.rep_number,
                    int((rep_event.created_utc_ms or 0)),
                    analysis.label,
                    1.0 - analysis.bad_form_probability,
                    rep_uuid,
                    str(rep_event.event_id),
                    int(rep.captured_monotonic_ns),
                    rep.quality.value,
                    str(analysis.analysis_id),
                    rep_hash,
                ),
            )
            connection.execute(
                """
                INSERT INTO analysis_events (
                    analysis_id, event_id, session_uuid, rep_uuid, schema_version,
                    model_package_id, model_version, feature_contract_version,
                    input_hash, label, bad_form_probability, threshold, latency_ns,
                    quality, created_monotonic_ns, created_utc_ms, payload_json,
                    payload_hash
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(analysis.analysis_id),
                    str(analysis_event.event_id),
                    session_uuid,
                    rep_uuid,
                    analysis_event.schema_version,
                    analysis.model_package_id,
                    analysis.model_version,
                    analysis.feature_contract_version,
                    analysis.input_hash,
                    analysis.label,
                    analysis.bad_form_probability,
                    analysis.threshold,
                    analysis.latency_ns,
                    analysis.quality.value,
                    int(analysis_event.created_monotonic_ns),
                    analysis_event.created_utc_ms,
                    analysis_json,
                    analysis_hash,
                ),
            )
            connection.execute(
                """
                INSERT INTO outbox (
                    event_id, schema_version, event_type, device_id, session_uuid,
                    created_monotonic_ns, created_utc_ms, payload_json, payload_hash
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(analysis_event.event_id),
                    1,
                    "completed_rep_analysis",
                    analysis_event.device_id,
                    session_uuid,
                    int(analysis_event.created_monotonic_ns),
                    analysis_event.created_utc_ms,
                    outbox_json,
                    outbox_hash,
                ),
            )
            connection.commit()
            return SavedRep(
                rep_row_id=int(cursor.lastrowid),
                analysis_id=analysis.analysis_id,
                outbox_event_id=analysis_event.event_id,
                already_existed=False,
            )
        except RepositoryError:
            connection.rollback()
            raise
        except sqlite3.Error as exc:
            connection.rollback()
            raise RepositoryError(f"completed-rep transaction failed: {exc}") from exc
        finally:
            connection.close()

    def counts(self) -> dict[str, int]:
        connection = connect_database(self.database_path)
        try:
            return {
                table: connection.execute(f'SELECT count(*) FROM "{table}"').fetchone()[0]
                for table in (
                    "sessions",
                    "session_imu_summaries",
                    "reps",
                    "analysis_events",
                    "outbox",
                )
            }
        finally:
            connection.close()
