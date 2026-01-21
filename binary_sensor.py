from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import MessanaCoordinator


@dataclass(frozen=True)
class ZoneActiveRef:
    zone_id: int


class MessanaZoneActiveBinarySensor(CoordinatorEntity[MessanaCoordinator], BinarySensorEntity):
    _attr_has_entity_name = True
    _attr_device_class = "running"

    def __init__(self, coordinator: MessanaCoordinator, ref: ZoneActiveRef) -> None:
        super().__init__(coordinator)
        self._zone_id = ref.zone_id
        self._attr_unique_id = f"{DOMAIN}_zone_{self._zone_id}_active"

    @property
    def name(self) -> str:
        zone = (self.coordinator.data.get("zones", {}) or {}).get(self._zone_id, {})
        zname = zone.get("name") or f"Zone {self._zone_id}"
        return f"{zname} Active"

    @property
    def is_on(self) -> bool:
        zone = (self.coordinator.data.get("zones", {}) or {}).get(self._zone_id, {})
        return int(zone.get("thermal_status", 0) or 0) != 0

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator: MessanaCoordinator = data["coordinator"]

    zone_count = int(coordinator.data.get("system", {}).get("effective_zone_count", 0))

    entities: list[MessanaZoneActiveBinarySensor] = []
    for zid in range(zone_count):
        entities.append(MessanaZoneActiveBinarySensor(coordinator, ZoneActiveRef(zone_id=zid)))

    async_add_entities(entities)
