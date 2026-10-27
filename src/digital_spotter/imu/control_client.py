"""Authenticated BLE control-session client for the provisioned wearable."""

from __future__ import annotations

import asyncio
import secrets
import time
from typing import Protocol

from digital_spotter.contracts import MonotonicNanoseconds
from digital_spotter.imu.clock import SensorClockMapper
from digital_spotter.imu.control import (
    AuthenticatedCommand,
    AuthenticatedResponse,
    ControlProtocolError,
    decode_response,
    derive_session_key,
    encode_command,
    sensor_window,
)
from digital_spotter.imu.protocol import CONTROL_UUID, WearableStatus


class ControlTransport(Protocol):
    async def start_notify(self, characteristic_uuid: str, callback) -> None: ...
    async def stop_notify(self, characteristic_uuid: str) -> None: ...
    async def write(self, characteristic_uuid: str, data: bytes, *, response: bool) -> None: ...


class WearableControlClient:
    """Serialize command exchanges and verify every logical response."""

    def __init__(
        self,
        *,
        transport: ControlTransport,
        device_key: bytes,
        device_id: str,
        clock_mapper: SensorClockMapper,
        response_timeout_s: float = 3.0,
    ):
        if response_timeout_s <= 0 or response_timeout_s > 30:
            raise ValueError("control response timeout must be between 0 and 30 seconds")
        self.transport = transport
        self.device_key = device_key
        self.device_id = device_id
        self.clock_mapper = clock_mapper
        self.response_timeout_s = response_timeout_s
        self._responses: asyncio.Queue[bytes] = asyncio.Queue(maxsize=4)
        self._lock = asyncio.Lock()
        self._session_nonce: bytes | None = None
        self._session_key: bytes | None = None
        self._boot_id: int | None = None
        self._sensor_window: int | None = None
        self._opened = False

    def _on_response(self, encoded: bytes) -> None:
        if self._responses.full():
            self._responses.get_nowait()
            self._responses.task_done()
        self._responses.put_nowait(encoded)

    async def _exchange(
        self,
        command: AuthenticatedCommand,
        *,
        key: bytes,
    ) -> AuthenticatedResponse:
        async with self._lock:
            while not self._responses.empty():
                self._responses.get_nowait()
                self._responses.task_done()
            await self.transport.write(
                CONTROL_UUID,
                encode_command(command, key=key),
                response=True,
            )
            try:
                encoded = await asyncio.wait_for(
                    self._responses.get(),
                    timeout=self.response_timeout_s,
                )
            except TimeoutError as exc:
                raise ControlProtocolError("wearable control response timed out") from exc
            try:
                response = decode_response(encoded, key=key)
            finally:
                self._responses.task_done()
            if response.command_id != command.command_id:
                raise ControlProtocolError("wearable response command_id does not match request")
            if response.session_nonce != command.session_nonce:
                raise ControlProtocolError("wearable response session nonce does not match request")
            return response

    @staticmethod
    def _require_uint(response: AuthenticatedResponse, name: str, maximum: int) -> int:
        value = response.arguments.get(name)
        if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= maximum:
            raise ControlProtocolError(f"response argument {name} is invalid")
        return value

    async def open(self, status: WearableStatus) -> None:
        if status.device_id != self.device_id:
            raise ControlProtocolError("wearable status identity does not match control provisioning")
        if status.state == "unprovisioned":
            raise ControlProtocolError("wearable is unprovisioned and has no application identity")
        await self.transport.start_notify(CONTROL_UUID, self._on_response)
        self._opened = True
        nonce = secrets.token_bytes(16)
        command = AuthenticatedCommand(
            command_id=secrets.randbits(64),
            command="authenticate",
            session_nonce=nonce,
            issued_sensor_window=None,
            arguments={"boot_id": status.boot_id},
        )
        try:
            response = await self._exchange(command, key=self.device_key)
            if response.result != "accepted" or tuple(response.arguments) != (
                "boot_id",
                "sensor_time_us",
            ):
                raise ControlProtocolError("wearable authentication was not accepted")
            boot_id = self._require_uint(response, "boot_id", 0xFFFFFFFFFFFFFFFF)
            sensor_time_us = self._require_uint(response, "sensor_time_us", 0xFFFFFFFF)
            if boot_id != status.boot_id:
                raise ControlProtocolError("wearable authentication boot_id changed")
            self._session_key = derive_session_key(
                device_key=self.device_key,
                session_nonce=nonce,
                device_id=self.device_id,
                boot_id=boot_id,
            )
            self._session_nonce = nonce
            self._boot_id = boot_id
            self._sensor_window = sensor_window(sensor_time_us)
        except Exception:
            await self.close()
            raise

    def _session(self) -> tuple[bytes, bytes, int, int]:
        if (
            self._session_key is None
            or self._session_nonce is None
            or self._boot_id is None
            or self._sensor_window is None
        ):
            raise ControlProtocolError("wearable control session is not authenticated")
        return self._session_key, self._session_nonce, self._boot_id, self._sensor_window

    async def _session_command(
        self,
        name: str,
        arguments: dict[str, int | str | bytes | None],
    ) -> AuthenticatedResponse:
        key, nonce, _boot_id, window = self._session()
        response = await self._exchange(
            AuthenticatedCommand(
                command_id=secrets.randbits(64),
                command=name,
                session_nonce=nonce,
                issued_sensor_window=window,
                arguments=arguments,
            ),
            key=key,
        )
        return response

    async def set_streaming(self, enabled: bool) -> None:
        response = await self._session_command("start" if enabled else "stop", {})
        if response.result not in {"accepted", "already_applied"} or response.arguments:
            raise ControlProtocolError("wearable rejected the streaming state command")

    async def identify(self) -> None:
        response = await self._session_command("identify", {})
        if response.result not in {"accepted", "rate_limited"} or response.arguments:
            raise ControlProtocolError("wearable rejected the identify command")

    async def send_feedback(
        self,
        cue: str,
        *,
        source_is_real: bool,
        quality_gate_passed: bool,
        clock_synchronized: bool,
    ) -> bool:
        if cue not in {"good", "bad"}:
            raise ControlProtocolError("wearable feedback cue must be good or bad")
        if not source_is_real or not quality_gate_passed or not clock_synchronized:
            raise ControlProtocolError("wearable feedback is blocked by the product quality gate")
        response = await self._session_command("feedback", {"cue": cue})
        if response.arguments:
            raise ControlProtocolError("wearable feedback response has unexpected arguments")
        if response.result == "rate_limited":
            return False
        if response.result != "accepted":
            raise ControlProtocolError("wearable rejected the feedback command")
        return True

    async def time_sync(self) -> bool:
        _key, _nonce, boot_id, _window = self._session()
        request_nonce = secrets.token_bytes(16)
        t1_pi_ns = MonotonicNanoseconds(time.monotonic_ns())
        response = await self._session_command(
            "time_sync",
            {"request_nonce": request_nonce, "t1_pi_ns": int(t1_pi_ns)},
        )
        t4_pi_ns = MonotonicNanoseconds(time.monotonic_ns())
        if response.result != "accepted" or tuple(response.arguments) != (
            "boot_id",
            "request_nonce",
            "sensor_receive_us",
            "sensor_send_us",
        ):
            raise ControlProtocolError("wearable rejected the time-sync command")
        response_nonce = response.arguments["request_nonce"]
        if not isinstance(response_nonce, bytes) or not secrets.compare_digest(
            response_nonce,
            request_nonce,
        ):
            raise ControlProtocolError("wearable time-sync nonce does not match request")
        response_boot = self._require_uint(response, "boot_id", 0xFFFFFFFFFFFFFFFF)
        receive_us = self._require_uint(response, "sensor_receive_us", 0xFFFFFFFF)
        send_us = self._require_uint(response, "sensor_send_us", 0xFFFFFFFF)
        if response_boot != boot_id:
            raise ControlProtocolError("wearable rebooted during the control session")
        self._sensor_window = sensor_window(send_us)
        return self.clock_mapper.observe_exchange(
            boot_id=boot_id,
            t1_pi_ns=t1_pi_ns,
            sensor_receive_us=receive_us,
            sensor_send_us=send_us,
            t4_pi_ns=t4_pi_ns,
        )

    async def close(self) -> None:
        try:
            if self._opened:
                await self.transport.stop_notify(CONTROL_UUID)
        finally:
            self._opened = False
            self._session_key = None
            self._session_nonce = None
            self._boot_id = None
            self._sensor_window = None
