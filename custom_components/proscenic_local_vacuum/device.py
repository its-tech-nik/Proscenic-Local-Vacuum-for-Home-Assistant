"""Blocking tinytuya helpers for the Proscenic Local Vacuum integration."""
from __future__ import annotations

from dataclasses import dataclass
import ipaddress
import logging
from typing import Any

import tinytuya
from tinytuya import scanner

from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

CONNECTION_TIMEOUT = 5.0  # seconds
# Tuya devices broadcast their presence roughly every 5 seconds.
SCAN_TIME = 12  # seconds


class DeviceCommunicationError(Exception):
    """Raised when the vacuum does not return a usable response."""


@dataclass(frozen=True)
class DiscoveredDevice:
    """A Tuya device seen broadcasting on the LAN."""

    ip: str
    device_id: str
    protocol_version: str | None


def scan_lan(device_id: str | None = None) -> list[DiscoveredDevice]:
    """Listen for Tuya UDP broadcasts (blocking).

    Stops early once device_id has been seen, otherwise after SCAN_TIME.
    """
    found = scanner.devices(
        verbose=False,
        scantime=SCAN_TIME,
        color=False,
        poll=False,
        byID=True,
        wantids=[device_id] if device_id else None,
    )
    devices = [
        DiscoveredDevice(
            ip=info["ip"],
            device_id=gw_id,
            protocol_version=str(info["version"]) if info.get("version") else None,
        )
        for gw_id, info in found.items()
        if info.get("origin") == "broadcast" and info.get("ip")
    ]
    return sorted(devices, key=lambda device: ipaddress.ip_address(device.ip))


async def async_scan_lan(
    hass: HomeAssistant, device_id: str | None = None
) -> list[DiscoveredDevice]:
    """Scan the LAN for Tuya devices; an empty list if scanning is not possible."""
    try:
        devices = await hass.async_add_executor_job(scan_lan, device_id)
    except Exception:
        _LOGGER.exception("LAN scan for Tuya devices failed")
        return []
    _LOGGER.debug("LAN scan found: %s", devices)
    return devices


def create_device(
    host: str, device_id: str, local_key: str, protocol_version: float
) -> tinytuya.Device:
    """Create a non-persistent tinytuya device."""
    device = tinytuya.Device(
        dev_id=device_id,
        address=host,
        local_key=local_key,
        version=protocol_version,
    )
    device.set_socketPersistent(False)
    device.set_socketTimeout(CONNECTION_TIMEOUT)
    return device


def fetch_status(device: tinytuya.Device) -> dict[str, Any]:
    """Return the DPS values reported by the vacuum (blocking)."""
    status = device.status()
    if not isinstance(status, dict) or "dps" not in status:
        raise DeviceCommunicationError(f"Invalid status response: {status}")
    return status["dps"]


async def async_test_connection(
    hass: HomeAssistant,
    host: str,
    device_id: str,
    local_key: str,
    protocol_version: float,
) -> bool:
    """Return True if the vacuum answers a status request."""

    def _test() -> None:
        fetch_status(create_device(host, device_id, local_key, protocol_version))

    try:
        await hass.async_add_executor_job(_test)
    except Exception as err:
        _LOGGER.debug("Connection test to %s failed: %s", host, err)
        return False
    return True
