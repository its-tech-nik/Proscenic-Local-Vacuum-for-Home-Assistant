"""DataUpdateCoordinator for Proscenic Local vacuum."""
from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import datetime, timedelta
import logging
from typing import Any

import tinytuya

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import format_mac
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import (
    CONF_DEVICE_ID,
    CONF_LOCAL_KEY,
    CONF_MAC,
    CONF_POLL_INTERVAL,
    CONF_PROTOCOL_VERSION,
    DEFAULT_POLL_INTERVAL,
    DEFAULT_PROTOCOL_VERSION,
    DOMAIN,
    DPS_LOCATION,
    DPS_MODE_COMMAND,
    DPS_PAUSE,
    DPS_RETURN_HOME,
    DPS_START_CLEAN,
    DPS_STATUS,
    DPS_SUCTION,
    MODE_SMART,
)
from .device import async_scan_lan, create_device, fetch_status

_LOGGER = logging.getLogger(__name__)

COMMAND_RETRY_DELAY = 0.5  # seconds between retries
MAX_COMMAND_RETRIES = 3

# LAN rediscovery can take up to SCAN_TIME; avoid hammering the network.
HOST_RESOLVE_COOLDOWN = timedelta(minutes=5)

type ProscenicConfigEntry = ConfigEntry[ProscenicLocalCoordinator]


def get_poll_interval(entry: ConfigEntry) -> timedelta:
    """Return the configured polling interval for an entry."""
    return timedelta(
        seconds=entry.options.get(CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL)
    )


class ProscenicLocalCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinator for polling Proscenic Local vacuum data."""

    config_entry: ProscenicConfigEntry

    def __init__(self, hass: HomeAssistant, entry: ProscenicConfigEntry) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=get_poll_interval(entry),
        )
        self.device_id: str = entry.data[CONF_DEVICE_ID]
        self._host: str = entry.data[CONF_HOST]
        self._local_key: str = entry.data[CONF_LOCAL_KEY]
        self._protocol_version: float = float(
            entry.data.get(CONF_PROTOCOL_VERSION, DEFAULT_PROTOCOL_VERSION)
        )
        self.device_mac: str | None = None
        if raw_mac := entry.data.get(CONF_MAC):
            try:
                self.device_mac = format_mac(str(raw_mac))
            except ValueError:
                _LOGGER.warning("Invalid stored MAC ignored: %s", raw_mac)
        self._last_host_resolve_attempt: datetime | None = None
        self._lock = asyncio.Lock()

    def _create_device(self) -> tinytuya.Device:
        return create_device(
            self._host, self.device_id, self._local_key, self._protocol_version
        )

    def _fetch_status(self) -> dict[str, Any]:
        dps = fetch_status(self._create_device())
        _LOGGER.debug("Got vacuum status: %s", dps)
        return dps

    def _mac_matches_discovered(self, discovered_mac: str | None) -> bool:
        if not self.device_mac or not discovered_mac:
            return True
        try:
            return format_mac(discovered_mac) == self.device_mac
        except ValueError:
            return True

    async def _async_try_resolve_host(self) -> bool:
        """Find the vacuum on the LAN after a failed poll; persist host if it changed.

        Tuya broadcasts carry the device ID but usually not the MAC, so the device
        is matched by ID; the stored MAC is only checked when a broadcast has one.

        Returns:
            True if the host was updated and the caller should retry immediately.
        """
        now = dt_util.utcnow()
        if (
            self._last_host_resolve_attempt is not None
            and now - self._last_host_resolve_attempt < HOST_RESOLVE_COOLDOWN
        ):
            return False

        self._last_host_resolve_attempt = now

        found = next(
            (
                device
                for device in await async_scan_lan(self.hass, self.device_id)
                if device.device_id == self.device_id
            ),
            None,
        )
        if found is None:
            _LOGGER.debug("LAN discovery did not find device %s", self.device_id)
            return False

        if not self._mac_matches_discovered(found.mac):
            _LOGGER.warning(
                "Ignoring LAN discovery result for %s: MAC mismatch (expected %s, got %s)",
                self.device_id,
                self.device_mac,
                found.mac,
            )
            return False

        new_ip = found.ip
        if new_ip == self._host:
            return False

        _LOGGER.warning(
            "Updating vacuum host after failed poll: %s -> %s", self._host, new_ip
        )
        self._host = new_ip
        self.hass.config_entries.async_update_entry(
            self.config_entry, data={**self.config_entry.data, CONF_HOST: new_ip}
        )
        return True

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from the vacuum, rediscovering its IP if it moved."""
        async with self._lock:
            try:
                data = await self.hass.async_add_executor_job(self._fetch_status)
            except Exception as err:
                error: Exception = err
            else:
                self._last_host_resolve_attempt = None
                return data

            if await self._async_try_resolve_host():
                try:
                    data = await self.hass.async_add_executor_job(self._fetch_status)
                except Exception as err:
                    error = err
                else:
                    self._last_host_resolve_attempt = None
                    return data

            raise UpdateFailed(f"Error communicating with vacuum: {error}") from error

    async def async_start_cleaning(self) -> None:
        """Start smart cleaning."""
        await self._async_send_command(
            self._send_multi_value,
            {DPS_START_CLEAN: True, DPS_MODE_COMMAND: MODE_SMART},
        )

    async def async_pause(self) -> None:
        """Pause cleaning."""
        await self._async_send_command(self._send_single_value, DPS_PAUSE, True)

    async def async_return_home(self) -> None:
        """Return to charging dock."""
        await self._async_send_command(self._send_single_value, DPS_RETURN_HOME, True)

    async def async_set_suction(self, suction: str) -> None:
        """Set suction power level (gentle, normal, strong)."""
        await self._async_send_command(self._send_single_value, DPS_SUCTION, suction)

    async def _async_send_command(
        self, send: Callable[..., dict | None], *args: Any
    ) -> None:
        """Send a command with retries, then refresh the state.

        Raises:
            HomeAssistantError: If every attempt failed.
        """
        last_error: str | None = None
        async with self._lock:
            for attempt in range(1, MAX_COMMAND_RETRIES + 1):
                try:
                    result = await self.hass.async_add_executor_job(send, *args)
                except Exception as err:
                    last_error = str(err)
                else:
                    # tinytuya often returns an empty response even on success,
                    # so only explicit error payloads count as failures.
                    if not self._is_error_response(result):
                        _LOGGER.debug("Command %s sent (result: %s)", args, result)
                        break
                    last_error = str(result)

                _LOGGER.warning(
                    "Command %s failed (attempt %d/%d): %s",
                    args,
                    attempt,
                    MAX_COMMAND_RETRIES,
                    last_error,
                )
                if attempt < MAX_COMMAND_RETRIES:
                    await asyncio.sleep(COMMAND_RETRY_DELAY)
            else:
                raise HomeAssistantError(
                    f"Failed to send command to vacuum after {MAX_COMMAND_RETRIES} "
                    f"attempts: {last_error}"
                )

        # The refresh takes the lock itself, so it must run after releasing it.
        await asyncio.sleep(1.0)
        await self.async_request_refresh()

    @staticmethod
    def _is_error_response(result: dict | None) -> bool:
        """Return True if tinytuya returned an explicit error payload."""
        return isinstance(result, dict) and any(
            key in result for key in ("Error", "Err", "error")
        )

    def _send_single_value(self, dps_id: str, value: Any) -> dict | None:
        """Send a single DPS value (blocking)."""
        return self._create_device().set_value(int(dps_id), value)

    def _send_multi_value(self, dps_values: dict[str, Any]) -> dict | None:
        """Send multiple DPS values in one command (blocking)."""
        device = self._create_device()
        payload = device.generate_payload(tinytuya.CONTROL, dps_values)
        return device.send(payload)

    @property
    def status(self) -> str | None:
        """Get current vacuum status."""
        return self.data.get(DPS_STATUS) if self.data else None

    @property
    def suction_level(self) -> str | None:
        """Get current suction level."""
        return self.data.get(DPS_SUCTION) if self.data else None

    @property
    def location(self) -> str | None:
        """Get current location."""
        return self.data.get(DPS_LOCATION) if self.data else None
