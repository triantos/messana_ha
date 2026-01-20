from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .api import MessanaClient
from .const import (
    DOMAIN,
    PLATFORMS,
    CONF_BASE_URL,
    CONF_API_KEY,
    CONF_SCAN_INTERVAL,
    CONF_ZONE_COUNT_OVERRIDE,
    DEFAULT_SCAN_INTERVAL_SECONDS,
    DEFAULT_ZONE_COUNT_OVERRIDE,
)
from .coordinator import MessanaCoordinator


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    base_url = entry.data[CONF_BASE_URL]
    api_key = entry.data[CONF_API_KEY]

    scan_interval = int(entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL_SECONDS))
    zone_count_override = int(entry.options.get(CONF_ZONE_COUNT_OVERRIDE, DEFAULT_ZONE_COUNT_OVERRIDE))

    client = MessanaClient(hass=hass, base_url=base_url, api_key=api_key)
    coordinator = MessanaCoordinator(
        hass,
        client,
        scan_interval_seconds=scan_interval,
        zone_count_override=zone_count_override,
    )
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "client": client,
        "coordinator": coordinator,
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unloaded
