from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.components.switch import SwitchEntity

from .const import DOMAIN
from .coordinator import MessanaCoordinator
from .api import MessanaClient
from .entity import MessanaEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator: MessanaCoordinator = data["coordinator"]
    client: MessanaClient = data["client"]
    async_add_entities([MessanaSystemPowerSwitch(coordinator, client)])


class MessanaSystemPowerSwitch(MessanaEntity, SwitchEntity):
    _attr_has_entity_name = True
    _attr_name = "System Power"

    def __init__(self, coordinator: MessanaCoordinator, client: MessanaClient) -> None:
        super().__init__(coordinator)
        self.client = client
        self._attr_unique_id = "messana_system_power"

    @property
    def is_on(self) -> bool:
        return bool(self.coordinator.data.get("system", {}).get("status", 0))

    async def async_turn_on(self, **kwargs) -> None:
        await self.client.set_system_status(True)  # :contentReference[oaicite:38]{index=38}
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs) -> None:
        await self.client.set_system_status(False)  # :contentReference[oaicite:39]{index=39}
        await self.coordinator.async_request_refresh()
