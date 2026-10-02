"""The Proscenic Local Vacuum integration."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME, Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr, entity_registry as er

from .const import (
    CONF_DEVICE_ID,
    CONF_MAC,
    CONF_POLL_INTERVAL,
    DEFAULT_POLL_INTERVAL,
    DOMAIN,
)
from .coordinator import (
    ProscenicConfigEntry,
    ProscenicLocalCoordinator,
    get_poll_interval,
)

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.VACUUM]


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate config entries to the latest schema."""
    if entry.version > 3:
        return False

    if entry.version == 1:
        hass.config_entries.async_update_entry(
            entry, data={CONF_MAC: None, **entry.data}, version=2
        )

    if entry.version == 2:
        await _async_migrate_ids_to_device_id(hass, entry)

        data = dict(entry.data)
        poll_interval = data.pop(CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL)
        name = data.pop(CONF_NAME, None)
        hass.config_entries.async_update_entry(
            entry,
            title=name or entry.title,
            data=data,
            options={**entry.options, CONF_POLL_INTERVAL: poll_interval},
            version=3,
        )

    _LOGGER.debug("Migrated config entry %s to version %s", entry.entry_id, entry.version)
    return True


async def _async_migrate_ids_to_device_id(
    hass: HomeAssistant, entry: ConfigEntry
) -> None:
    """Re-key the device and entities from the config entry ID to the Tuya device ID."""
    old_id = entry.entry_id
    device_id = entry.data[CONF_DEVICE_ID]

    @callback
    def _migrate_unique_id(entity_entry: er.RegistryEntry) -> dict[str, Any] | None:
        unique_id = entity_entry.unique_id
        if unique_id == old_id or unique_id.startswith(f"{old_id}_"):
            return {"new_unique_id": device_id + unique_id[len(old_id) :]}
        return None

    await er.async_migrate_entries(hass, entry.entry_id, _migrate_unique_id)

    device_registry = dr.async_get(hass)
    if device := device_registry.async_get_device(identifiers={(DOMAIN, old_id)}):
        device_registry.async_update_device(
            device.id, new_identifiers={(DOMAIN, device_id)}
        )


async def async_setup_entry(hass: HomeAssistant, entry: ProscenicConfigEntry) -> bool:
    """Set up Proscenic Local Vacuum from a config entry."""
    coordinator = ProscenicLocalCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ProscenicConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_update_listener(
    hass: HomeAssistant, entry: ProscenicConfigEntry
) -> None:
    """Apply option changes without reloading.

    Connection changes go through the reconfigure flow, which reloads on its own;
    host updates written by LAN rediscovery must not trigger a reload either.
    """
    entry.runtime_data.update_interval = get_poll_interval(entry)
