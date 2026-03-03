from __future__ import annotations

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult

from .api import MessanaClient, MessanaApiError, MessanaAuthError
from .const import (
    DOMAIN,
    CONF_BASE_URL,
    CONF_API_KEY,
    CONF_SCAN_INTERVAL,
    CONF_ZONE_COUNT_OVERRIDE,
    DEFAULT_SCAN_INTERVAL_SECONDS,
    DEFAULT_ZONE_COUNT_OVERRIDE,
)


async def _validate(hass: HomeAssistant, base_url: str, api_key: str) -> None:
    client = MessanaClient(hass=hass, base_url=base_url, api_key=api_key)
    await client.get_system_status()


class MessanaConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input: dict | None = None) -> FlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            base_url = user_input[CONF_BASE_URL]
            api_key = user_input[CONF_API_KEY]
            try:
                await _validate(self.hass, base_url, api_key)
                return self.async_create_entry(
                    title="Messana",
                    data={CONF_BASE_URL: base_url, CONF_API_KEY: api_key},
                    options={
                        CONF_SCAN_INTERVAL: DEFAULT_SCAN_INTERVAL_SECONDS,
                        CONF_ZONE_COUNT_OVERRIDE: DEFAULT_ZONE_COUNT_OVERRIDE,
                    },
                )
            except MessanaAuthError:
                errors["base"] = "auth"
            except MessanaApiError:
                errors["base"] = "cannot_connect"
            except Exception:
                errors["base"] = "unknown"

        schema = vol.Schema(
            {
                vol.Required(CONF_BASE_URL, default="http://192.168.1.50"): str,
                vol.Required(CONF_API_KEY): str,
                vol.Optional(CONF_DETACH_ON_SETPOINT, default=options.get(CONF_DETACH_ON_SETPOINT, True)): bool,
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    @staticmethod
    def async_get_options_flow(config_entry: config_entries.ConfigEntry) -> config_entries.OptionsFlow:
        return MessanaOptionsFlowHandler(config_entry)


class MessanaOptionsFlowHandler(config_entries.OptionsFlow):
    def __init__(self, entry: config_entries.ConfigEntry) -> None:
        self._entry = entry

    async def async_step_init(self, user_input: dict | None = None) -> FlowResult:
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        current_scan = int(self._entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL_SECONDS))
        current_override = int(self._entry.options.get(CONF_ZONE_COUNT_OVERRIDE, DEFAULT_ZONE_COUNT_OVERRIDE))

        schema = vol.Schema(
            {
                vol.Required(CONF_SCAN_INTERVAL, default=current_scan): vol.All(
                    vol.Coerce(int), vol.Range(min=5, max=3600)
                ),
                vol.Required(CONF_ZONE_COUNT_OVERRIDE, default=current_override): vol.All(
                    vol.Coerce(int), vol.Range(min=0, max=256)
                ),
            }
        )

        return self.async_show_form(step_id="init", data_schema=schema)
