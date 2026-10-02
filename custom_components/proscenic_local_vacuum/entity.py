"""Base entity for the Proscenic Local Vacuum integration."""
from __future__ import annotations

from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import ProscenicLocalCoordinator


class ProscenicLocalEntity(CoordinatorEntity[ProscenicLocalCoordinator]):
    """Common device info for all Proscenic entities."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: ProscenicLocalCoordinator) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.device_id)},
            name=coordinator.config_entry.title,
            manufacturer="Proscenic",
        )
        if coordinator.device_mac:
            self._attr_device_info["connections"] = {
                (CONNECTION_NETWORK_MAC, coordinator.device_mac)
            }
