"""Small Bleak/BlueZ boundary kept out of the deterministic agent core."""

from __future__ import annotations

import asyncio
from collections.abc import Callable

from bleak import BleakClient, BleakScanner

from digital_spotter.imu.protocol import SERVICE_UUID


class BLETransportError(RuntimeError):
    pass


class BleakWearableTransport:
    def __init__(self, *, scan_timeout_s: float = 10.0, connect_timeout_s: float = 30.0):
        self.scan_timeout_s = scan_timeout_s
        self.connect_timeout_s = connect_timeout_s
        self._client: BleakClient | None = None
        self._disconnected = asyncio.Event()

    @property
    def is_connected(self) -> bool:
        return self._client is not None and self._client.is_connected

    async def connect(self) -> None:
        self._disconnected.clear()
        device = await BleakScanner.find_device_by_filter(
            lambda _device, advertisement: SERVICE_UUID.lower()
            in {uuid.lower() for uuid in (advertisement.service_uuids or [])},
            timeout=self.scan_timeout_s,
            service_uuids=[SERVICE_UUID],
        )
        if device is None:
            raise BLETransportError("provisioned service was not discovered")
        loop = asyncio.get_running_loop()

        def disconnected(_client: BleakClient) -> None:
            loop.call_soon_threadsafe(self._disconnected.set)

        self._client = BleakClient(
            device,
            disconnected_callback=disconnected,
            services=[SERVICE_UUID],
            timeout=self.connect_timeout_s,
            pair=True,
        )
        try:
            await self._client.connect()
        except Exception:
            self._client = None
            raise

    async def disconnect(self) -> None:
        client, self._client = self._client, None
        if client is not None and client.is_connected:
            await client.disconnect()
        self._disconnected.set()

    def _require_client(self) -> BleakClient:
        if self._client is None or not self._client.is_connected:
            raise BLETransportError("wearable is not connected")
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
