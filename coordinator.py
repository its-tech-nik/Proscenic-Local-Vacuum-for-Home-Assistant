"""DataUpdateCoordinator for Proscenic Local vacuum."""
from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from typing import Any

import tinytuya

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    DEFAULT_POLL_INTERVAL,
    DEFAULT_PROTOCOL_VERSION,
    DOMAIN,
    DPS_BATTERY,
    DPS_CLEAN_AREA,
    DPS_CLEAN_TIME,
    DPS_LOCATION,
    DPS_STATUS,
    DPS_SUCTION,
)

_LOGGER = logging.getLogger(__name__)

# Connection settings
CONNECTION_TIMEOUT = 5.0  # seconds
COMMAND_RETRY_DELAY = 0.5  # seconds between retries
MAX_COMMAND_RETRIES = 3


class ProscenicLocalCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinator for polling Proscenic Local vacuum data."""

    def __init__(
        self,
        hass: HomeAssistant,
        host: str,
        device_id: str,
        local_key: str,
        protocol_version: float = DEFAULT_PROTOCOL_VERSION,
        poll_interval: int = DEFAULT_POLL_INTERVAL,
    ) -> None:
        """Initialize the coordinator.

        Args:
            hass: Home Assistant instance
            host: Device IP address
            device_id: Tuya device ID
            local_key: Tuya local key
            protocol_version: Tuya protocol version (default 3.3)
            poll_interval: Polling interval in seconds
        """
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=poll_interval),
        )
        self._host = host
        self._device_id = device_id
        self._local_key = local_key
        self._protocol_version = protocol_version
        self._device: tinytuya.Device | None = None
        self._lock = asyncio.Lock()

    def _create_device(self) -> tinytuya.Device:
        """Create a tinytuya device instance."""
        device = tinytuya.Device(
            dev_id=self._device_id,
            address=self._host,
            local_key=self._local_key,
            version=self._protocol_version,
        )
        device.set_socketPersistent(False)
        device.set_socketTimeout(CONNECTION_TIMEOUT)
        return device

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from the vacuum.

        Returns:
            Dictionary with DPS values

        Raises:
            UpdateFailed: If communication with the device fails
        """
        async with self._lock:
            try:
                data = await self.hass.async_add_executor_job(self._fetch_status)
                if data is None:
                    raise UpdateFailed("Failed to get status from vacuum")
                return data
            except Exception as err:
                raise UpdateFailed(f"Error communicating with vacuum: {err}") from err

    def _fetch_status(self) -> dict[str, Any] | None:
        """Fetch status from the vacuum (blocking).

        Returns:
            Dictionary with DPS values or None if failed
        """
        try:
            device = self._create_device()
            status = device.status()
            if status and "dps" in status:
                _LOGGER.debug("Got vacuum status: %s", status["dps"])
                return status["dps"]
            _LOGGER.warning("Invalid status response: %s", status)
            return None
        except Exception as err:
            _LOGGER.error("Error fetching vacuum status: %s", err)
            raise

    async def async_start_cleaning(self) -> bool:
        """Start smart cleaning.

        Returns:
            True if command was sent successfully
        """
        # Start cleaning requires multiple DPS: DPS 1 = True, DPS 4 = 'smart'
        return await self._async_send_multi_command({"1": True, "4": "smart"})

    async def async_pause(self) -> bool:
        """Pause cleaning.

        Returns:
            True if command was sent successfully
        """
        # DPS 2 = True for pause
        return await self._async_send_single_command(2, True)

    async def async_return_home(self) -> bool:
        """Return to charging dock.

        Returns:
            True if command was sent successfully
        """
        # DPS 3 = True for return home
        return await self._async_send_single_command(3, True)

    async def async_set_suction(self, suction: str) -> bool:
        """Set suction power level.

        Args:
            suction: Suction level (gentle, normal, strong)

        Returns:
            True if command was sent successfully
        """
        # DPS 9 = suction level
        return await self._async_send_single_command(9, suction)

    async def _async_send_single_command(self, dps_id: int, value: Any) -> bool:
        """Send a single DPS command to the vacuum.

        Args:
            dps_id: DPS ID as integer
            value: Value to set

        Returns:
            True if command was sent successfully
        """
        success = False
        async with self._lock:
            for attempt in range(MAX_COMMAND_RETRIES):
                try:
                    result = await self.hass.async_add_executor_job(
                        self._send_single_value, dps_id, value
                    )
                    # Check for explicit errors, but don't fail on empty response
                    # (tinytuya often returns empty/None even on success)
                    if self._is_error_response(result):
                        _LOGGER.warning(
                            "Command DPS %s=%s got error response: %s (attempt %d/%d)",
                            dps_id, value, result, attempt + 1, MAX_COMMAND_RETRIES
                        )
                    else:
                        _LOGGER.debug("Command DPS %s=%s sent (result: %s)", dps_id, value, result)
                        success = True
                        break  # Exit retry loop on success
                except Exception as err:
                    _LOGGER.warning(
                        "Error sending command DPS %s=%s (attempt %d/%d): %s",
                        dps_id, value, attempt + 1, MAX_COMMAND_RETRIES, err
                    )
                
                if attempt < MAX_COMMAND_RETRIES - 1:
                    await asyncio.sleep(COMMAND_RETRY_DELAY)
            
            if not success:
                _LOGGER.error("Failed to send command DPS %s=%s after %d attempts", 
                             dps_id, value, MAX_COMMAND_RETRIES)
        
        # Refresh OUTSIDE the lock to avoid deadlock
        if success:
            await asyncio.sleep(1.0)
            await self.async_request_refresh()
        
        return success

    async def _async_send_multi_command(self, dps_values: dict[str, Any]) -> bool:
        """Send multiple DPS values in one command.

        Args:
            dps_values: Dictionary of DPS values to set (string keys)

        Returns:
            True if command was sent successfully
        """
        success = False
        async with self._lock:
            for attempt in range(MAX_COMMAND_RETRIES):
                try:
                    result = await self.hass.async_add_executor_job(
                        self._send_multi_value, dps_values
                    )
                    # Check for explicit errors, but don't fail on empty response
                    # (tinytuya often returns empty/None even on success)
                    if self._is_error_response(result):
                        _LOGGER.warning(
                            "Multi-command %s got error response: %s (attempt %d/%d)",
                            dps_values, result, attempt + 1, MAX_COMMAND_RETRIES
                        )
                    else:
                        _LOGGER.debug("Multi-command %s sent (result: %s)", dps_values, result)
                        success = True
                        break  # Exit retry loop on success
                except Exception as err:
                    _LOGGER.warning(
                        "Error sending multi-command %s (attempt %d/%d): %s",
                        dps_values, attempt + 1, MAX_COMMAND_RETRIES, err
                    )
                
                if attempt < MAX_COMMAND_RETRIES - 1:
                    await asyncio.sleep(COMMAND_RETRY_DELAY)
            
            if not success:
                _LOGGER.error("Failed to send multi-command %s after %d attempts", 
                             dps_values, MAX_COMMAND_RETRIES)
        
        # Refresh OUTSIDE the lock to avoid deadlock
        if success:
            await asyncio.sleep(1.0)
            await self.async_request_refresh()
        
        return success

    def _is_error_response(self, result: dict | None) -> bool:
        """Check if the response indicates an error.

        Args:
            result: Response from tinytuya

        Returns:
            True if the response is an explicit error
        """
        if result is None:
            return False  # None/empty is often success
        if isinstance(result, dict):
            # Check for error indicators
            if "Error" in result or "Err" in result or "error" in result:
                return True
            # Check for specific error codes
            if result.get("Error"):
                return True
        return False

    def _send_single_value(self, dps_id: int, value: Any) -> dict | None:
        """Send a single DPS value (blocking).

        Args:
            dps_id: DPS ID as integer (required by tinytuya set_value)
            value: Value to set

        Returns:
            Response from device or None
        """
        device = self._create_device()
        _LOGGER.debug("Sending single command: DPS %s = %s", dps_id, value)
        result = device.set_value(dps_id, value)
        _LOGGER.debug("Command result: %s", result)
        return result

    def _send_multi_value(self, dps_values: dict[str, Any]) -> dict | None:
        """Send multiple DPS values in one command (blocking).

        Args:
            dps_values: Dictionary of DPS values (string keys for generate_payload)

        Returns:
            Response from device or None
        """
        device = self._create_device()
        _LOGGER.debug("Sending multi-command: %s", dps_values)
        payload = device.generate_payload(tinytuya.CONTROL, dps_values)
        result = device.send(payload)
        _LOGGER.debug("Command result: %s", result)
        return result

    @property
    def status(self) -> str | None:
        """Get current vacuum status."""
        if self.data:
            # Try string key first, then integer key (tinytuya may return either)
            status = self.data.get(DPS_STATUS) or self.data.get(int(DPS_STATUS))
            if status:
                _LOGGER.debug("Vacuum status (DPS 5): %s", status)
            return status
        return None

    @property
    def battery_level(self) -> int | None:
        """Get battery level percentage."""
        if self.data:
            return self.data.get(DPS_BATTERY)
        return None

    @property
    def suction_level(self) -> str | None:
        """Get current suction level."""
        if self.data:
            return self.data.get(DPS_SUCTION)
        return None

    @property
    def clean_time(self) -> int | None:
        """Get current session clean time in minutes."""
        if self.data:
            return self.data.get(DPS_CLEAN_TIME)
        return None

    @property
    def clean_area(self) -> int | None:
        """Get current session clean area in m²."""
        if self.data:
            return self.data.get(DPS_CLEAN_AREA)
        return None

    @property
    def location(self) -> str | None:
        """Get current location."""
        if self.data:
            return self.data.get(DPS_LOCATION)
        return None

    async def async_test_connection(self) -> bool:
        """Test connection to the vacuum.

        Returns:
            True if connection is successful
        """
        try:
            data = await self.hass.async_add_executor_job(self._fetch_status)
            return data is not None
        except Exception as err:
            _LOGGER.error("Connection test failed: %s", err)
            return False

