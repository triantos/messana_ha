from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.entity import EntityCategory

from .const import DOMAIN
from .coordinator import MessanaCoordinator
from .entity import MessanaEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator: MessanaCoordinator = data["coordinator"]

    zone_count = int(coordinator.data.get("system", {}).get("effective_zone_count", 0))

    entities: list[ButtonEntity] = []
    for zid in range(zone_count):
        entities.append(MessanaDetachScheduleButton(coordinator, zid))

    async_add_entities(entities)


class MessanaDetachScheduleButton(MessanaEntity, ButtonEntity):
    """Button to detach a zone from schedule control (scheduleOn -> 0)."""

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:calendar-remove"

    def __init__(self, coordinator: MessanaCoordinator, zone_id: int) -> None:
        super().__init__(coordinator)
        self.zone_id = zone_id
        self._attr_unique_id = f"messana_zone_{zone_id}_detach_schedule"
        self._attr_name = "Detach schedule"

    @property
    def available(self) -> bool:
        # Only show as "available" when schedule control is currently enabled for the zone
        z = (self.coordinator.data or {}).get("zones", {}).get(self.zone_id, {})
        return int(z.get("schedule_on") or 0) == 1

    async def async_press(self) -> None:
        await self.coordinator.client.set_zone_schedule_on(self.zone_id, False)
        await self.coordinator.async_request_refresh()
