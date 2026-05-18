from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import MessanaCoordinator
from .entity import MessanaEntity


@dataclass(frozen=True)
class ZoneActiveRef:
    zone_id: int


class MessanaZoneActiveBinarySensor(MessanaEntity, BinarySensorEntity):
    _attr_has_entity_name = True
    _attr_device_class = "running"

    def __init__(
        self,
        coordinator: MessanaCoordinator,
        ref: ZoneActiveRef,
        zone_name: str | None,
    ) -> None:
        super().__init__(coordinator, zone_id=ref.zone_id, zone_name=zone_name)
        self._attr_unique_id = f"{DOMAIN}_zone_{self._zone_id}_active"

    @property
    def name(self) -> str:
        return "Active"

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
        zone_name = (coordinator.data.get("zones", {}).get(zid, {}) or {}).get("name")
        entities.append(MessanaZoneActiveBinarySensor(coordinator, ZoneActiveRef(zone_id=zid), zone_name))

    async_add_entities(entities)
