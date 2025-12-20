"""Sensor entities for Proscenic Local vacuum."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME, PERCENTAGE, UnitOfTime, UnitOfArea
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DEFAULT_NAME,
    DOMAIN,
    DPS_CLEAN_AREA,
    DPS_CLEAN_TIME,
    DPS_FILTER,
    DPS_MAIN_BRUSH,
    DPS_SIDE_BRUSH,
)
from .coordinator import ProscenicLocalCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Proscenic Local sensors from a config entry.

    Args:
        hass: Home Assistant instance
        entry: Config entry
        async_add_entities: Callback to add entities
    """
    coordinator: ProscenicLocalCoordinator = hass.data[DOMAIN][entry.entry_id]
    name = entry.data.get(CONF_NAME, DEFAULT_NAME)

    entities: list[SensorEntity] = [
        ProscenicLocalBatterySensor(coordinator, entry, name),
        ProscenicLocalCleanTimeSensor(coordinator, entry, name),
        ProscenicLocalCleanAreaSensor(coordinator, entry, name),
        ProscenicLocalMainBrushSensor(coordinator, entry, name),
        ProscenicLocalSideBrushSensor(coordinator, entry, name),
        ProscenicLocalFilterSensor(coordinator, entry, name),
    ]

    async_add_entities(entities)


class ProscenicLocalSensorBase(CoordinatorEntity[ProscenicLocalCoordinator], SensorEntity):
    """Base class for Proscenic sensors."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: ProscenicLocalCoordinator,
        entry: ConfigEntry,
        device_name: str,
        sensor_name: str,
        unique_id_suffix: str,
    ) -> None:
        """Initialize the sensor.

        Args:
            coordinator: The data coordinator
            entry: Config entry
            device_name: Device name
            sensor_name: Sensor name suffix
            unique_id_suffix: Unique ID suffix
        """
        super().__init__(coordinator)
        self._entry = entry
        self._device_name = device_name
        self._attr_name = sensor_name
        self._attr_unique_id = f"{entry.entry_id}_{unique_id_suffix}"

    @property
    def device_info(self) -> dict[str, Any]:
        """Return device info for device registry.

        Returns:
            Device info dictionary
        """
        return {
            "identifiers": {(DOMAIN, self._entry.entry_id)},
            "name": self._device_name,
            "manufacturer": "Proscenic",
            "model": "Q8",
        }

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self.async_write_ha_state()


class ProscenicLocalBatterySensor(ProscenicLocalSensorBase):
    """Battery level sensor for Proscenic."""

    _attr_device_class = SensorDeviceClass.BATTERY
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(
        self,
        coordinator: ProscenicLocalCoordinator,
        entry: ConfigEntry,
        device_name: str,
    ) -> None:
        """Initialize the battery sensor."""
        super().__init__(
            coordinator,
            entry,
            device_name,
            "Battery",
            "battery",
        )

    @property
    def native_value(self) -> int | None:
        """Return the battery level."""
        return self.coordinator.battery_level


class ProscenicLocalCleanTimeSensor(ProscenicLocalSensorBase):
    """Clean time sensor for Proscenic."""

    _attr_device_class = SensorDeviceClass.DURATION
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:timer"

    def __init__(
        self,
        coordinator: ProscenicLocalCoordinator,
        entry: ConfigEntry,
        device_name: str,
    ) -> None:
        """Initialize the clean time sensor."""
        super().__init__(
            coordinator,
            entry,
            device_name,
            "Clean Time",
            "clean_time",
        )

    @property
    def native_value(self) -> int | None:
        """Return the clean time in minutes."""
        if self.coordinator.data:
            return self.coordinator.data.get(DPS_CLEAN_TIME)
        return None


class ProscenicLocalCleanAreaSensor(ProscenicLocalSensorBase):
    """Clean area sensor for Proscenic."""

    _attr_native_unit_of_measurement = UnitOfArea.SQUARE_METERS
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:texture-box"

    def __init__(
        self,
        coordinator: ProscenicLocalCoordinator,
        entry: ConfigEntry,
        device_name: str,
    ) -> None:
        """Initialize the clean area sensor."""
        super().__init__(
            coordinator,
            entry,
            device_name,
            "Clean Area",
            "clean_area",
        )

    @property
    def native_value(self) -> int | None:
        """Return the clean area in m²."""
        if self.coordinator.data:
            return self.coordinator.data.get(DPS_CLEAN_AREA)
        return None


class ProscenicLocalMainBrushSensor(ProscenicLocalSensorBase):
    """Main brush remaining time sensor for Proscenic."""

    _attr_device_class = SensorDeviceClass.DURATION
    _attr_native_unit_of_measurement = UnitOfTime.HOURS
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:brush"

    def __init__(
        self,
        coordinator: ProscenicLocalCoordinator,
        entry: ConfigEntry,
        device_name: str,
    ) -> None:
        """Initialize the main brush sensor."""
        super().__init__(
            coordinator,
            entry,
            device_name,
            "Main Brush Remaining",
            "main_brush",
        )

    @property
    def native_value(self) -> float | None:
        """Return the main brush remaining time in hours."""
        if self.coordinator.data:
            minutes = self.coordinator.data.get(DPS_MAIN_BRUSH)
            if minutes is not None:
                return round(minutes / 60, 1)
        return None


class ProscenicLocalSideBrushSensor(ProscenicLocalSensorBase):
    """Side brush remaining time sensor for Proscenic."""

    _attr_device_class = SensorDeviceClass.DURATION
    _attr_native_unit_of_measurement = UnitOfTime.HOURS
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:brush"

    def __init__(
        self,
        coordinator: ProscenicLocalCoordinator,
        entry: ConfigEntry,
        device_name: str,
    ) -> None:
        """Initialize the side brush sensor."""
        super().__init__(
            coordinator,
            entry,
            device_name,
            "Side Brush Remaining",
            "side_brush",
        )

    @property
    def native_value(self) -> float | None:
        """Return the side brush remaining time in hours."""
        if self.coordinator.data:
            minutes = self.coordinator.data.get(DPS_SIDE_BRUSH)
            if minutes is not None:
                return round(minutes / 60, 1)
        return None


class ProscenicLocalFilterSensor(ProscenicLocalSensorBase):
    """Filter remaining time sensor for Proscenic."""

    _attr_device_class = SensorDeviceClass.DURATION
    _attr_native_unit_of_measurement = UnitOfTime.HOURS
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:air-filter"

    def __init__(
        self,
        coordinator: ProscenicLocalCoordinator,
        entry: ConfigEntry,
        device_name: str,
    ) -> None:
        """Initialize the filter sensor."""
        super().__init__(
            coordinator,
            entry,
            device_name,
            "Filter Remaining",
            "filter",
        )

    @property
    def native_value(self) -> float | None:
        """Return the filter remaining time in hours."""
        if self.coordinator.data:
            minutes = self.coordinator.data.get(DPS_FILTER)
            if minutes is not None:
                return round(minutes / 60, 1)
        return None

