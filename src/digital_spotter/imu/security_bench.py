"""Non-persisting E3 application-authentication and replay rejection bench."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import secrets
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

from digital_spotter.imu.bleak_transport import BleakWearableTransport
from digital_spotter.imu.control import (
    AuthenticatedCommand,
    ControlProtocolError,
    decode_response,
    derive_session_key,
    encode_command,
    load_device_key,
    sensor_window,
)
from digital_spotter.imu.protocol import CONTROL_UUID, STATUS_UUID, parse_wearable_status
from digital_spotter.imu.runtime import read_provisioned_device_id


@dataclass(frozen=True)
class SecurityBenchSummary:
    evidence_environment: str
    hardware_simulated: bool
    device_id: str
    valid_authentication_accepted: bool
    captured_command_replay_rejected: bool
    captured_feedback_replay_rejected: bool
    feedback_applied_once: bool
    wrong_key_rejected: bool
    passed: bool


async def _next_response(queue: asyncio.Queue[bytes], timeout_s: float) -> bytes:
    try:
        value = await asyncio.wait_for(queue.get(), timeout=timeout_s)
    except TimeoutError as exc:
        raise ControlProtocolError("security bench response timed out") from exc
    queue.task_done()
    return value


async def run_security_bench(
    *,
    device_id: str,
    device_key: bytes,
    timeout_s: float = 3.0,
) -> SecurityBenchSummary:
    transport = BleakWearableTransport()
    responses: asyncio.Queue[bytes] = asyncio.Queue(maxsize=4)

    def on_response(payload: bytes) -> None:
        if responses.full():
            responses.get_nowait()
            responses.task_done()
        responses.put_nowait(bytes(payload))

    valid_accepted = False
    replay_rejected = False
    feedback_replay_rejected = False
    feedback_applied_once = False
    try:
        await transport.connect()
        status = parse_wearable_status(await transport.read(STATUS_UUID))
        if status.device_id != device_id or status.state == "unprovisioned":
            raise ControlProtocolError("wearable identity is not provisioned for this Pi")
        await transport.start_notify(CONTROL_UUID, on_response)
        command = AuthenticatedCommand(
            command_id=secrets.randbits(64),
            command="authenticate",
            session_nonce=secrets.token_bytes(16),
            issued_sensor_window=None,
            arguments={"boot_id": status.boot_id},
        )
        captured = encode_command(command, key=device_key)
        await transport.write(CONTROL_UUID, captured, response=True)
        first = decode_response(await _next_response(responses, timeout_s), key=device_key)
        valid_accepted = first.command_id == command.command_id and first.result == "accepted"

        response_boot = first.arguments.get("boot_id")
        response_sensor_time = first.arguments.get("sensor_time_us")
        if (
            isinstance(response_boot, bool)
            or not isinstance(response_boot, int)
            or response_boot != status.boot_id
            or isinstance(response_sensor_time, bool)
            or not isinstance(response_sensor_time, int)
        ):
            raise ControlProtocolError("authentication response did not establish a session")
        session_key = derive_session_key(
            device_key=device_key,
            session_nonce=command.session_nonce,
            device_id=device_id,
            boot_id=response_boot,
        )

        await transport.write(CONTROL_UUID, captured, response=True)
        replay = decode_response(await _next_response(responses, timeout_s), key=device_key)
        replay_rejected = replay.command_id == command.command_id and replay.result == "replayed"

        before_feedback = parse_wearable_status(await transport.read(STATUS_UUID))
        feedback = AuthenticatedCommand(
            command_id=secrets.randbits(64),
            command="feedback",
            session_nonce=command.session_nonce,
            issued_sensor_window=sensor_window(response_sensor_time),
            arguments={"cue": "good"},
        )
        captured_feedback = encode_command(feedback, key=session_key)
        await transport.write(CONTROL_UUID, captured_feedback, response=True)
        feedback_first = decode_response(
            await _next_response(responses, timeout_s),
            key=session_key,
        )
        await transport.write(CONTROL_UUID, captured_feedback, response=True)
        feedback_replay = decode_response(
            await _next_response(responses, timeout_s),
            key=session_key,
        )
        after_feedback = parse_wearable_status(await transport.read(STATUS_UUID))
        feedback_replay_rejected = (
            feedback_replay.command_id == feedback.command_id
            and feedback_replay.result == "replayed"
        )
        feedback_applied_once = (
            feedback_first.command_id == feedback.command_id
            and feedback_first.result == "accepted"
            and after_feedback.actuator_commands == before_feedback.actuator_commands + 1
        )
    finally:
        try:
            if transport.is_connected:
                await transport.stop_notify(CONTROL_UUID)
        except Exception:
            pass
        finally:
            await transport.disconnect()

    wrong_transport = BleakWearableTransport()
    wrong_responses: asyncio.Queue[bytes] = asyncio.Queue(maxsize=1)
    wrong_key_rejected = False
    try:
        await wrong_transport.connect()
        status = parse_wearable_status(await wrong_transport.read(STATUS_UUID))
        await wrong_transport.start_notify(CONTROL_UUID, wrong_responses.put_nowait)
        wrong_key = hashlib.sha256(device_key + b"digital-spotter-wrong-key-test").digest()
        wrong = encode_command(
            AuthenticatedCommand(
                command_id=secrets.randbits(64),
                command="authenticate",
                session_nonce=secrets.token_bytes(16),
                issued_sensor_window=None,
                arguments={"boot_id": status.boot_id},
            ),
            key=wrong_key,
        )
        try:
            await wrong_transport.write(CONTROL_UUID, wrong, response=True)
            response = await asyncio.wait_for(wrong_responses.get(), timeout=1.0)
            wrong_responses.task_done()
            try:
                decode_response(response, key=wrong_key)
            except ControlProtocolError:
                wrong_key_rejected = True
        except (Exception, TimeoutError):
            wrong_key_rejected = True
    finally:
        try:
            if wrong_transport.is_connected:
                await wrong_transport.stop_notify(CONTROL_UUID)
        except Exception:
            pass
        finally:
            await wrong_transport.disconnect()

    return SecurityBenchSummary(
        evidence_environment="E3_real_hardware",
        hardware_simulated=False,
        device_id=device_id,
        valid_authentication_accepted=valid_accepted,
        captured_command_replay_rejected=replay_rejected,
        captured_feedback_replay_rejected=feedback_replay_rejected,
        feedback_applied_once=feedback_applied_once,
        wrong_key_rejected=wrong_key_rejected,
        passed=(
            valid_accepted
            and replay_rejected
            and feedback_replay_rejected
            and feedback_applied_once
            and wrong_key_rejected
        ),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ds-imu-security-bench")
    parser.add_argument("--device-id-file", type=Path, required=True)
    parser.add_argument("--device-key-file", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        summary = asyncio.run(
            run_security_bench(
                device_id=read_provisioned_device_id(args.device_id_file),
                device_key=load_device_key(args.device_key_file),
            )
        )
    except Exception as exc:
        print(f"IMU security bench failed: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(asdict(summary), sort_keys=True, indent=2))
    return 0 if summary.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
