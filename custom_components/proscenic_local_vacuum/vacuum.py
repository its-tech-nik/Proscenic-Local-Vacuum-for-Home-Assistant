"""Vacuum entity for Proscenic."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.vacuum import (
    StateVacuumEntity,
    VacuumActivity,
    VacuumEntityFeature,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    FAN_SPEEDS,
    STATUS_CHARGING,
    STATUS_GOTO_CHARGE,
    STATUS_PAUSED,
    STATUS_SLEEP,
    STATUS_SMART,
)
from .coordinator import ProscenicConfigEntry, ProscenicLocalCoordinator
from .entity import ProscenicLocalEntity

_LOGGER = logging.getLogger(__name__)

STATUS_TO_ACTIVITY = {
    STATUS_SMART: VacuumActivity.CLEANING,
    STATUS_PAUSED: VacuumActivity.PAUSED,
    STATUS_GOTO_CHARGE: VacuumActivity.RETURNING,
    STATUS_SLEEP: VacuumActivity.IDLE,
    STATUS_CHARGING: VacuumActivity.DOCKED,
    # STATUS_STANDBY is not mapped - HA doesn't have a standby state
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ProscenicConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Proscenic vacuum from a config entry."""
    async_add_entities([ProscenicLocalVacuum(entry.runtime_data)])


class ProscenicLocalVacuum(ProscenicLocalEntity, StateVacuumEntity):
    """Representation of a Proscenic vacuum."""

    _attr_name = None
    _attr_supported_features = (
        VacuumEntityFeature.START
        | VacuumEntityFeature.PAUSE
        | VacuumEntityFeature.RETURN_HOME
        | VacuumEntityFeature.FAN_SPEED
        | VacuumEntityFeature.STATE
    )
    _attr_fan_speed_list = FAN_SPEEDS

    def __init__(self, coordinator: ProscenicLocalCoordinator) -> None:
        """Initialize the vacuum entity."""
        super().__init__(coordinator)
        self._attr_unique_id = coordinator.device_id

    @property
    def activity(self) -> VacuumActivity | None:
        """Return the current vacuum activity."""
        status = self.coordinator.status
        if status is None:
            return None

        activity = STATUS_TO_ACTIVITY.get(status)
        if activity is None:
            _LOGGER.debug("Unmapped vacuum status: '%s'", status)
        return activity

    @property
    def fan_speed(self) -> str | None:
        """Return the current suction level (gentle, normal, strong)."""
        return self.coordinator.suction_level

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        if not self.coordinator.data:
            return {}
        attrs: dict[str, Any] = {"raw_status": self.coordinator.status}
        if (location := self.coordinator.location) is not None:
            attrs["location"] = location
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
        """Set fan speed (suction power)."""
        if fan_speed not in FAN_SPEEDS:
            raise ServiceValidationError(
                f"Invalid fan speed '{fan_speed}'. Valid options: {', '.join(FAN_SPEEDS)}"
            )
        await self.coordinator.async_set_suction(fan_speed)
