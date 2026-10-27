"""Bleak/BlueZ boundary for the frozen R9 research contract."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Iterable

from bleak import BleakClient, BleakScanner

from digital_spotter.imu.r9_protocol import (
    DEVICE_ADDRESS,
    DEVICE_NAME,
    REQUIRED_CHARACTERISTIC_UUIDS,
    SERVICE_UUID,
)


LOGGER = logging.getLogger("digital_spotter.imu.transport")


class R9TransportError(RuntimeError):
    pass


def validate_device_identity(
    *,
    name: str | None,
    address: str,
    expected_name: str,
    expected_address: str,
) -> None:
    if name != expected_name:
        raise R9TransportError("discovered BLE name does not match R9")
    if address.casefold() != expected_address.casefold():
        raise R9TransportError("discovered BLE address does not match R9")


def validate_gatt_contract(
    *,
    service_uuids: Iterable[str],
    characteristic_uuids: Iterable[str],
) -> None:
    normalized_services = {value.casefold() for value in service_uuids}
    normalized_characteristics = {value.casefold() for value in characteristic_uuids}
    if SERVICE_UUID.casefold() not in normalized_services:
        raise R9TransportError("R9 service UUID is missing")
    missing = {
        value for value in REQUIRED_CHARACTERISTIC_UUIDS
        if value.casefold() not in normalized_characteristics
    }
    if missing:
        raise R9TransportError(
            "R9 characteristic UUIDs are missing: " + ", ".join(sorted(missing))
        )


class R9BleakTransport:
    def __init__(
        self,
        *,
        expected_name: str = DEVICE_NAME,
        expected_address: str = DEVICE_ADDRESS,
        scan_timeout_s: float = 15.0,
        connect_timeout_s: float = 20.0,
    ) -> None:
        self.expected_name = expected_name
        self.expected_address = expected_address
        self.scan_timeout_s = scan_timeout_s
        self.connect_timeout_s = connect_timeout_s
        self._client: BleakClient | None = None
        self._disconnected = asyncio.Event()

    @property
    def is_connected(self) -> bool:
        return self._client is not None and self._client.is_connected

    def _record_disconnection(
        self,
        disconnected_client: BleakClient,
        loop: asyncio.AbstractEventLoop,
    ) -> None:
        if self._client is disconnected_client:
            LOGGER.info("BlueZ reported established R9 disconnection")
            loop.call_soon_threadsafe(self._disconnected.set)

    async def connect(self) -> None:
        self._disconnected.clear()

        def matches(device, advertisement) -> bool:
            observed_name = advertisement.local_name or device.name
            return (
                observed_name == self.expected_name
                and device.address.casefold() == self.expected_address.casefold()
            )

        device = await BleakScanner.find_device_by_filter(
            matches,
            timeout=self.scan_timeout_s,
        )
        if device is None:
            raise R9TransportError("expected R9 wearable was not discovered")
        validate_device_identity(
            name=device.name,
            address=device.address,
            expected_name=self.expected_name,
            expected_address=self.expected_address,
        )
        loop = asyncio.get_running_loop()

        def disconnected(disconnected_client: BleakClient) -> None:
            # Bleak can briefly connect/disconnect while retrying
            # le-connection-abort-by-local inside connect(). Those callbacks
            # precede acceptance into self._client and must not poison the
            # runtime's established-connection event.
            self._record_disconnection(disconnected_client, loop)

        client = BleakClient(
            device,
            disconnected_callback=disconnected,
            timeout=self.connect_timeout_s,
            pair=False,
        )
        try:
            await client.connect()
            services = list(client.services)
            validate_gatt_contract(
                service_uuids=[service.uuid for service in services],
                characteristic_uuids=[
                    characteristic.uuid
                    for service in services
                    for characteristic in service.characteristics
                ],
            )
        except Exception:
            if client.is_connected:
                await client.disconnect()
            raise
        self._client = client
        LOGGER.info("R9 BLE connection and GATT contract verified")

    async def disconnect(self) -> None:
        client, self._client = self._client, None
        if client is not None and client.is_connected:
            await client.disconnect()
        self._disconnected.set()

    def _require_client(self) -> BleakClient:
        if self._client is None or not self._client.is_connected:
            raise R9TransportError("R9 wearable is not connected")
        return self._client

    async def read(self, characteristic_uuid: str) -> bytes:
        return bytes(await self._require_client().read_gatt_char(characteristic_uuid))

    async def write(
        self,
        characteristic_uuid: str,
        data: bytes,
        *,
        response: bool,
    ) -> None:
        await self._require_client().write_gatt_char(
            characteristic_uuid,
            data,
            response=response,
        )

    async def start_notify(
        self,
        characteristic_uuid: str,
        callback: Callable[[bytes], None],
    ) -> None:
        def bleak_callback(_sender, data: bytearray) -> None:
            callback(bytes(data))

        await self._require_client().start_notify(characteristic_uuid, bleak_callback)

    async def stop_notify(self, characteristic_uuid: str) -> None:
        if self.is_connected:
            await self._require_client().stop_notify(characteristic_uuid)

    async def wait_disconnected(self) -> None:
        await self._disconnected.wait()
