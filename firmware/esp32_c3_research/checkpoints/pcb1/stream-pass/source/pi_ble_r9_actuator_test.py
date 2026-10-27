#!/usr/bin/env python3
"""Validate R9 non-blocking cues against the frozen real-MPU6500 BLE stream."""

from __future__ import annotations

import argparse
import asyncio
import math
import re
import struct
import time
from dataclasses import dataclass

from bleak import BleakClient, BleakScanner


DEVICE_NAME = "ESP32-C3-Test"
DEVICE_ADDRESS = "50:78:7D:92:61:1A"
DEVICE_INFO_CHARACTERISTIC_UUID = "e193acb8-25ef-422c-b3e5-972eae75b8ea"
CONTROL_CHARACTERISTIC_UUID = "7f725422-d560-4852-96d8-3407f417b1d8"
STREAM_CHARACTERISTIC_UUID = "772af3c3-f1f9-43b0-8230-4dff401446ea"
STATUS_CHARACTERISTIC_UUID = "7f07eb06-7be4-49a1-b952-1ed033b0dfc7"

EXPECTED_DEVICE_INFO = (
    b"protocol=1;firmware=0.9.0-r9;hardware=esp32-c3;imu=mpu6500;rate_hz=50"
)
SUPPORTED_DEVICE_INFO = frozenset({
    EXPECTED_DEVICE_INFO,
    b"protocol=1;firmware=0.9.1-pcb1;hardware=esp32-c3;imu=mpu6500;rate_hz=50",
})
STATUS_PATTERN = re.compile(
    rb"^state=(idle|streaming|error);i2c_errors=(\d+);"
    rb"samples_sent=(\d+);uptime_ms=(\d+)$"
)
STREAM_PACKET = struct.Struct("<BBHIhhhhhh")
STREAM_PACKET_SIZE = 20
STATUS_MAX_VALUE_BYTES = 96
MINIMUM_RATE_HZ = 48.0
MAXIMUM_RATE_HZ = 52.0
MINIMUM_SENSOR_INTERVAL_US = 10_000
MAXIMUM_SENSOR_INTERVAL_US = 30_000
CUE_TEST_DURATION_SECONDS = 6 * 0.9


@dataclass(frozen=True)
class Status:
    state: str
    i2c_errors: int
    samples_sent: int
    uptime_ms: int


@dataclass(frozen=True)
class StreamSample:
    arrival_ns: int
    sequence: int
    sensor_time_us: int
    acceleration_raw: tuple[int, int, int]
    angular_velocity_raw: tuple[int, int, int]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)
    print(f"[ASSERT] PASS — {message}")


def parse_status(payload: bytes) -> Status:
    require(len(payload) <= STATUS_MAX_VALUE_BYTES, "status payload is bounded")
    match = STATUS_PATTERN.fullmatch(payload)
    require(match is not None, "status payload matches the strict R9 schema")
    assert match is not None
    return Status(
        state=match.group(1).decode("ascii"),
        i2c_errors=int(match.group(2)),
        samples_sent=int(match.group(3)),
        uptime_ms=int(match.group(4)),
    )


async def read_status(client: BleakClient, label: str) -> Status:
    payload = bytes(await client.read_gatt_char(STATUS_CHARACTERISTIC_UUID))
    print(f"[STATUS] label={label} value={payload.decode(errors='replace')}")
    return parse_status(payload)


async def send_control(
    client: BleakClient,
    request: bytes,
    expected_response: bytes,
) -> None:
    await client.write_gatt_char(
        CONTROL_CHARACTERISTIC_UUID,
        request,
        response=True,
    )
    response = bytes(await client.read_gatt_char(CONTROL_CHARACTERISTIC_UUID))
    print(
        f"[CONTROL] request={request!r} "
        f"response={response.decode(errors='replace')!r}"
    )
    require(response == expected_response, f"control response for {request!r} matches")


async def find_device():
    print(f"[SCAN] Looking for {DEVICE_NAME!r}...")
    device = await BleakScanner.find_device_by_name(DEVICE_NAME, timeout=15.0)
    require(device is not None, "expected BLE name was discovered")
    assert device is not None
    require(
        device.address.casefold() == DEVICE_ADDRESS.casefold(),
        "device address matches the hardware contract",
    )
    return device


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--duration", type=float, default=30.0)
    parser.add_argument(
        "--cue-demo",
        action="store_true",
        help="run the short owner-observation sequence instead of validation",
    )
    arguments = parser.parse_args()
    if arguments.duration < 10.0 or arguments.duration > 60.0:
        parser.error("--duration must be in the range 10..60 seconds")
    return arguments


async def run_validation(duration_seconds: float) -> None:
    samples: list[StreamSample] = []
    stream_errors: list[str] = []
    first_notification = asyncio.Event()
    unexpected_disconnects = 0
    streaming_expected = False

    def disconnected_handler(_client: BleakClient) -> None:
        nonlocal unexpected_disconnects
        if streaming_expected:
            unexpected_disconnects += 1

    def notification_handler(_sender: object, data: bytearray) -> None:
        payload = bytes(data)
        if len(payload) != STREAM_PACKET_SIZE:
            stream_errors.append(f"length={len(payload)}")
            first_notification.set()
            return
        fields = STREAM_PACKET.unpack(payload)
        if fields[0] != 1 or fields[1] != 0:
            stream_errors.append(
                f"protocol={fields[0]} flags=0x{fields[1]:02x}"
            )
            first_notification.set()
            return
        samples.append(StreamSample(
            time.monotonic_ns(), fields[2], fields[3],
            tuple(fields[4:7]), tuple(fields[7:10]),
        ))
        first_notification.set()

    device = await find_device()
    client = BleakClient(
        device,
        timeout=20.0,
        pair=False,
        disconnected_callback=disconnected_handler,
    )

    async with client:
        require(client.is_connected, "plain BLE connection is active")
        device_info = bytes(
            await client.read_gatt_char(DEVICE_INFO_CHARACTERISTIC_UUID)
        )
        print(f"[DEVICE_INFO] {device_info.decode(errors='replace')}")
        require(device_info in SUPPORTED_DEVICE_INFO, "known R9/PCB1 device info is exact")

        initial_status = await read_status(client, "initial")
        require(initial_status.state == "idle", "new connection starts idle")
        require(initial_status.i2c_errors == 0, "initial status has no I2C errors")

        await client.start_notify(STREAM_CHARACTERISTIC_UUID, notification_handler)
        await asyncio.sleep(0.4)
        require(not samples, "idle state emits no stream notifications")

        streaming_expected = True
        await send_control(client, b"stream:start", b"ok:streaming")
        await asyncio.wait_for(first_notification.wait(), timeout=5.0)
        streaming_status = await read_status(client, "streaming")
        require(streaming_status.state == "streaming", "status reports streaming")

        measure_started_ns = time.monotonic_ns()
        sample_start_index = len(samples)

        await asyncio.sleep(5.0)
        await send_control(client, b"cue:test", b"error:busy_streaming")
        await asyncio.sleep(5.0)
        await send_control(client, b"buzzer:test", b"ok:buzzer_test")
        await asyncio.sleep(5.0)
        await send_control(client, b"identify", b"ok:identify")

        elapsed = (time.monotonic_ns() - measure_started_ns) / 1_000_000_000.0
        await asyncio.sleep(max(0.0, duration_seconds - elapsed))
        measure_ended_ns = time.monotonic_ns()
        sample_end_index = len(samples)

        final_streaming_status = await read_status(client, "streaming-final")
        require(
            final_streaming_status.state == "streaming",
            "manual buzzer and deferred identify do not stop streaming",
        )
        require(
            final_streaming_status.samples_sent > streaming_status.samples_sent,
            "status samples_sent increases during streaming",
        )

        measured_samples = samples[sample_start_index:sample_end_index]
        require(not stream_errors, "stream has no packet/protocol errors")
        minimum_samples = int(duration_seconds * 45.0)
        require(
            len(measured_samples) >= minimum_samples,
            f"received at least {minimum_samples} concurrent stream samples",
        )

        sequence_deltas = [
            (current.sequence - previous.sequence) & 0xFFFF
            for previous, current in zip(measured_samples, measured_samples[1:])
        ]
        timestamp_deltas = [
            (current.sensor_time_us - previous.sensor_time_us) & 0xFFFFFFFF
            for previous, current in zip(measured_samples, measured_samples[1:])
        ]
        out_of_bound_timestamp_deltas = [
            (index + 1, delta)
            for index, delta in enumerate(timestamp_deltas)
            if not MINIMUM_SENSOR_INTERVAL_US <= delta <= MAXIMUM_SENSOR_INTERVAL_US
        ]
        print(
            "[TIMING] "
            f"samples={len(measured_samples)} "
            f"sensor_interval_min_us={min(timestamp_deltas)} "
            f"sensor_interval_max_us={max(timestamp_deltas)} "
            f"out_of_bound_count={len(out_of_bound_timestamp_deltas)} "
            f"first_out_of_bound={out_of_bound_timestamp_deltas[:10]}"
        )
        require(all(delta == 1 for delta in sequence_deltas), "sequence has zero gaps")
        require(
            all(
                MINIMUM_SENSOR_INTERVAL_US <= delta <= MAXIMUM_SENSOR_INTERVAL_US
                for delta in timestamp_deltas
            ),
            "sensor intervals remain within the R6 bound",
        )

        elapsed_seconds = (
            measure_ended_ns - measure_started_ns
        ) / 1_000_000_000.0
        rate_hz = len(measured_samples) / elapsed_seconds
        require(
            MINIMUM_RATE_HZ <= rate_hz <= MAXIMUM_RATE_HZ,
            "concurrent notification rate remains approximately 50 Hz",
        )
        require(unexpected_disconnects == 0, "no unexpected disconnect occurred")

        await send_control(client, b"stream:stop", b"ok:idle")
        streaming_expected = False
        await asyncio.sleep(1.1)
        stopped_count = len(samples)
        await asyncio.sleep(0.3)
        require(len(samples) == stopped_count, "stopped state remains notification-silent")

        await send_control(client, b"cue:test", b"ok:cue_test")
        await asyncio.sleep(CUE_TEST_DURATION_SECONDS + 0.4)
        final_status = await read_status(client, "final-idle")
        require(final_status.state == "idle", "cue test returns to idle")
        require(final_status.i2c_errors == 0, "final status has no I2C errors")
        require(unexpected_disconnects == 0, "cue test does not disconnect BLE")
        await client.stop_notify(STREAM_CHARACTERISTIC_UUID)

        print("[SUMMARY]")
        print(f"  duration_seconds={elapsed_seconds:.6f}")
        print(f"  samples={len(measured_samples)}")
        print(f"  notification_rate_hz={rate_hz:.6f}")
        print(f"  sequence_gaps={sum(delta != 1 for delta in sequence_deltas)}")
        print(f"  sensor_interval_min_us={min(timestamp_deltas)}")
        print(f"  sensor_interval_max_us={max(timestamp_deltas)}")
        print(f"  i2c_errors={final_status.i2c_errors}")
        print(f"  samples_sent={final_status.samples_sent}")
        print(f"  unexpected_disconnects={unexpected_disconnects}")
        for label, attribute in (
            ("acceleration_raw", "acceleration_raw"),
            ("angular_velocity_raw", "angular_velocity_raw"),
        ):
            ranges = [
                (min(getattr(sample, attribute)[axis] for sample in measured_samples),
                 max(getattr(sample, attribute)[axis] for sample in measured_samples))
                for axis in range(3)
            ]
            print(f"  {label}_ranges={ranges}")
        magnitudes = [
            math.sqrt(sum((axis / 16384.0) ** 2 for axis in sample.acceleration_raw))
            for sample in measured_samples
        ]
        print(f"  acceleration_magnitude_g_range=({min(magnitudes):.4f}, {max(magnitudes):.4f})")

    require(not client.is_connected, "client disconnected cleanly")
    print("TEST RESULT: PASS")


async def run_cue_demo() -> None:
    device = await find_device()
    client = BleakClient(device, timeout=20.0, pair=False)
    await client.connect()
    try:
        require(client.is_connected, "plain BLE connection is active")
        device_info = bytes(
            await client.read_gatt_char(DEVICE_INFO_CHARACTERISTIC_UUID)
        )
        require(device_info in SUPPORTED_DEVICE_INFO, "known R9/PCB1 device info is exact")

        print("[DEMO] Connected idle: green for 1.5 seconds")
        await asyncio.sleep(1.5)
        print(
            "[DEMO] Cue test: white, blue, green, cyan, orange, red "
            "(0.9 seconds each)"
        )
        await send_control(client, b"cue:test", b"ok:cue_test")
        await asyncio.sleep(CUE_TEST_DURATION_SECONDS + 0.5)

        print("[DEMO] Natural streaming state: steady cyan for 2 seconds")
        await send_control(client, b"stream:start", b"ok:streaming")
        await asyncio.sleep(1.0)
        print("[DEMO] Manual buzzer: one short beep")
        await send_control(client, b"buzzer:test", b"ok:buzzer_test")
        await asyncio.sleep(1.0)
        await send_control(client, b"stream:stop", b"ok:idle")
        print("[DEMO] Connected idle: green for 1 second")
        await asyncio.sleep(1.0)
    finally:
        if client.is_connected:
            print("[DEMO] Disconnect: orange flash, then blue advertising breath")
            await client.disconnect()
            await asyncio.sleep(2.0)

    print("CUE DEMO COMPLETE — report the colors and beep you observed")


def main() -> None:
    arguments = parse_arguments()
    try:
        if arguments.cue_demo:
            asyncio.run(run_cue_demo())
        else:
            asyncio.run(run_validation(arguments.duration))
    except KeyboardInterrupt:
        print("\nTEST RESULT: STOPPED")
        raise SystemExit(130)
    except Exception as error:
        print(f"TEST RESULT: FAIL — {type(error).__name__}: {error}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
