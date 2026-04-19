"""Vacuum entity for Proscenic."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.vacuum import (
    StateVacuumEntity,
    VacuumEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC, format_mac
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    CONF_MAC,
    DEFAULT_NAME,
    DOMAIN,
    DPS_LOCATION,
    FAN_SPEEDS,
    STATUS_CHARGING,
    STATUS_GOTO_CHARGE,
    STATUS_PAUSED,
    STATUS_SLEEP,
    STATUS_SMART,
)
from .coordinator import ProscenicLocalCoordinator

_LOGGER = logging.getLogger(__name__)

# Map DPS status values to Home Assistant VacuumActivity states
# Using string values since VacuumActivity enum may not be available in all HA versions
STATE_CLEANING = "cleaning"
STATE_DOCKED = "docked"
STATE_PAUSED = "paused"
STATE_IDLE = "idle"
STATE_RETURNING = "returning"
STATE_ERROR = "error"

STATUS_TO_STATE = {
    STATUS_SMART: STATE_CLEANING,
    STATUS_PAUSED: STATE_PAUSED,
    STATUS_GOTO_CHARGE: STATE_RETURNING,
    STATUS_SLEEP: STATE_IDLE,
    STATUS_CHARGING: STATE_DOCKED,  # Charging on dock = docked state
    # Note: STATUS_STANDBY is not mapped - HA doesn't have a standby state
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Proscenic vacuum from a config entry.

    Args:
        hass: Home Assistant instance
        entry: Config entry
        async_add_entities: Callback to add entities
    """
    coordinator: ProscenicLocalCoordinator = hass.data[DOMAIN][entry.entry_id]
    name = entry.data.get(CONF_NAME, DEFAULT_NAME)

    async_add_entities([ProscenicLocalVacuum(coordinator, entry, name)])


class ProscenicLocalVacuum(CoordinatorEntity[ProscenicLocalCoordinator], StateVacuumEntity):
    """Representation of a Proscenic vacuum."""

    _attr_has_entity_name = True
    _attr_supported_features = (
        VacuumEntityFeature.START
        | VacuumEntityFeature.PAUSE
        | VacuumEntityFeature.RETURN_HOME
        | VacuumEntityFeature.FAN_SPEED
        | VacuumEntityFeature.STATE
    )
    _attr_fan_speed_list = FAN_SPEEDS

    def __init__(
        self,
        coordinator: ProscenicLocalCoordinator,
        entry: ConfigEntry,
        name: str,
    ) -> None:
        """Initialize the vacuum entity.

        Args:
            coordinator: The data coordinator
            entry: Config entry
            name: Entity name
        """
        super().__init__(coordinator)
        self._entry = entry
        self._attr_name = name
        self._attr_unique_id = entry.entry_id

    @property
    def activity(self) -> str | None:
        """Return the current vacuum activity.

        Returns:
            The current activity state string
        """
        status = self.coordinator.status
        if status is None:
            return None
        
        mapped_state = STATUS_TO_STATE.get(status)
        if mapped_state is None:
            # Log unmapped status for debugging
            _LOGGER.debug("Unmapped vacuum status: '%s'", status)
        return mapped_state

    @property
    def fan_speed(self) -> str | None:
        """Return the current fan speed.

        Returns:
            Current suction level (gentle, normal, strong)
        """
        return self.coordinator.suction_level

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes.

        Returns:
            Dictionary with extra attributes
        """
        attrs: dict[str, Any] = {}

        if self.coordinator.data:
            data = self.coordinator.data

            # Location
            if DPS_LOCATION in data:
                attrs["location"] = data[DPS_LOCATION]

            # Raw status for debugging
            attrs["raw_status"] = self.coordinator.status

        return attrs

    async def async_start(self) -> None:
        """Start or resume cleaning."""
        await self.coordinator.async_start_cleaning()

    async def async_pause(self) -> None:
        """Pause cleaning."""
        await self.coordinator.async_pause()

    async def async_return_to_base(self, **kwargs: Any) -> None:
        """Return to charging dock."""
        await self.coordinator.async_return_home()

    async def async_set_fan_speed(self, fan_speed: str, **kwargs: Any) -> None:
        """Set fan speed (suction power).

        Args:
            fan_speed: The fan speed to set (gentle, normal, strong)
        """
        if fan_speed not in FAN_SPEEDS:
            _LOGGER.warning("Invalid fan speed: %s. Valid options: %s", fan_speed, FAN_SPEEDS)
            return
        await self.coordinator.async_set_suction(fan_speed)

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self.async_write_ha_state()

    @property
    def device_info(self) -> dict[str, Any]:
        """Return device info for device registry.

        Returns:
            Device info dictionary
        """
        info: dict[str, Any] = {
            "identifiers": {(DOMAIN, self._entry.entry_id)},
            "name": self._attr_name,
            "manufacturer": "Proscenic",
            "model": "Q8",
        }
        raw_mac = self._entry.data.get(CONF_MAC)
        if raw_mac:
            try:
                info["connections"] = {(CONNECTION_NETWORK_MAC, format_mac(str(raw_mac)))}
            except ValueError:
                pass
        return info

