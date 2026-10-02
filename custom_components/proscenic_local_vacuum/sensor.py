"""Sensor entities for Proscenic Local vacuum."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, UnitOfArea, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import StateType

from .const import (
    DPS_BATTERY,
    DPS_CLEAN_AREA,
    DPS_CLEAN_TIME,
    DPS_FILTER,
    DPS_MAIN_BRUSH,
    DPS_SIDE_BRUSH,
)
from .coordinator import ProscenicConfigEntry, ProscenicLocalCoordinator
from .entity import ProscenicLocalEntity


def _minutes_to_hours(minutes: Any) -> float:
    return round(minutes / 60, 1)


@dataclass(frozen=True, kw_only=True)
class ProscenicSensorEntityDescription(SensorEntityDescription):
    """Describes a sensor backed by a single DPS value."""

    dps: str
    value_fn: Callable[[Any], StateType] = lambda value: value


SENSORS: tuple[ProscenicSensorEntityDescription, ...] = (
    ProscenicSensorEntityDescription(
        key="battery",
        dps=DPS_BATTERY,
        device_class=SensorDeviceClass.BATTERY,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    ProscenicSensorEntityDescription(
        key="clean_time",
        translation_key="clean_time",
        dps=DPS_CLEAN_TIME,
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.MINUTES,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    ProscenicSensorEntityDescription(
        key="clean_area",
        translation_key="clean_area",
        dps=DPS_CLEAN_AREA,
        device_class=SensorDeviceClass.AREA,
        native_unit_of_measurement=UnitOfArea.SQUARE_METERS,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    ProscenicSensorEntityDescription(
        key="main_brush",
        translation_key="main_brush_remaining",
        dps=DPS_MAIN_BRUSH,
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.HOURS,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_minutes_to_hours,
    ),
    ProscenicSensorEntityDescription(
        key="side_brush",
        translation_key="side_brush_remaining",
        dps=DPS_SIDE_BRUSH,
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.HOURS,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_minutes_to_hours,
    ),
    ProscenicSensorEntityDescription(
        key="filter",
        translation_key="filter_remaining",
        dps=DPS_FILTER,
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.HOURS,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_minutes_to_hours,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ProscenicConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Proscenic Local sensors from a config entry."""
    coordinator = entry.runtime_data
    async_add_entities(
        ProscenicLocalSensor(coordinator, description) for description in SENSORS
    )


class ProscenicLocalSensor(ProscenicLocalEntity, SensorEntity):
    """Sensor reporting a single DPS value."""

    entity_description: ProscenicSensorEntityDescription

    def __init__(
        self,
        coordinator: ProscenicLocalCoordinator,
        description: ProscenicSensorEntityDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.device_id}_{description.key}"

    @property
    def native_value(self) -> StateType:
        """Return the sensor value."""
        if not self.coordinator.data:
            return None
        value = self.coordinator.data.get(self.entity_description.dps)
        if value is None:
            return None
        return self.entity_description.value_fn(value)
