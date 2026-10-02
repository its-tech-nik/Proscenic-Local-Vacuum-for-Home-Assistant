"""Blocking tinytuya helpers for the Proscenic Local Vacuum integration."""
from __future__ import annotations

import logging
from typing import Any

import tinytuya

from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

CONNECTION_TIMEOUT = 5.0  # seconds


class DeviceCommunicationError(Exception):
    """Raised when the vacuum does not return a usable response."""


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
