"""Local Wi-Fi link status for the Pi UI and indicator.

This intentionally checks only the configured interface and whether it owns an
IPv4 address. It does not contact the internet, expose the address, or alter any
network configuration.
"""

from __future__ import annotations

import fcntl
import re
import socket
import struct
from collections.abc import Callable
from pathlib import Path


_INTERFACE = re.compile(r"[A-Za-z0-9_.:-]{1,15}")
_SIOCGIFADDR = 0x8915


class LinuxWiFiProbe:
    """Read a single Linux interface without relying on external connectivity."""

    def __init__(
        self,
        *,
        interface: str = "wlan0",
        operstate_reader: Callable[[str], str | None] | None = None,
        address_reader: Callable[[str], bool] | None = None,
    ) -> None:
        if not _INTERFACE.fullmatch(interface):
            raise ValueError("invalid network interface")
        self.interface = interface
        self._operstate_reader = operstate_reader or self._read_operstate
        self._address_reader = address_reader or self._has_ipv4_address

    @staticmethod
    def _read_operstate(interface: str) -> str | None:
        try:
            return (
                Path("/sys/class/net", interface, "operstate")
                .read_text(encoding="ascii")
                .strip()
                .lower()
            )
        except (FileNotFoundError, OSError, UnicodeError):
            return None

    @staticmethod
    def _has_ipv4_address(interface: str) -> bool:
        request = struct.pack("256s", interface.encode("ascii"))
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as handle:
                fcntl.ioctl(handle.fileno(), _SIOCGIFADDR, request)
        except OSError:
            return False
        return True

    def sample(self) -> dict[str, str | bool]:
        operstate = self._operstate_reader(self.interface)
        if operstate is None:
            state = "unavailable"
            has_address = False
        else:
            has_address = bool(self._address_reader(self.interface))
            state = "connected" if operstate == "up" and has_address else "disconnected"
        return {
            "state": state,
            "interface": self.interface,
            "has_local_address": has_address,
        }
