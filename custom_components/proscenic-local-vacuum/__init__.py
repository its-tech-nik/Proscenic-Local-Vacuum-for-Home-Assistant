"""The Proscenic Local Vacuum integration."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_NAME, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.device_registry import format_mac

from .const import (
    CONF_DEVICE_ID,
    CONF_LOCAL_KEY,
    CONF_MAC,
    CONF_POLL_INTERVAL,
    CONF_PROTOCOL_VERSION,
    DEFAULT_POLL_INTERVAL,
    DEFAULT_PROTOCOL_VERSION,
    DOMAIN,
)
from .coordinator import ProscenicLocalCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.VACUUM, Platform.SENSOR]


def _only_host_changed_in_data(
    previous: dict[str, Any] | None, current: dict[str, Any]
) -> bool:
    """Return True if current entry data differs from previous only by CONF_HOST."""
    if previous is None:
        return False
    if previous == current:
        return False
    prev_rest = {k: v for k, v in previous.items() if k != CONF_HOST}
    cur_rest = {k: v for k, v in current.items() if k != CONF_HOST}
    return prev_rest == cur_rest and previous.get(CONF_HOST) != current.get(CONF_HOST)


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate config entries to the latest schema."""
    if entry.version > 2:
        return False

    if entry.version == 2:
        return True

    data = {**entry.data}
    if CONF_MAC not in data:
        data[CONF_MAC] = None
    hass.config_entries.async_update_entry(entry, version=2, data=data)

    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Proscenic Local Vacuum from a config entry.

    Args:
        hass: Home Assistant instance
        entry: Config entry

    Returns:
        True if setup was successful

    Raises:
        ConfigEntryNotReady: If the device is not available
    """
    hass.data.setdefault(DOMAIN, {})

    # Extract configuration
    host = entry.data[CONF_HOST]
    device_id = entry.data[CONF_DEVICE_ID]
    local_key = entry.data[CONF_LOCAL_KEY]
    protocol_version = entry.data.get(CONF_PROTOCOL_VERSION, DEFAULT_PROTOCOL_VERSION)
    poll_interval = entry.data.get(CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL)
    raw_mac = entry.data.get(CONF_MAC)
    device_mac: str | None = None
    if raw_mac:
        try:
            device_mac = format_mac(str(raw_mac))
        except ValueError:
            _LOGGER.warning("Invalid stored MAC ignored: %s", raw_mac)

    # Create coordinator
    coordinator = ProscenicLocalCoordinator(
        hass,
        host=host,
        device_id=device_id,
        local_key=local_key,
        protocol_version=protocol_version,
        poll_interval=poll_interval,
        config_entry=entry,
        device_mac=device_mac,
    )
    coordinator.note_config_entry_data(dict(entry.data))

    # Fetch initial data
    await coordinator.async_config_entry_first_refresh()

    # Store coordinator
    hass.data[DOMAIN][entry.entry_id] = coordinator

    # Set up platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Register update listener for options
    entry.async_on_unload(entry.add_update_listener(async_update_options))

    _LOGGER.info(
        "Proscenic Local Vacuum '%s' set up successfully",
        entry.data.get(CONF_NAME, "Unknown"),
    )

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry.

    Args:
        hass: Home Assistant instance
        entry: Config entry

    Returns:
        True if unload was successful
    """
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok


async def async_update_options(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options update.

    Args:
        hass: Home Assistant instance
        entry: Config entry
    """
    coordinator: ProscenicLocalCoordinator | None = hass.data.get(DOMAIN, {}).get(
        entry.entry_id
    )
    if coordinator is not None and _only_host_changed_in_data(
        coordinator.entry_data_snapshot, dict(entry.data)
    ):
        coordinator.set_host(entry.data[CONF_HOST])
        coordinator.note_config_entry_data(dict(entry.data))
        return

    hass.config_entries.async_schedule_reload(entry.entry_id)

