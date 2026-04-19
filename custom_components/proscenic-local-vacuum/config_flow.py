"""Config flow for Proscenic Local Vacuum integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_NAME, CONF_PASSWORD
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector
from homeassistant.helpers.device_registry import format_mac

from .const import (
    CONF_DEVICE_ID,
    CONF_LOCAL_KEY,
    CONF_MAC,
    CONF_POLL_INTERVAL,
    CONF_PROTOCOL_VERSION,
    DEFAULT_NAME,
    DEFAULT_POLL_INTERVAL,
    DEFAULT_PROTOCOL_VERSION,
    DOMAIN,
    TUYA_REGIONS,
)
from .coordinator import ProscenicLocalCoordinator
from .tuya_cloud import InvalidAuthentication, TuyaCloudApi, TuyaCloudApiError

_LOGGER = logging.getLogger(__name__)

CONF_EMAIL = "email"
CONF_REGION = "region"


def _normalize_mac(mac: str | None) -> str | None:
    """Normalize MAC for storage and device registry."""
    if not mac or not str(mac).strip():
        return None
    try:
        return format_mac(str(mac).strip())
    except ValueError:
        _LOGGER.warning("Ignoring invalid MAC address: %s", mac)
        return None

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_EMAIL): str,
        vol.Required(CONF_PASSWORD): str,
        vol.Required(CONF_REGION, default="eu"): selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=[
                    selector.SelectOptionDict(value=k, label=v)
                    for k, v in TUYA_REGIONS.items()
                ],
                mode=selector.SelectSelectorMode.DROPDOWN,
            ),
        ),
    }
)


def _reconfigure_connection_schema(entry: config_entries.ConfigEntry) -> vol.Schema:
    """Schema for editing LAN connection details (device ID is fixed)."""
    data = entry.data
    mac_default = data.get(CONF_MAC) or ""
    return vol.Schema(
        {
            vol.Required(CONF_HOST, default=data.get(CONF_HOST, "")): str,
            vol.Optional(CONF_MAC, default=mac_default): str,
            vol.Required(CONF_LOCAL_KEY, default=data.get(CONF_LOCAL_KEY, "")): str,
            vol.Optional(CONF_NAME, default=data.get(CONF_NAME, DEFAULT_NAME)): str,
            vol.Optional(
                CONF_PROTOCOL_VERSION,
                default=data.get(CONF_PROTOCOL_VERSION, DEFAULT_PROTOCOL_VERSION),
            ): vol.Coerce(float),
            vol.Optional(
                CONF_POLL_INTERVAL,
                default=data.get(CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL),
            ): vol.All(vol.Coerce(int), vol.Range(min=10, max=300)),
        }
    )


class ProscenicLocalConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Proscenic Local Vacuum."""

    VERSION = 2

    def __init__(self) -> None:
        """Initialize config flow."""
        self._email: str | None = None
        self._password: str | None = None
        self._region: str | None = None
        self._devices: list[dict[str, Any]] = []
        self._selected_device: dict[str, Any] | None = None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step - cloud credentials.

        Args:
            user_input: User input from the form

        Returns:
            Flow result
        """
        errors: dict[str, str] = {}

        if user_input is not None:
            self._email = user_input[CONF_EMAIL]
            self._password = user_input[CONF_PASSWORD]
            self._region = user_input[CONF_REGION]

            try:
                # Login to Tuya Cloud and get devices
                api = TuyaCloudApi(self._region, self._email, self._password)
                await self.hass.async_add_executor_job(api.login)
                self._devices = await self.hass.async_add_executor_job(api.list_devices)

                if not self._devices:
                    errors["base"] = "no_devices"
                else:
                    return await self.async_step_select_device()

            except InvalidAuthentication:
                errors["base"] = "invalid_auth"
            except TuyaCloudApiError as err:
                _LOGGER.error("Tuya Cloud API error: %s", err)
                errors["base"] = "cannot_connect"
            except Exception as err:
                _LOGGER.exception("Unexpected error during login: %s", err)
                errors["base"] = "unknown"

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
            description_placeholders={"app_name": "Proscenic Home"},
        )

    async def async_step_select_device(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle device selection step.

        Args:
            user_input: User input from the form

        Returns:
            Flow result
        """
        errors: dict[str, str] = {}

        if user_input is not None:
            device_id = user_input[CONF_DEVICE_ID]
            self._selected_device = next(
                (d for d in self._devices if d["id"] == device_id), None
            )
            if self._selected_device:
                # Check if IP was extracted from DPS 34
                if self._selected_device.get("ip"):
                    return await self.async_step_confirm_ip()
                else:
                    return await self.async_step_manual_ip()
            errors["base"] = "device_not_found"

        # Build device selection options
        device_options = [
            selector.SelectOptionDict(
                value=d["id"],
                label=f"{d['name']} ({d['id'][:8]}...)",
            )
            for d in self._devices
        ]

        return self.async_show_form(
            step_id="select_device",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_DEVICE_ID): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=device_options,
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        ),
                    ),
                }
            ),
            errors=errors,
        )

    async def async_step_confirm_ip(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle IP confirmation step (when IP was extracted from cloud).

        Args:
            user_input: User input from the form

        Returns:
            Flow result
        """
        errors: dict[str, str] = {}

        if self._selected_device is None:
            return self.async_abort(reason="device_not_found")

        suggested_ip = self._selected_device.get("ip", "")

        if user_input is not None:
            host = user_input[CONF_HOST]

            # Test connection
            if await self._test_connection(
                host,
                self._selected_device["id"],
                self._selected_device["local_key"],
            ):
                return await self.async_step_options(host=host)
            errors["base"] = "cannot_connect"

        return self.async_show_form(
            step_id="confirm_ip",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_HOST, default=suggested_ip): str,
                }
            ),
            errors=errors,
            description_placeholders={
                "device_name": self._selected_device.get("name", "Unknown"),
                "suggested_ip": suggested_ip,
            },
        )

    async def async_step_manual_ip(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle manual IP entry step.

        Args:
            user_input: User input from the form

        Returns:
            Flow result
        """
        errors: dict[str, str] = {}

        if self._selected_device is None:
            return self.async_abort(reason="device_not_found")

        if user_input is not None:
            host = user_input[CONF_HOST]

            # Test connection
            if await self._test_connection(
                host,
                self._selected_device["id"],
                self._selected_device["local_key"],
            ):
                return await self.async_step_options(host=host)
            errors["base"] = "cannot_connect"

        return self.async_show_form(
            step_id="manual_ip",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_HOST): str,
                }
            ),
            errors=errors,
            description_placeholders={
                "device_name": self._selected_device.get("name", "Unknown"),
            },
        )

    async def async_step_options(
        self, user_input: dict[str, Any] | None = None, host: str | None = None
    ) -> FlowResult:
        """Handle optional settings step.

        Args:
            user_input: User input from the form
            host: Device IP address from previous step

        Returns:
            Flow result
        """
        if self._selected_device is None:
            return self.async_abort(reason="device_not_found")

        # Store host from previous step
        if host is not None:
            self._host = host

        if user_input is not None:
            # Create config entry
            await self.async_set_unique_id(self._selected_device["id"])
            self._abort_if_unique_id_configured()

            return self.async_create_entry(
                title=user_input.get(CONF_NAME, self._selected_device.get("name", DEFAULT_NAME)),
                data={
                    CONF_HOST: self._host,
                    CONF_DEVICE_ID: self._selected_device["id"],
                    CONF_LOCAL_KEY: self._selected_device["local_key"],
                    CONF_MAC: _normalize_mac(self._selected_device.get("mac")),
                    CONF_NAME: user_input.get(CONF_NAME, self._selected_device.get("name", DEFAULT_NAME)),
                    CONF_PROTOCOL_VERSION: user_input.get(
                        CONF_PROTOCOL_VERSION, DEFAULT_PROTOCOL_VERSION
                    ),
                    CONF_POLL_INTERVAL: user_input.get(
                        CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL
                    ),
                },
            )

        return self.async_show_form(
            step_id="options",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_NAME,
                        default=self._selected_device.get("name", DEFAULT_NAME),
                    ): str,
                    vol.Optional(
                        CONF_PROTOCOL_VERSION, default=DEFAULT_PROTOCOL_VERSION
                    ): vol.Coerce(float),
                    vol.Optional(
                        CONF_POLL_INTERVAL, default=DEFAULT_POLL_INTERVAL
                    ): vol.All(vol.Coerce(int), vol.Range(min=10, max=300)),
                }
            ),
            description_placeholders={
                "device_name": self._selected_device.get("name", "Unknown"),
            },
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Let the user change host, keys, MAC, and related settings after setup."""
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}

        if user_input is not None:
            host = user_input[CONF_HOST]
            local_key = user_input[CONF_LOCAL_KEY]
            device_id = entry.data[CONF_DEVICE_ID]

            if await self._test_connection(host, device_id, local_key):
                await self.async_set_unique_id(entry.unique_id)
                self._abort_if_unique_id_mismatch()

                mac = _normalize_mac(user_input.get(CONF_MAC))
                data_updates: dict[str, Any] = {
                    CONF_HOST: host,
                    CONF_LOCAL_KEY: local_key,
                    CONF_MAC: mac,
                    CONF_NAME: user_input.get(CONF_NAME, entry.data.get(CONF_NAME, DEFAULT_NAME)),
                    CONF_PROTOCOL_VERSION: user_input.get(
                        CONF_PROTOCOL_VERSION,
                        entry.data.get(CONF_PROTOCOL_VERSION, DEFAULT_PROTOCOL_VERSION),
                    ),
                    CONF_POLL_INTERVAL: user_input.get(
                        CONF_POLL_INTERVAL,
                        entry.data.get(CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL),
                    ),
                }

                return self.async_update_reload_and_abort(
                    entry,
                    data_updates=data_updates,
                )

            errors["base"] = "cannot_connect"

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=_reconfigure_connection_schema(entry),
            errors=errors,
            description_placeholders={
                "device_name": entry.data.get(CONF_NAME, DEFAULT_NAME),
                "device_id": entry.data.get(CONF_DEVICE_ID, ""),
            },
        )

    async def async_step_manual(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle manual configuration (for YAML-like setup).

        Args:
            user_input: User input from the form

        Returns:
            Flow result
        """
        errors: dict[str, str] = {}

        if user_input is not None:
            host = user_input[CONF_HOST]
            device_id = user_input[CONF_DEVICE_ID]
            local_key = user_input[CONF_LOCAL_KEY]

            # Test connection
            if await self._test_connection(host, device_id, local_key):
                await self.async_set_unique_id(device_id)
                self._abort_if_unique_id_configured()

                return self.async_create_entry(
                    title=user_input.get(CONF_NAME, DEFAULT_NAME),
                    data={
                        CONF_HOST: host,
                        CONF_DEVICE_ID: device_id,
                        CONF_LOCAL_KEY: local_key,
                        CONF_MAC: _normalize_mac(user_input.get(CONF_MAC)),
                        CONF_NAME: user_input.get(CONF_NAME, DEFAULT_NAME),
                        CONF_PROTOCOL_VERSION: user_input.get(
                            CONF_PROTOCOL_VERSION, DEFAULT_PROTOCOL_VERSION
                        ),
                        CONF_POLL_INTERVAL: user_input.get(
                            CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL
                        ),
                    },
                )
            errors["base"] = "cannot_connect"

        return self.async_show_form(
            step_id="manual",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_HOST): str,
                    vol.Optional(CONF_MAC): str,
                    vol.Required(CONF_DEVICE_ID): str,
                    vol.Required(CONF_LOCAL_KEY): str,
                    vol.Optional(CONF_NAME, default=DEFAULT_NAME): str,
                    vol.Optional(
                        CONF_PROTOCOL_VERSION, default=DEFAULT_PROTOCOL_VERSION
                    ): vol.Coerce(float),
                    vol.Optional(
                        CONF_POLL_INTERVAL, default=DEFAULT_POLL_INTERVAL
                    ): vol.All(vol.Coerce(int), vol.Range(min=10, max=300)),
                }
            ),
            errors=errors,
        )

    async def _test_connection(
        self, host: str, device_id: str, local_key: str
    ) -> bool:
        """Test connection to the vacuum.

        Args:
            host: Device IP address
            device_id: Tuya device ID
            local_key: Tuya local key

        Returns:
            True if connection is successful
        """
        coordinator = ProscenicLocalCoordinator(
            self.hass,
            host=host,
            device_id=device_id,
            local_key=local_key,
        )
        return await coordinator.async_test_connection()

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Get options flow handler.

        Args:
            config_entry: Config entry

        Returns:
            Options flow handler
        """
        return ProscenicLocalOptionsFlow()


class ProscenicLocalOptionsFlow(config_entries.OptionsFlow):
    """Handle options flow for Proscenic Local."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Choose between polling settings and full device connection setup."""
        return self.async_show_menu(
            step_id="init",
            menu_options=["poll_interval", "device_connection"],
        )

    async def async_step_poll_interval(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Adjust polling interval (stored in config entry data)."""
        entry = self.config_entry
        errors: dict[str, str] = {}

        if user_input is not None:
            interval = user_input[CONF_POLL_INTERVAL]
            new_data = {**dict(entry.data), CONF_POLL_INTERVAL: interval}
            self.hass.config_entries.async_update_entry(entry, data=new_data)
            preserved = dict(entry.options)
            return self.async_create_entry(title="", data=preserved)

        return self.async_show_form(
            step_id="poll_interval",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_POLL_INTERVAL,
                        default=entry.data.get(
                            CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL
                        ),
                    ): vol.All(vol.Coerce(int), vol.Range(min=10, max=300)),
                }
            ),
            errors=errors,
        )

    async def async_step_device_connection(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Update host, local key, MAC, and related fields (same as Reconfigure)."""
        entry = self.config_entry
        errors: dict[str, str] = {}

        if user_input is not None:
            host = user_input[CONF_HOST]
            local_key = user_input[CONF_LOCAL_KEY]
            device_id = entry.data[CONF_DEVICE_ID]

            test_coordinator = ProscenicLocalCoordinator(
                self.hass,
                host=host,
                device_id=device_id,
                local_key=local_key,
                protocol_version=float(
                    user_input.get(
                        CONF_PROTOCOL_VERSION,
                        entry.data.get(CONF_PROTOCOL_VERSION, DEFAULT_PROTOCOL_VERSION),
                    )
                ),
                poll_interval=int(
                    user_input.get(
                        CONF_POLL_INTERVAL,
                        entry.data.get(CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL),
                    )
                ),
            )
            if await test_coordinator.async_test_connection():
                mac = _normalize_mac(user_input.get(CONF_MAC))
                new_data = {
                    **dict(entry.data),
                    CONF_HOST: host,
                    CONF_LOCAL_KEY: local_key,
                    CONF_MAC: mac,
                    CONF_NAME: user_input.get(
                        CONF_NAME, entry.data.get(CONF_NAME, DEFAULT_NAME)
                    ),
                    CONF_PROTOCOL_VERSION: user_input.get(
                        CONF_PROTOCOL_VERSION,
                        entry.data.get(CONF_PROTOCOL_VERSION, DEFAULT_PROTOCOL_VERSION),
                    ),
                    CONF_POLL_INTERVAL: user_input.get(
                        CONF_POLL_INTERVAL,
                        entry.data.get(CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL),
                    ),
                }
                self.hass.config_entries.async_update_entry(entry, data=new_data)
                preserved = dict(entry.options)
                return self.async_create_entry(title="", data=preserved)

            errors["base"] = "cannot_connect"

        return self.async_show_form(
            step_id="device_connection",
            data_schema=_reconfigure_connection_schema(entry),
            errors=errors,
            description_placeholders={
                "device_name": entry.data.get(CONF_NAME, DEFAULT_NAME),
                "device_id": entry.data.get(CONF_DEVICE_ID, ""),
            },
        )

