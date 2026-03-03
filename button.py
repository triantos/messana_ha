from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import slugify
from homeassistant.helpers import entity_registry as er

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

    await coordinator.async_config_entry_first_refresh()

    zone_count = int(coordinator.data.get("system", {}).get("effective_zone_count", 0))

    entities: list[ButtonEntity] = []
    for zid in range(zone_count):
        z = (coordinator.data or {}).get("zones", {}).get(zid, {}) or {}
        zone_name = (
            z.get("name")
            or z.get("label")
            or z.get("display_name")
            or f"Zone {zid + 1}"
        )

        entities.append(
            MessanaDetachScheduleButton(
                coordinator=coordinator,
                entry_id=entry.entry_id,
                zone_id=zid,
                zone_name=zone_name,
            )
        )

    async_add_entities(entities)

class MessanaDetachScheduleButton(MessanaEntity, ButtonEntity):
    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:calendar-remove"

    def __init__(
        self,
        coordinator: MessanaCoordinator,
        entry_id: str,
        zone_id: int,
        zone_name: str,
    ) -> None:
        super().__init__(coordinator)
        self.zone_id = zone_id

        # New unique_id (entry-scoped)
        self._attr_unique_id = f"{entry_id}_messana_zone_{zone_id}_detach_schedule"

        # UI label (paired with zone name in UI because has_entity_name=True)
        self._attr_name = "Detach schedule"

        zone_slug = slugify(zone_name) or f"zone_{zone_id + 1}"
        self._attr_suggested_object_id = f"{zone_slug}_detach_schedule"

    @property
    def available(self) -> bool:
        z = (self.coordinator.data or {}).get("zones", {}).get(self.zone_id, {})
        return int(z.get("schedule_on") or 0) == 1

    async def async_press(self) -> None:
        await self.coordinator.client.set_zone_schedule_on(self.zone_id, False)
        await self.coordinator.async_request_refresh()
