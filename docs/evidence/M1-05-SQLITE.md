# M1-05 SQLite migration and outbox evidence

**Date:** 2026-08-26
**Environment:** E1 local Linux Python 3.12
**Status:** DONE for schema, repository, backup, and restore foundation

## Delivered

- ordered migrations `0001` and `0002`, with contiguous-version enforcement and a
  checksum derived from migration identity plus implementation source;
- safe bridging of fresh and prototype `sessions`/`reps` tables, deterministic UUID
  backfill for historical rows, and additive product identity/state fields;
- `schema_migrations`, `devices`, `sessions`, `reps`, `analysis_events`,
  `model_registry`, `outbox`, and `audit_events` tables plus bounded constraints and
  lookup indexes;
- connection defaults for WAL, foreign keys, five-second busy timeout, and
  `synchronous=FULL`;
- required online backup before any existing database receives pending migrations;
- an atomic repository transaction for completed rep, analysis, and a versioned
  immutable composite outbox payload containing both exact event envelopes;
- stable UUID/event idempotency, conflict rejection, and an explicit refusal to
  durably save simulated/replay results;
- online `dsctl database backup` plus manifest/hash/schema/count-verified restore to
  a new path. Restore refuses to overwrite an existing database.

No live Pi database was migrated. The verified M0 Pi backup and its running
prototype remain untouched.

## Acceptance evidence

Focused M1 suite:

```text
.venv/bin/python -m pytest tests/unit tests/contract tests/replay tests/persistence -q
49 passed in 13.51s
```

Full prototype plus M1 compatibility suite:

```text
PYTHONPATH=src:.venv/lib/python3.12/site-packages \
  /tmp/digital-spotter-venv/bin/python -m pytest tests -q
135 passed, 7 warnings in 15.04s
```

The mixed path is intentional for this one compatibility run: the isolated legacy
environment contains the historical camera/model stack but not M1's `msgpack`,
while the canonical environment contains the locked M1 package dependencies. No
package was downloaded and the legacy environment was not modified.

The operator drill created a fresh database, reported schema version 2, performed
an online backup, and restored it to a new path. Backup and restored schema/counts
matched. Tests additionally prove:

- a copied legacy database cannot migrate without a backup destination;
- historical session/rep counts and identities survive migration;
- repeat migrations and repeat completed-rep writes are idempotent;
- forced outbox failure leaves no rep or analysis row;
- changed content under an existing stable ID is rejected;
- simulated data, migration-checksum tampering, manifest tampering, and restore
  overwrite are rejected.

The final source distribution and wheel were also built offline from the locked
cache. A new Python 3.12 environment installed that wheel and successfully ran
`dsctl database migrate` and `dsctl database status`; inspection confirmed both
numbered migration modules and all persistence modules were included.

## Security and operating boundary

- The outbox is local durable state only. It does not contain Firebase credentials
  and cannot upload directly to Firebase.
- Backup encryption/retention is not yet implemented; backups containing real user
  data must remain protected and must not be exported until the privacy/retention
  decisions and product key management are complete.
- `dsctl database migrate` mutates a database only after an existing database has
  received a verified online backup. Production service stop/activation remains an
  M8 operations procedure.

## Rollback

For a future real migration, stop writers, preserve the affected file, validate the
pre-migration backup manifest, restore to a new path, run integrity/schema/count
checks, then atomically activate the recovered database. M1 did not alter or delete
the legacy schema or the Pi database.
