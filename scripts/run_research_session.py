#!/usr/bin/env python3
"""Local-only research session/status viewer; no V5 scoring or browser writes."""

from __future__ import annotations

import argparse
import asyncio
import math
import os
import signal
import threading
import time
from http.server import ThreadingHTTPServer
from pathlib import Path
from uuid import uuid4

from digital_spotter.api.research_session import ResearchStatusHub, status_handler_class
from digital_spotter.core import (
    LocalSessionService,
    SessionStartRequest,
    UnixIMUEventServer,
    UnixVisionEventServer,
)
from digital_spotter.core.research_status import ResearchStatusProjector
from digital_spotter.inference.v5_model import V5ModelRuntime
from digital_spotter.inference.v5_shadow import V5ShadowEvaluator
from digital_spotter.persistence import SQLiteRepository


async def run(args: argparse.Namespace) -> None:
    if not args.database.is_file():
        raise FileNotFoundError("research database must already exist and be migrated")
    static_dir = Path(__file__).resolve().parents[1] / "src/digital_spotter/web/static"
    if not (static_dir / "ui-preview/index.html").is_file():
        raise FileNotFoundError("research UI assets are missing")
    for socket_path in (args.imu_socket, args.vision_socket):
        if socket_path.exists() or socket_path.is_symlink():
            raise FileExistsError(f"refusing to replace existing socket path: {socket_path}")
    repository = SQLiteRepository(args.database)
    if repository.get_active_session() is not None:
        raise RuntimeError("another local session is active; no session was changed")
    shadow = (
        V5ShadowEvaluator(V5ModelRuntime(args.shadow_v5_package))
        if args.shadow_v5_package is not None else None
    )

    session = LocalSessionService(repository=repository)
    projector = ResearchStatusProjector(session)
    hub = ResearchStatusHub()
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
    http_server: ThreadingHTTPServer | None = None
    http_worker: threading.Thread | None = None
    session_uuid = uuid4()
    begun = False
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for name in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(name, stop.set)

    await session.open()
    try:
        await session.begin(SessionStartRequest(
            session_uuid=session_uuid,
            edge_device_id=args.edge_device_id,
            imu_device_id=args.imu_device_id,
            exercise_id=args.exercise_id,
            exercise_name="Squat" if args.exercise_id == 0 else "Deadlift",
            exercise_contract_version="v5-research-video-rule-1",
            started_monotonic_ns=time.monotonic_ns(),
            created_utc_ms=time.time_ns() // 1_000_000,
            model_package_id=None,
        ))
        begun = True
        await imu_server.start()
        await vision_server.start()
        initial_now = time.monotonic_ns()
        hub.publish(projector.refresh(now_monotonic_ns=initial_now))
        hub.publish_imu_window(projector.imu_window(now_monotonic_ns=initial_now))
        http_server = ThreadingHTTPServer(
            ("127.0.0.1", args.port), status_handler_class(hub, static_dir)
        )
        http_worker = threading.Thread(target=http_server.serve_forever, daemon=True)
        http_worker.start()
        print(f"Research status: http://127.0.0.1:{args.port}/ui-preview/", flush=True)
        print("V5 analysis unavailable in the UI; no scored result is saved.", flush=True)
        if shadow is not None:
            print("Experimental V5 shadow inference enabled; output is not validated feedback.", flush=True)
        while not stop.is_set():
            completed = session.poll_completed_reps()
            now_ns = time.monotonic_ns()
            hub.publish(projector.refresh(
                now_monotonic_ns=now_ns, completed_reps=completed
            ))
            hub.publish_imu_window(projector.imu_window(now_monotonic_ns=now_ns))
            if shadow is not None:
                for rep in completed:
                    try:
                        outcome = shadow.evaluate(
                            rep,
                            exercise_id=args.exercise_id,
                            load_kg=args.load_kg,
                        )
                    except Exception as exc:
                        print(
                            f"SHADOW ONLY rep={rep.event.rep_number} unavailable "
                            f"runtime_error={type(exc).__name__}",
                            flush=True,
                        )
                    else:
                        print(
                            f"SHADOW ONLY rep={outcome.rep_number} state={outcome.state} "
                            f"reason={outcome.reason or 'none'}",
                            flush=True,
                        )
            try:
                await asyncio.wait_for(stop.wait(), timeout=0.25)
            except TimeoutError:
                pass
    finally:
        if http_server is not None:
            http_server.shutdown()
            http_server.server_close()
        if http_worker is not None:
            http_worker.join(timeout=2)
        await vision_server.close()
        await imu_server.close()
        if begun:
            await session.stop(
                session_uuid=session_uuid,
                ended_monotonic_ns=time.monotonic_ns(),
                ended_utc_ms=time.time_ns() // 1_000_000,
            )
        await session.close(checkpoint_monotonic_ns=time.monotonic_ns())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--imu-socket", type=Path, required=True)
    parser.add_argument("--vision-socket", type=Path, required=True)
    parser.add_argument("--edge-device-id", required=True)
    parser.add_argument("--imu-device-id", required=True)
    parser.add_argument("--exercise-id", type=int, choices=(0, 1), required=True)
    parser.add_argument("--shadow-v5-package", type=Path)
    parser.add_argument("--load-kg", type=float)
    parser.add_argument("--port", type=int, default=8766)
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("port must be 1..65535")
    if (args.shadow_v5_package is None) != (args.load_kg is None):
        parser.error("--shadow-v5-package and --load-kg must be provided together")
    if args.load_kg is not None and (not math.isfinite(args.load_kg) or args.load_kg < 0):
        parser.error("--load-kg must be a finite non-negative number")
    try:
        asyncio.run(run(args))
    except (OSError, RuntimeError, ValueError) as exc:
        parser.exit(2, f"Research session unavailable: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
