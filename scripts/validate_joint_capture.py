#!/usr/bin/env python3
"""Short research check: one local session receives real IMU and vision events."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import time
from pathlib import Path
from uuid import uuid4

from digital_spotter.core import (
    LocalSessionService,
    SessionStartRequest,
    UnixIMUEventServer,
    UnixVisionEventServer,
)
from digital_spotter.persistence import SQLiteRepository, migrate_database


async def _run(args: argparse.Namespace) -> int:
    if args.database.exists():
        raise FileExistsError(f"database already exists: {args.database}")
    migrate_database(args.database)
    repository = SQLiteRepository(args.database)
    session = LocalSessionService(repository=repository)
    imu_server = UnixIMUEventServer(
        socket_path=args.imu_socket,
        on_event=session.accept_imu,
        allowed_uids=frozenset({os.getuid()}),
        socket_mode=0o600,
    )
    vision_server = UnixVisionEventServer(
        socket_path=args.vision_socket,
        on_pose=session.accept_pose,
        allowed_uids=frozenset({os.getuid()}),
    )
    session_uuid = uuid4()
    started_ns = time.monotonic_ns()
    await session.open()
    try:
        await session.begin(
            SessionStartRequest(
                session_uuid=session_uuid,
                edge_device_id=args.edge_device_id,
                imu_device_id=args.imu_device_id,
                exercise_id=0,
                exercise_name="Joint capture research check",
                exercise_contract_version="joint-capture-1",
                started_monotonic_ns=started_ns,
                created_utc_ms=time.time_ns() // 1_000_000,
                model_package_id=None,
            )
        )
        try:
            await imu_server.start()
            await vision_server.start()
            print(json.dumps({"status": "listening", "imu_socket": str(args.imu_socket), "vision_socket": str(args.vision_socket)}), flush=True)
            deadline = asyncio.get_running_loop().time() + args.startup_timeout
            while asyncio.get_running_loop().time() < deadline:
                if session.ring_snapshot() and session.pose_stats().accepted_count:
                    break
                await asyncio.sleep(0.1)
            if session.ring_snapshot() and session.pose_stats().accepted_count:
                await asyncio.sleep(args.duration)
        finally:
            await imu_server.close()
            await vision_server.close()
        pose = session.pose_stats()
        result = await session.stop(
            session_uuid=session_uuid,
            ended_monotonic_ns=time.monotonic_ns(),
            ended_utc_ms=time.time_ns() // 1_000_000,
        )
    finally:
        await session.close(checkpoint_monotonic_ns=time.monotonic_ns())
    imu = result.imu_summary
    success = imu.sample_count > 0 and pose.accepted_count > 0
    report = {
        "result": "PASS" if success else "FAIL",
        "session_uuid": str(session_uuid),
        "database": str(args.database),
        "imu_samples": imu.sample_count,
        "imu_first_captured_monotonic_ns": imu.first_captured_monotonic_ns,
        "imu_last_captured_monotonic_ns": imu.last_captured_monotonic_ns,
        "imu_degraded_samples": imu.degraded_sample_count,
        "imu_gap_count": imu.gap_count,
        "pose_events": pose.accepted_count,
        "pose_first_captured_monotonic_ns": pose.first_captured_monotonic_ns,
        "pose_last_captured_monotonic_ns": pose.last_captured_monotonic_ns,
        "pose_degraded_events": pose.degraded_count,
        "pose_ring_evictions": pose.ring_evictions,
        "imu_ingest": imu_server.counters().__dict__,
        "vision_ingest": vision_server.counters().__dict__,
        "analysis_events_persisted": repository.counts()["analysis_events"],
        "fusion_or_scoring_performed": False,
    }
    print(json.dumps(report, sort_keys=True))
    return 0 if success else 1


def main() -> int:
    parser = argparse.ArgumentParser(prog="validate-joint-capture")
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--imu-socket", type=Path, required=True)
    parser.add_argument("--vision-socket", type=Path, required=True)
    parser.add_argument("--edge-device-id", default="pi4-joint-research")
    parser.add_argument("--imu-device-id", default="dsimu-r9-50787d92611a")
    parser.add_argument("--duration", type=float, default=8.0)
    parser.add_argument("--startup-timeout", type=float, default=20.0)
    args = parser.parse_args()
    if not 1.0 <= args.duration <= 30.0 or not 1.0 <= args.startup_timeout <= 60.0:
        parser.error("duration must be 1-30 seconds and startup timeout 1-60 seconds")
    try:
        return asyncio.run(_run(args))
    except (FileExistsError, OSError, ValueError) as exc:
        print(json.dumps({"result": "ERROR", "error": str(exc)}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
