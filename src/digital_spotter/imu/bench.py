"""Bounded, non-persisting real-hardware bench for the provisioned BLE wearable."""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import sys
import time
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path

from digital_spotter.contracts import ClockState, MonotonicNanoseconds
from digital_spotter.imu.agent import IMUAgentCore
from digital_spotter.imu.bleak_transport import BleakWearableTransport
from digital_spotter.imu.clock import SensorClockMapper
from digital_spotter.imu.control import load_device_key
from digital_spotter.imu.control_client import WearableControlClient
from digital_spotter.imu.protocol import (
    DEVICE_INFO_UUID,
    IMU_STREAM_UUID,
    STATUS_UUID,
    IMUFlags,
    decode_imu_packet,
)
from digital_spotter.imu.runtime import read_provisioned_device_id


@dataclass(frozen=True)
class HardwareBenchSummary:
    evidence_environment: str
    hardware_simulated: bool
    identify_exercised: bool
    device_id: str
    firmware_version: str
    hardware_revision: str
    imu_model: str
    configured_rate_hz: int
    requested_duration_s: float
    observed_duration_s: float
    samples_received: int
    observed_sensor_rate_hz: float | None
    sequence_gaps: int
    packets_rejected: int
    notification_queue_drops: int
    sensor_error_samples: int
    saturated_samples: int
    calibrated_samples: int
    clock_state: str
    clock_drift_ppm: float | None
    clock_error_p95_ms: float | None
    clock_model_error_ms: float
    clock_fit_points: int
    clock_fit_rtt_max_ms: float | None
    clock_drift_observed: bool
    accepted_clock_exchanges: int
    rejected_clock_exchanges: int
    clock_rtt_min_ms: float | None
    clock_rtt_p50_ms: float | None
    clock_rtt_p95_ms: float | None
    clock_rtt_max_ms: float | None
    clock_causal_cap_samples: int
    clock_max_future_projection_ms: float
    status_sensor_errors: int
    status_sensor_error_delta: int
    status_sensor_retries: int
    status_sensor_retry_delta: int
    actuator_commands: int
    actuator_rejections: int
    actuator_rate_limits: int
    actuator_driver_errors: int
    actuator_driver_error_delta: int
    status_last_error_code: str | None
    initial_heap_free_bytes: int
    final_heap_free_bytes: int
    firmware_minimum_heap_free_bytes: int
    heap_decline_bytes: int
    passed: bool
    failed_checks: tuple[str, ...]


def _nearest_rank_p95(values: list[int]) -> int | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[max(0, math.ceil(0.95 * len(ordered)) - 1)]


def _nearest_rank_p50(values: list[int]) -> int | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[max(0, math.ceil(0.50 * len(ordered)) - 1)]


def _sensor_rate_hz(sensor_times_us: list[int]) -> float | None:
    if len(sensor_times_us) < 2:
        return None
    elapsed_us = 0
    previous = sensor_times_us[0]
    for current in sensor_times_us[1:]:
        delta = (current - previous) & 0xFFFFFFFF
        if delta == 0 or delta > 0x80000000:
            return None
        elapsed_us += delta
        previous = current
    if elapsed_us <= 0:
        return None
    return (len(sensor_times_us) - 1) * 1_000_000.0 / elapsed_us


def _failed_checks(
    *,
    configured_rate_hz: int,
    requested_duration_s: float,
    samples_received: int,
    observed_sensor_rate_hz: float | None,
    sequence_gaps: int,
    packets_rejected: int,
    notification_queue_drops: int,
    sensor_error_samples: int,
    status_sensor_error_delta: int,
    status_sensor_retry_delta: int,
    heap_decline_bytes: int,
    clock_state: ClockState,
    clock_error_p95_ns: int | None,
    require_calibrated: bool,
    calibrated_samples: int,
    actuator_driver_error_delta: int = 0,
) -> tuple[str, ...]:
    failed: list[str] = []
    minimum_samples = math.floor(configured_rate_hz * requested_duration_s * 0.90)
    if samples_received < minimum_samples:
        failed.append("sample_count_below_90_percent")
    if observed_sensor_rate_hz is None or not (
        configured_rate_hz * 0.98 <= observed_sensor_rate_hz <= configured_rate_hz * 1.02
    ):
        failed.append("sensor_rate_outside_2_percent")
    if sequence_gaps:
        failed.append("sequence_gaps_detected")
    if packets_rejected:
        failed.append("packets_rejected")
    if notification_queue_drops:
        failed.append("notification_queue_drops")
    if sensor_error_samples:
        failed.append("sensor_error_flag_seen")
    if status_sensor_error_delta:
        failed.append("status_sensor_errors_increased")
    if status_sensor_retry_delta:
        failed.append("status_sensor_retries_increased")
    if actuator_driver_error_delta:
        failed.append("actuator_driver_errors_increased")
    if heap_decline_bytes:
        failed.append("heap_declined")
    if clock_state is not ClockState.SYNCHRONIZED:
        failed.append("clock_not_synchronized")
    if clock_error_p95_ns is None or clock_error_p95_ns >= 20_000_000:
        failed.append("clock_error_p95_not_below_20_ms")
    if require_calibrated and calibrated_samples != samples_received:
        failed.append("calibration_required")
    return tuple(failed)


async def run_hardware_bench(args: argparse.Namespace) -> HardwareBenchSummary:
    device_id = read_provisioned_device_id(args.device_id_file)
    device_key = load_device_key(args.device_key_file)
    mapper = SensorClockMapper()
    transport = BleakWearableTransport(
        scan_timeout_s=args.scan_timeout,
        connect_timeout_s=args.connect_timeout,
    )
    core = IMUAgentCore(
        expected_device_id=device_id,
        max_buffer_samples=min(10_000, max(250, math.ceil(args.duration * 60))),
        clock_mapper=mapper,
    )
    control = WearableControlClient(
        transport=transport,
        device_key=device_key,
        device_id=device_id,
        clock_mapper=mapper,
    )
    imu_queue: asyncio.Queue[tuple[bytes, int]] = asyncio.Queue(maxsize=args.queue_size)
    status_queue: asyncio.Queue[bytes] = asyncio.Queue(maxsize=4)
    queue_drops = 0
    sensor_times_us: list[int] = []
    clock_errors_ns: list[int] = []
    flag_counts: Counter[IMUFlags] = Counter()
    accepted_clock_exchanges = 0
    stream_started = 0.0
    stream_stopped = 0.0
    streaming = False
    info = None
    status = None
    initial_status = None

    def on_imu(payload: bytes) -> None:
        nonlocal queue_drops
        if imu_queue.full():
            imu_queue.get_nowait()
            imu_queue.task_done()
            queue_drops += 1
        imu_queue.put_nowait((bytes(payload), time.monotonic_ns()))

    def on_status(payload: bytes) -> None:
        if status_queue.full():
            status_queue.get_nowait()
            status_queue.task_done()
        status_queue.put_nowait(bytes(payload))

    try:
        await transport.connect()
        info = core.accept_device_info(await transport.read(DEVICE_INFO_UUID))
        status = core.accept_status(await transport.read(STATUS_UUID))
        await control.open(status)
        await transport.start_notify(STATUS_UUID, on_status)
        await transport.start_notify(IMU_STREAM_UUID, on_imu)
        for exchange in range(args.initial_clock_exchanges):
            accepted_clock_exchanges += int(await control.time_sync())
            if exchange + 1 < args.initial_clock_exchanges:
                await asyncio.sleep(args.initial_clock_interval)
        if args.identify:
            await control.identify()
        initial_status = core.accept_status(await transport.read(STATUS_UUID))
        await control.set_streaming(True)
        streaming = True
        stream_started = time.monotonic()
        deadline = stream_started + args.duration
        next_clock_sync = stream_started + args.clock_sync_interval
        while time.monotonic() < deadline:
            while not status_queue.empty():
                status = core.accept_status(status_queue.get_nowait())
                status_queue.task_done()
            now = time.monotonic()
            if now >= next_clock_sync:
                accepted_clock_exchanges += int(await control.time_sync())
                next_clock_sync = now + args.clock_sync_interval
                continue
            timeout = max(0.001, min(1.0, deadline - now, next_clock_sync - now))
            try:
                packet, arrival_ns = await asyncio.wait_for(imu_queue.get(), timeout=timeout)
            except TimeoutError:
                continue
            try:
                decoded = decode_imu_packet(
                    packet,
                    scale_profile_version=status.scale_profile_version,
                )
                event = core.accept_packet(
                    packet,
                    arrival_monotonic_ns=MonotonicNanoseconds(arrival_ns),
                )
                if event is not None:
                    sensor_times_us.append(decoded.sensor_time_us)
                    clock_errors_ns.append(event.payload.estimated_clock_error_ns)
                    for flag in IMUFlags:
                        if decoded.flags & flag:
                            flag_counts[flag] += 1
            finally:
                imu_queue.task_done()
        stream_stopped = time.monotonic()
        accepted_clock_exchanges += int(await control.time_sync())
        await control.set_streaming(False)
        streaming = False
        await asyncio.sleep(0.2)
        status = core.accept_status(await transport.read(STATUS_UUID))
    finally:
        if transport.is_connected:
            if streaming:
                try:
                    accepted_clock_exchanges += int(await control.time_sync())
                    await control.set_streaming(False)
                except Exception:
                    pass
            for characteristic in (IMU_STREAM_UUID, STATUS_UUID):
                try:
                    await transport.stop_notify(characteristic)
                except Exception:
                    pass
            try:
                await control.close()
            finally:
                await transport.disconnect()

    if info is None or status is None or initial_status is None:
        raise RuntimeError("wearable identity/status was not established")
    counters = core.counters()
    observed_rate = _sensor_rate_hz(sensor_times_us)
    clock_p95_ns = _nearest_rank_p95(clock_errors_ns)
    clock_diagnostics = mapper.exchange_diagnostics
    clock_rtts_ns = [
        diagnostic.round_trip_ns
        for diagnostic in clock_diagnostics
        if diagnostic.round_trip_ns >= 0
    ]
    rejected_clock_exchanges = sum(
        not diagnostic.accepted for diagnostic in clock_diagnostics
    )
    clock_rtt_min_ns = min(clock_rtts_ns, default=None)
    clock_rtt_p50_ns = _nearest_rank_p50(clock_rtts_ns)
    clock_rtt_p95_ns = _nearest_rank_p95(clock_rtts_ns)
    clock_rtt_max_ns = max(clock_rtts_ns, default=None)
    status_sensor_error_delta = max(0, status.sensor_errors - initial_status.sensor_errors)
    status_sensor_retry_delta = max(0, status.sensor_retries - initial_status.sensor_retries)
    actuator_driver_error_delta = max(
        0,
        status.actuator_driver_errors - initial_status.actuator_driver_errors,
    )
    heap_decline_bytes = max(0, initial_status.heap_free_bytes - status.heap_free_bytes)
    failed = _failed_checks(
        configured_rate_hz=info.sample_rate_hz,
        requested_duration_s=args.duration,
        samples_received=len(sensor_times_us),
        observed_sensor_rate_hz=observed_rate,
        sequence_gaps=counters.sequence_gaps,
        packets_rejected=counters.packets_rejected,
        notification_queue_drops=queue_drops,
        sensor_error_samples=flag_counts[IMUFlags.SENSOR_ERROR],
        status_sensor_error_delta=status_sensor_error_delta,
        status_sensor_retry_delta=status_sensor_retry_delta,
        heap_decline_bytes=heap_decline_bytes,
        clock_state=mapper.state,
        clock_error_p95_ns=clock_p95_ns,
        require_calibrated=args.require_calibrated,
        calibrated_samples=flag_counts[IMUFlags.CALIBRATED],
        actuator_driver_error_delta=actuator_driver_error_delta,
    )
    return HardwareBenchSummary(
        evidence_environment="E3_real_hardware",
        hardware_simulated=False,
        identify_exercised=args.identify,
        device_id=info.device_id,
        firmware_version=info.firmware_version,
        hardware_revision=info.hardware_revision,
        imu_model=info.imu_model,
        configured_rate_hz=info.sample_rate_hz,
        requested_duration_s=args.duration,
        observed_duration_s=max(0.0, stream_stopped - stream_started),
        samples_received=len(sensor_times_us),
        observed_sensor_rate_hz=observed_rate,
        sequence_gaps=counters.sequence_gaps,
        packets_rejected=counters.packets_rejected,
        notification_queue_drops=queue_drops,
        sensor_error_samples=flag_counts[IMUFlags.SENSOR_ERROR],
        saturated_samples=flag_counts[IMUFlags.SATURATED],
        calibrated_samples=flag_counts[IMUFlags.CALIBRATED],
        clock_state=mapper.state.value,
        clock_drift_ppm=mapper.drift_ppm,
        clock_error_p95_ms=None if clock_p95_ns is None else clock_p95_ns / 1_000_000.0,
        clock_model_error_ms=mapper.estimated_error_ns / 1_000_000.0,
        clock_fit_points=mapper.fit_point_count,
        clock_fit_rtt_max_ms=(
            None
            if mapper.fit_rtt_max_ns is None
            else mapper.fit_rtt_max_ns / 1_000_000.0
        ),
        clock_drift_observed=mapper.drift_observed,
        accepted_clock_exchanges=accepted_clock_exchanges,
        rejected_clock_exchanges=rejected_clock_exchanges,
        clock_rtt_min_ms=None if clock_rtt_min_ns is None else clock_rtt_min_ns / 1_000_000.0,
        clock_rtt_p50_ms=None if clock_rtt_p50_ns is None else clock_rtt_p50_ns / 1_000_000.0,
        clock_rtt_p95_ms=None if clock_rtt_p95_ns is None else clock_rtt_p95_ns / 1_000_000.0,
        clock_rtt_max_ms=None if clock_rtt_max_ns is None else clock_rtt_max_ns / 1_000_000.0,
        clock_causal_cap_samples=mapper.causal_cap_samples,
        clock_max_future_projection_ms=mapper.max_future_projection_ns / 1_000_000.0,
        status_sensor_errors=status.sensor_errors,
        status_sensor_error_delta=status_sensor_error_delta,
        status_sensor_retries=status.sensor_retries,
        status_sensor_retry_delta=status_sensor_retry_delta,
        actuator_commands=status.actuator_commands,
        actuator_rejections=status.actuator_rejections,
        actuator_rate_limits=status.actuator_rate_limits,
        actuator_driver_errors=status.actuator_driver_errors,
        actuator_driver_error_delta=actuator_driver_error_delta,
        status_last_error_code=status.last_error_code,
        initial_heap_free_bytes=initial_status.heap_free_bytes,
        final_heap_free_bytes=status.heap_free_bytes,
        firmware_minimum_heap_free_bytes=status.heap_minimum_free_bytes,
        heap_decline_bytes=heap_decline_bytes,
        passed=not failed,
        failed_checks=failed,
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ds-imu-bench")
    parser.add_argument("--device-id-file", type=Path, required=True)
    parser.add_argument("--device-key-file", type=Path, required=True)
    parser.add_argument("--duration", type=float, default=10.0)
    parser.add_argument("--scan-timeout", type=float, default=15.0)
    parser.add_argument("--connect-timeout", type=float, default=30.0)
    parser.add_argument("--queue-size", type=int, default=512)
    parser.add_argument("--initial-clock-exchanges", type=int, default=8)
    parser.add_argument("--initial-clock-interval", type=float, default=0.1)
    parser.add_argument("--clock-sync-interval", type=float, default=3.0)
    parser.add_argument("--require-calibrated", action="store_true")
    parser.add_argument(
        "--identify",
        action="store_true",
        help="exercise the authenticated non-blocking identify cue before streaming",
    )
    return parser


def _validate_args(args: argparse.Namespace) -> None:
    if not 2.0 <= args.duration <= 3600.0:
        raise ValueError("duration must be between 2 and 3600 seconds")
    if not 1.0 <= args.scan_timeout <= 120.0:
        raise ValueError("scan timeout must be between 1 and 120 seconds")
    if not 1.0 <= args.connect_timeout <= 120.0:
        raise ValueError("connect timeout must be between 1 and 120 seconds")
    if not 64 <= args.queue_size <= 4096:
        raise ValueError("queue size must be between 64 and 4096")
    if not 5 <= args.initial_clock_exchanges <= 20:
        raise ValueError("initial clock exchanges must be between 5 and 20")
    if not 0.01 <= args.initial_clock_interval <= 1.0:
        raise ValueError("initial clock interval must be between 0.01 and 1 second")
    if not 1.0 <= args.clock_sync_interval <= 4.0:
        raise ValueError("clock sync interval must be between 1 and 4 seconds")


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        _validate_args(args)
        summary = asyncio.run(run_hardware_bench(args))
    except Exception as exc:
        print(f"IMU hardware bench failed: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(asdict(summary), sort_keys=True, indent=2))
    return 0 if summary.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
