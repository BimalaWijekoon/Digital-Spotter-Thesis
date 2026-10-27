"""Operator-facing bootstrap CLI for configuration and package diagnostics."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Sequence

from pydantic import ValidationError

from digital_spotter import __version__
from digital_spotter.config import SettingsLoadError, load_settings
from digital_spotter.contracts.model import validate_model_package
from digital_spotter.persistence import (
    BackupError,
    MigrationError,
    backup_database,
    current_schema_version,
    migrate_database,
    restore_database,
)
from digital_spotter.imu.provisioning import (
    ProvisioningError,
    import_claim,
    issue_claim_bundle,
    read_confidential_claim_file,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="dsctl")
    subcommands = parser.add_subparsers(dest="command", required=True)
    subcommands.add_parser("version", help="print the canonical package version")
    config = subcommands.add_parser("config", help="validate non-secret configuration")
    config_commands = config.add_subparsers(dest="config_command", required=True)
    check = config_commands.add_parser("check", help="validate and print a safe summary")
    check.add_argument("--config", type=Path)
    check.add_argument("--profile", choices=("development", "test", "production"))
    model = subcommands.add_parser("model", help="validate a model package manifest and hashes")
    model_commands = model.add_subparsers(dest="model_command", required=True)
    model_check = model_commands.add_parser("check", help="validate model package readiness")
    model_check.add_argument("--manifest", type=Path, required=True)
    model_check.add_argument("--production", action="store_true")
    database = subcommands.add_parser("database", help="migrate, back up, or restore SQLite")
    database_commands = database.add_subparsers(dest="database_command", required=True)
    database_status = database_commands.add_parser("status", help="print schema version")
    database_status.add_argument("--database", type=Path, required=True)
    database_migrate = database_commands.add_parser(
        "migrate", help="apply pending migrations with an existing-database backup"
    )
    database_migrate.add_argument("--database", type=Path, required=True)
    database_migrate.add_argument("--backup-dir", type=Path)
    database_backup = database_commands.add_parser("backup", help="create an online backup")
    database_backup.add_argument("--database", type=Path, required=True)
    database_backup.add_argument("--output", type=Path, required=True)
    database_restore = database_commands.add_parser(
        "restore", help="restore a verified backup to a new path"
    )
    database_restore.add_argument("--backup", type=Path, required=True)
    database_restore.add_argument("--database", type=Path, required=True)
    wearable = subcommands.add_parser("wearable", help="provision a physical BLE wearable")
    wearable_commands = wearable.add_subparsers(dest="wearable_command", required=True)
    wearable_provision = wearable_commands.add_parser(
        "provision", help="import a confidential one-time QR/export claim"
    )
    wearable_provision.add_argument(
        "--claim-file",
        required=True,
        help="claim text file, or '-' to read from stdin; never pass the claim itself",
    )
    wearable_provision.add_argument("--identity-dir", type=Path, required=True)
    wearable_issue = wearable_commands.add_parser(
        "issue-claim", help="issue a unique confidential claim on a trusted station"
    )
    wearable_issue.add_argument("--device-id", required=True)
    wearable_issue.add_argument("--output-dir", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "version":
        print(__version__)
        return 0
    if args.command == "model":
        result = validate_model_package(args.manifest, production=args.production)
        print(json.dumps(result.safe_summary(), sort_keys=True))
        ready = result.production_ready if args.production else result.compatibility_ready
        return 0 if ready else 3
    if args.command == "wearable":
        try:
            if args.wearable_command == "issue-claim":
                receipt = issue_claim_bundle(args.device_id, args.output_dir)
                print(
                    json.dumps(
                        {
                            "device_id": receipt.device_id,
                            "bundle_directory": str(receipt.bundle_directory),
                            "claim_sha256": receipt.claim_fingerprint,
                        },
                        sort_keys=True,
                    )
                )
                return 0
            if args.claim_file == "-":
                claim_text = sys.stdin.read(2049)
            else:
                claim_text = read_confidential_claim_file(Path(args.claim_file))
            receipt = import_claim(claim_text, args.identity_dir)
            print(
                json.dumps(
                    {
                        "device_id": receipt.device_id,
                        "identity_directory": str(receipt.identity_directory),
                        "claim_sha256": receipt.claim_fingerprint,
                    },
                    sort_keys=True,
                )
            )
            return 0
        except (OSError, UnicodeError, ProvisioningError) as exc:
            print(f"wearable provisioning failed: {exc}", file=sys.stderr)
            return 5
    if args.command == "database":
        try:
            if args.database_command == "status":
                print(json.dumps({"schema_version": current_schema_version(args.database)}))
                return 0
            if args.database_command == "migrate":
                report = migrate_database(args.database, backup_dir=args.backup_dir)
                print(
                    json.dumps(
                        {
                            "database": str(report.database_path),
                            "previous_version": report.previous_version,
                            "current_version": report.current_version,
                            "applied_versions": report.applied_versions,
                            "backup": str(report.backup_path) if report.backup_path else None,
                        },
                        sort_keys=True,
                    )
                )
                return 0
            if args.database_command == "backup":
                snapshot = backup_database(args.database, args.output)
            else:
                snapshot = restore_database(args.backup, args.database)
            print(
                json.dumps(
                    {
                        "database": str(snapshot.database_path),
                        "sha256": snapshot.sha256,
                        "size_bytes": snapshot.size_bytes,
                        "schema_version": snapshot.schema_version,
                        "counts": snapshot.counts,
                    },
                    sort_keys=True,
                )
            )
            return 0
        except (BackupError, MigrationError) as exc:
            print(f"database operation failed: {exc}", file=sys.stderr)
            return 4

    environ = dict(os.environ)
    if args.profile is not None:
        environ["DS_PROFILE"] = args.profile
    try:
        settings = load_settings(args.config, environ=environ)
    except (SettingsLoadError, ValidationError) as exc:
        print(f"configuration invalid: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(settings.safe_summary(), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
