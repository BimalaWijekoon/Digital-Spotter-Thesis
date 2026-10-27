#!/usr/bin/env python3
"""Run the canonical Pi workout UI/core with explicitly unavailable unverified scores."""
from __future__ import annotations
import argparse
import asyncio
import csv
import json
import os
import signal
import threading
import time
from http.server import ThreadingHTTPServer
from pathlib import Path

from digital_spotter.api.workout import WorkoutHub, is_private_research_origin, workout_handler
from digital_spotter.core import LocalSessionService, UnixIMUEventServer, UnixVisionEventServer
from digital_spotter.core.workout import WorkoutService
from digital_spotter.inference.v5_model import V5ModelRuntime
from digital_spotter.inference.v5_model import MODEL_VERSION
from digital_spotter.inference.v5_candidate import CANDIDATE_VERSION, V5CandidateRuntime
from digital_spotter.inference.v5_demo import DemoReplay
from digital_spotter.inference.v5_preprocessing import verify_copied_file
from digital_spotter.persistence import SQLiteRepository, migrate_database
from digital_spotter.feedback import FeedbackCoordinator
from digital_spotter.feedback.pi_gpio import PiGPIOFeedback
from digital_spotter.feedback.uds import UnixWearableCueClient
from digital_spotter.observability.network import LinuxWiFiProbe


def load_model_runtime(package, model_version=MODEL_VERSION):
    if model_version == MODEL_VERSION:
        return V5ModelRuntime(package)
    if model_version == CANDIDATE_VERSION:
        return V5CandidateRuntime(package)
    raise ValueError('unknown model version')


def model_reference(runtime, package):
    if runtime.model_version == MODEL_VERSION:
        with (package / 'COPY_MANIFEST.csv').open(newline='') as handle:
            for row in csv.DictReader(handle):
                verify_copied_file(package, row['destination_path'])
    phases, context = runtime.preprocessor.reference_inputs()
    prediction = runtime.predict_reference_only(phases, context)
    return {'version': 'v5_test_input_v1', 'source': 'frozen_fitted_medians',
            'live': False, 'reference_only': prediction.reference_only,
            'model_version': prediction.model_version, 'raw_probability': prediction.raw_probability,
            'calibrated_probability': prediction.calibrated_probability,
            'threshold': prediction.threshold, 'predicted_class': prediction.predicted_class}


async def run(args):
    args.run_dir.mkdir(mode=0o700, parents=True, exist_ok=False)
    socket_dir = args.socket_dir or args.run_dir
    socket_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    database = args.run_dir / 'workouts.sqlite3'
    migrate_database(database)  # A new isolated file; never migrate/overwrite earlier data.
    model = load_model_runtime(args.model_package, args.model_version)
    reference = model_reference(model, args.model_package)
    print(json.dumps({'event': 'v5_loaded', 'reference_only': True, **reference}), flush=True)
    feedback = None
    if args.enable_demo_feedback:
        pi_feedback = PiGPIOFeedback(
            red_pin=args.pi_rgb_pins[0], green_pin=args.pi_rgb_pins[1],
            blue_pin=args.pi_rgb_pins[2], buzzer_pin=args.pi_buzzer_pin,
            common_anode=args.pi_rgb_common_anode,
        )
        await pi_feedback.open()
        feedback = FeedbackCoordinator(
            pi=pi_feedback,
            wearable=UnixWearableCueClient(socket_dir / 'imu-control.sock'),
            enabled=True,
        )
    service = WorkoutService(session=LocalSessionService(repository=SQLiteRepository(database),
        imu_ring_capacity=1500), repository=SQLiteRepository(database), model=model,
        edge_device_id=args.edge_device_id, imu_device_id=args.imu_device_id,
        log_path=args.run_dir / 'inference.jsonl', reference_result=reference,
        demo=DemoReplay(model) if args.enable_demo else None, feedback=feedback,
        network_probe=LinuxWiFiProbe(interface=args.wifi_interface))
    await service.open()
    hub = WorkoutHub()
    hub.publish(service)
    imu = UnixIMUEventServer(socket_path=socket_dir / 'imu.sock',
        on_event=service.accept_imu, allowed_uids=frozenset({os.getuid()}), socket_mode=0o600)
    vision = UnixVisionEventServer(socket_path=socket_dir / 'vision.sock',
        on_pose=service.accept_pose, allowed_uids=frozenset({os.getuid()}))
    await imu.start()
    await vision.start()
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for name in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(name, stop.set)
    static = Path(__file__).resolve().parents[1] / 'src/digital_spotter/web/static'
    origins = frozenset(args.allowed_origin)
    if any(not is_private_research_origin(origin) for origin in origins):
        raise ValueError('only private loopback or Tailscale HTTPS origins are allowed')
    server = ThreadingHTTPServer(('127.0.0.1', args.port),
        workout_handler(hub, service, loop, static, origins=origins))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    print(f'WORKOUT_READY http://127.0.0.1:{args.port}/ui-preview/', flush=True)
    last_checkpoint = time.monotonic()
    try:
        while not stop.is_set():
            service.tick()
            hub.publish(service)
            if service.state in ('active', 'paused') and time.monotonic() - last_checkpoint >= 5:
                await service.session.checkpoint(now_monotonic_ns=time.monotonic_ns())
                last_checkpoint = time.monotonic()
            try:
                await asyncio.wait_for(stop.wait(), timeout=0.25)
            except TimeoutError:
                pass
    finally:
        await asyncio.to_thread(server.shutdown)
        server.server_close()
        thread.join(timeout=2)
        await vision.close()
        await imu.close()
        await service.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-dir', type=Path, required=True)
    parser.add_argument('--socket-dir', type=Path,
                        help='Stable local UDS directory; defaults to the run directory')
    parser.add_argument('--model-package', type=Path, required=True)
    parser.add_argument('--model-version', choices=(MODEL_VERSION, CANDIDATE_VERSION), default=MODEL_VERSION)
    parser.add_argument('--enable-demo', action='store_true',
                        help='Enable isolated synthetic V5 replay inference')
    parser.add_argument('--enable-demo-feedback', action='store_true',
                        help='Enable bounded Pi/wearable feedback for demo inference')
    parser.add_argument('--pi-rgb-pins', type=int, nargs=3, metavar=('R', 'G', 'B'),
                        default=(27, 17, 22))
    parser.add_argument('--pi-buzzer-pin', type=int, default=18)
    parser.add_argument('--pi-rgb-common-anode', action='store_true')
    parser.add_argument('--wifi-interface', default='wlan0')
    parser.add_argument('--edge-device-id', required=True)
    parser.add_argument('--imu-device-id', required=True)
    parser.add_argument('--port', type=int, default=8766)
    parser.add_argument('--allowed-origin', action='append', default=['http://127.0.0.1:4174'])
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error('invalid port')
    if args.enable_demo and args.model_version != CANDIDATE_VERSION:
        parser.error('--enable-demo requires the explicitly selected synthetic V5 revision')
    if args.enable_demo_feedback and not args.enable_demo:
        parser.error('--enable-demo-feedback requires --enable-demo')
    asyncio.run(run(args))


if __name__ == '__main__':
    main()
