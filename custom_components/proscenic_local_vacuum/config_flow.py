"""Config flow for Proscenic Local Vacuum integration."""
from __future__ import annotations

from collections.abc import Mapping
import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_HOST, CONF_NAME, CONF_PASSWORD
from homeassistant.core import callback
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
    MAX_POLL_INTERVAL,
    MIN_POLL_INTERVAL,
    PROTOCOL_VERSIONS,
    TUYA_REGIONS,
)
from .device import async_test_connection
from .tuya_cloud import InvalidAuthentication, TuyaCloudApi, TuyaCloudApiError

_LOGGER = logging.getLogger(__name__)

CONF_EMAIL = "email"
CONF_REGION = "region"

POLL_INTERVAL_VALIDATOR = vol.All(
    vol.Coerce(int), vol.Range(min=MIN_POLL_INTERVAL, max=MAX_POLL_INTERVAL)
)

PROTOCOL_VERSION_SELECTOR = selector.SelectSelector(
    selector.SelectSelectorConfig(
        options=PROTOCOL_VERSIONS,
        mode=selector.SelectSelectorMode.DROPDOWN,
    )
)

STEP_CLOUD_DATA_SCHEMA = vol.Schema(
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


def _normalize_mac(mac: str | None) -> str | None:
    """Normalize MAC for storage and device registry."""
    if not mac or not str(mac).strip():
        return None
    try:
        return format_mac(str(mac).strip())
    except ValueError:
        _LOGGER.warning("Ignoring invalid MAC address: %s", mac)
        return None


def _connection_schema(
    defaults: Mapping[str, Any],
    *,
    credentials: bool,
    device_id: bool = False,
    poll_interval: bool = False,
) -> vol.Schema:
    """Build the LAN connection form.

    Args:
        defaults: Values to pre-fill
        credentials: Ask for MAC and local key (not needed when they come from the cloud)
        device_id: Ask for the Tuya device ID (manual setup only)
        poll_interval: Ask for the polling interval (initial setup only)
    """
    schema: dict[vol.Marker, Any] = {
        vol.Required(CONF_HOST, default=defaults.get(CONF_HOST) or ""): str,
    }
    if credentials:
        schema[
            vol.Optional(
                CONF_MAC, description={"suggested_value": defaults.get(CONF_MAC)}
            )
        ] = str
        if device_id:
            schema[
                vol.Required(CONF_DEVICE_ID, default=defaults.get(CONF_DEVICE_ID, ""))
            ] = str
        schema[
            vol.Required(CONF_LOCAL_KEY, default=defaults.get(CONF_LOCAL_KEY, ""))
        ] = str
    schema[vol.Required(CONF_NAME, default=defaults.get(CONF_NAME, DEFAULT_NAME))] = str
    schema[
        vol.Required(
            CONF_PROTOCOL_VERSION,
            default=str(defaults.get(CONF_PROTOCOL_VERSION, DEFAULT_PROTOCOL_VERSION)),
        )
    ] = PROTOCOL_VERSION_SELECTOR
    if poll_interval:
        schema[
            vol.Required(
                CONF_POLL_INTERVAL,
                default=defaults.get(CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL),
            )
        ] = POLL_INTERVAL_VALIDATOR
    return vol.Schema(schema)


class ProscenicLocalConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Proscenic Local Vacuum."""

    VERSION = 3

    def __init__(self) -> None:
        """Initialize config flow."""
        self._devices: list[dict[str, Any]] = []
        self._selected_device: dict[str, Any] | None = None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Let the user choose between cloud discovery and manual setup."""
        return self.async_show_menu(step_id="user", menu_options=["cloud", "manual"])

    async def async_step_cloud(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Log in to the Proscenic cloud and fetch the account's devices."""
        errors: dict[str, str] = {}

        if user_input is not None:
            api = TuyaCloudApi(
                user_input[CONF_REGION], user_input[CONF_EMAIL], user_input[CONF_PASSWORD]
            )
            try:
                await self.hass.async_add_executor_job(api.login)
                self._devices = await self.hass.async_add_executor_job(api.list_devices)
            except InvalidAuthentication:
                errors["base"] = "invalid_auth"
            except TuyaCloudApiError as err:
                _LOGGER.error("Tuya Cloud API error: %s", err)
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected error during login")
                errors["base"] = "unknown"
            else:
                if self._devices:
                    return await self.async_step_select_device()
                errors["base"] = "no_devices"

        return self.async_show_form(
            step_id="cloud",
            data_schema=STEP_CLOUD_DATA_SCHEMA,
            errors=errors,
            description_placeholders={"app_name": "Proscenic Home"},
        )

    async def async_step_select_device(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Pick one of the devices found in the cloud account."""
        if user_input is not None:
            device_id = user_input[CONF_DEVICE_ID]
            self._selected_device = next(
                (d for d in self._devices if d["id"] == device_id), None
            )
            if self._selected_device is None:
                return self.async_abort(reason="device_not_found")

            await self.async_set_unique_id(device_id)
            self._abort_if_unique_id_configured()
            return await self.async_step_device()

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
        )

    async def async_step_device(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm LAN settings for the device selected from the cloud."""
        device = self._selected_device
        if device is None:
            return self.async_abort(reason="device_not_found")

        errors: dict[str, str] = {}

        if user_input is not None:
            if await async_test_connection(
                self.hass,
                user_input[CONF_HOST],
                device["id"],
                device["local_key"],
                float(user_input[CONF_PROTOCOL_VERSION]),
            ):
                return self._create_entry(
                    user_input, device["id"], device["local_key"], device.get("mac")
                )
            errors["base"] = "cannot_connect"

        defaults = user_input or {
            CONF_HOST: device.get("ip"),
            CONF_NAME: device.get("name") or DEFAULT_NAME,
        }
        return self.async_show_form(
            step_id="device",
            data_schema=_connection_schema(
                defaults, credentials=False, poll_interval=True
            ),
            errors=errors,
            description_placeholders={"device_name": device.get("name", DEFAULT_NAME)},
        )

    async def async_step_manual(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Set up a device with a known device ID and local key."""
        errors: dict[str, str] = {}

        if user_input is not None:
            device_id = user_input[CONF_DEVICE_ID].strip()
            await self.async_set_unique_id(device_id)
            self._abort_if_unique_id_configured()

            if await async_test_connection(
                self.hass,
                user_input[CONF_HOST],
                device_id,
                user_input[CONF_LOCAL_KEY],
                float(user_input[CONF_PROTOCOL_VERSION]),
            ):
                return self._create_entry(
                    user_input,
                    device_id,
                    user_input[CONF_LOCAL_KEY],
                    user_input.get(CONF_MAC),
                )
            errors["base"] = "cannot_connect"

        return self.async_show_form(
            step_id="manual",
            data_schema=_connection_schema(
                user_input or {}, credentials=True, device_id=True, poll_interval=True
            ),
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Let the user change host, local key, MAC, and protocol after setup."""
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}

        if user_input is not None:
            protocol_version = float(user_input[CONF_PROTOCOL_VERSION])
            if await async_test_connection(
                self.hass,
                user_input[CONF_HOST],
                entry.data[CONF_DEVICE_ID],
                user_input[CONF_LOCAL_KEY],
                protocol_version,
            ):
                return self.async_update_reload_and_abort(
                    entry,
                    title=user_input[CONF_NAME],
                    data_updates={
                        CONF_HOST: user_input[CONF_HOST],
                        CONF_LOCAL_KEY: user_input[CONF_LOCAL_KEY],
                        CONF_MAC: _normalize_mac(user_input.get(CONF_MAC)),
                        CONF_PROTOCOL_VERSION: protocol_version,
                    },
                )
            errors["base"] = "cannot_connect"

        defaults = user_input or {**entry.data, CONF_NAME: entry.title}
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=_connection_schema(defaults, credentials=True),
            errors=errors,
            description_placeholders={
                "device_name": entry.title,
                "device_id": entry.data[CONF_DEVICE_ID],
            },
        )

    @callback
    def _create_entry(
        self,
        user_input: dict[str, Any],
        device_id: str,
        local_key: str,
        mac: str | None,
    ) -> ConfigFlowResult:
        return self.async_create_entry(
            title=user_input[CONF_NAME],
            data={
                CONF_HOST: user_input[CONF_HOST],
                CONF_DEVICE_ID: device_id,
                CONF_LOCAL_KEY: local_key,
                CONF_MAC: _normalize_mac(mac),
                CONF_PROTOCOL_VERSION: float(user_input[CONF_PROTOCOL_VERSION]),
            },
            options={CONF_POLL_INTERVAL: user_input[CONF_POLL_INTERVAL]},
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Get the options flow handler."""
        return ProscenicLocalOptionsFlow()


class ProscenicLocalOptionsFlow(OptionsFlow):
    """Adjust the polling interval."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_POLL_INTERVAL,
                        default=self.config_entry.options.get(
                            CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL
                        ),
                    ): POLL_INTERVAL_VALIDATOR,
                }
            ),
        )
