#!/usr/bin/env python3
"""Short real-R11 to local-session/SQLite validation using disposable paths."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import pwd
import time
from pathlib import Path
from uuid import uuid4

from digital_spotter.core import (
    LocalSessionService,
    SessionStartRequest,
    UnixIMUEventServer,
)
from digital_spotter.persistence import SQLiteRepository, migrate_database


async def _run(args: argparse.Namespace) -> int:
    if args.database.exists():
        raise FileExistsError(f"validation database already exists: {args.database}")
    migrate_database(args.database)
    repository = SQLiteRepository(args.database)
    service = LocalSessionService(repository=repository)
    await service.open()
    session_uuid = uuid4()
    started_ns = time.monotonic_ns()
    await service.begin(
        SessionStartRequest(
            session_uuid=session_uuid,
            edge_device_id=args.edge_device_id,
            imu_device_id=args.imu_device_id,
            exercise_id=0,
            exercise_name="R12 IMU transport validation",
            exercise_contract_version="r12-transport-1",
            started_monotonic_ns=started_ns,
            created_utc_ms=time.time_ns() // 1_000_000,
            model_package_id=None,
        )
    )
    allowed_uid = pwd.getpwnam(args.imu_user).pw_uid if args.imu_user else os.getuid()
    server = UnixIMUEventServer(
        socket_path=args.socket,
        on_event=service.accept_imu,
        allowed_uids=frozenset({allowed_uid}),
    )
    await server.start()
    startup_deadline = asyncio.get_running_loop().time() + args.startup_timeout
    try:
        while (
            asyncio.get_running_loop().time() < startup_deadline
            and not service.ring_snapshot()
        ):
            await asyncio.sleep(0.1)
        if not service.ring_snapshot():
            raise TimeoutError("no R11 IMU event arrived before startup timeout")
        deadline = asyncio.get_running_loop().time() + args.duration
        while asyncio.get_running_loop().time() < deadline:
            await asyncio.sleep(0.1)
    finally:
        await server.close()
    ended_ns = time.monotonic_ns()
    result = await service.stop(
        session_uuid=session_uuid,
        ended_monotonic_ns=ended_ns,
        ended_utc_ms=time.time_ns() // 1_000_000,
    )
    ingest = server.counters()
    await service.close()
    summary = result.imu_summary
    if (
        summary.sample_count >= 2
        and summary.first_captured_monotonic_ns is not None
        and summary.last_captured_monotonic_ns is not None
    ):
        elapsed_s = (
            summary.last_captured_monotonic_ns
            - summary.first_captured_monotonic_ns
        ) / 1_000_000_000
        measured_hz = (summary.sample_count - 1) / elapsed_s if elapsed_s > 0 else 0.0
    else:
        elapsed_s = 0.0
        measured_hz = 0.0
    report = {
        "result": "PASS"
        if summary.sample_count >= args.minimum_samples and ingest.events_rejected == 0
        else "FAIL",
        "session_uuid": str(session_uuid),
        "database": str(args.database.resolve()),
        "socket": str(args.socket.resolve()),
        "elapsed_s": elapsed_s,
        "measured_hz": measured_hz,
        "sample_count": summary.sample_count,
        "gap_count": summary.gap_count,
        "ring_eviction_count": summary.ring_eviction_count,
        "degraded_sample_count": summary.degraded_sample_count,
        "clock_reset_count": summary.clock_reset_count,
        "distinct_boot_count": summary.distinct_boot_count,
        "ingest": ingest.__dict__,
        "session_state": result.record.state,
        "raw_imu_persisted": False,
    }
    print(json.dumps(report, sort_keys=True))
    return 0 if report["result"] == "PASS" else 1


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="validate-r12-local-session")
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--socket", type=Path, required=True)
    parser.add_argument("--edge-device-id", default="pi4-r12-bench")
    parser.add_argument("--imu-device-id", default="dsimu-r9-50787d92611a")
    parser.add_argument("--imu-user")
    parser.add_argument("--duration", type=float, default=10.0)
    parser.add_argument("--startup-timeout", type=float, default=20.0)
    parser.add_argument("--minimum-samples", type=int, default=400)
    return parser


def main() -> int:
    args = _parser().parse_args()
    if not 1.0 <= args.duration <= 300.0:
        raise SystemExit("duration must be between 1 and 300 seconds")
    if not 1.0 <= args.startup_timeout <= 120.0:
        raise SystemExit("startup-timeout must be between 1 and 120 seconds")
    if args.minimum_samples < 1:
        raise SystemExit("minimum-samples must be positive")
    try:
        return asyncio.run(_run(args))
    except (FileExistsError, OSError, ValueError) as exc:
        print(json.dumps({"result": "ERROR", "error": str(exc)}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
