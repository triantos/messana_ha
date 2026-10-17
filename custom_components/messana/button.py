from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import slugify

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
        entities.append(MessanaUseMacrozoneDefaultButton(coordinator, zid, zone_name))

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
        super().__init__(coordinator, zone_id=zone_id, zone_name=zone_name)
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
        return super().available and int(z.get("schedule_on") or 0) == 1

    async def async_press(self) -> None:
        await self.coordinator.client.set_zone_schedule_on(self.zone_id, False)
        await self.coordinator.async_request_refresh()


class MessanaUseMacrozoneDefaultButton(MessanaEntity, ButtonEntity):
    """Copy the group's current default into this room without changing schedules."""

    _attr_icon = "mdi:home-thermometer"
    _attr_name = "Use macrozone default"

    def __init__(self, coordinator, zone_id: int, zone_name: str) -> None:
        super().__init__(coordinator, zone_id=zone_id, zone_name=zone_name)
        self.zone_id = zone_id
        self._attr_unique_id = f"messana_zone_{zone_id}_use_macrozone_default"
        zone = coordinator.data.get("zones", {}).get(zone_id, {})
        self._attr_name = "Copy global default" if zone.get("macrozone_id") == 0 else "Copy macrozone default"

    @property
    def available(self) -> bool:
        zone = self.coordinator.data.get("zones", {}).get(self.zone_id, {})
        return super().available and zone.get("macrozone_default") is not None

    async def async_press(self) -> None:
        if not self.available:
            raise HomeAssistantError("The macrozone default temperature is unavailable")
        zone = self.coordinator.data["zones"][self.zone_id]
        try:
            await self.coordinator.client.set_zone_setpoint(self.zone_id, zone["macrozone_default"])
        finally:
            await self.coordinator.async_request_refresh()
