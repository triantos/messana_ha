from __future__ import annotations

from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.components.sensor import SensorEntity

from .const import DOMAIN
from .coordinator import MessanaCoordinator
from .diagnostic import MessanaRawSampleSensor


def _ha_temp_unit(messana_unit: str) -> UnitOfTemperature:
    if messana_unit.lower().startswith("f"):
        return UnitOfTemperature.FAHRENHEIT
    return UnitOfTemperature.CELSIUS


@dataclass(frozen=True)
class ZoneSensorDef:
    key: str
    suffix: str
    native_unit: str | None


ZONE_SENSORS = [
    ZoneSensorDef(key="humidity", suffix="Humidity", native_unit=PERCENTAGE),
    ZoneSensorDef(key="dewpoint", suffix="Dew Point", native_unit=None),  # temp unit is system tempUnit
]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator: MessanaCoordinator = data["coordinator"]

    # Create sensors based on effective zone count for the same reason as climate.py.
    zone_count = int(coordinator.data.get("system", {}).get("effective_zone_count", 0))

    entities: list[MessanaZoneSensor] = []
    for zid in range(zone_count):
        for sdef in ZONE_SENSORS:
            entities.append(MessanaZoneSensor(coordinator, zid, sdef))
    
    entities.append(MessanaRawSampleSensor(coordinator))


    async_add_entities(entities)


class MessanaZoneSensor(CoordinatorEntity[MessanaCoordinator], SensorEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator: MessanaCoordinator, zone_id: int, sdef: ZoneSensorDef) -> None:
        super().__init__(coordinator)
        self.zone_id = zone_id
        self.sdef = sdef
        self._attr_unique_id = f"messana_zone_{zone_id}_{sdef.key}"
        self._attr_native_unit_of_measurement = sdef.native_unit

    @property
    def name(self) -> str:
        z = self.coordinator.data["zones"].get(self.zone_id, {})
        zone_name = z.get("name", f"Zone {self.zone_id}")
        return f"{zone_name} {self.sdef.suffix}"

    @property
    def native_unit_of_measurement(self) -> str | None:
        if self.sdef.key == "dewpoint":
            unit = self.coordinator.data.get("system", {}).get("temp_unit", "Celsius")
            return _ha_temp_unit(unit)
        return self._attr_native_unit_of_measurement

    @property
    def native_value(self):
        z = self.coordinator.data["zones"].get(self.zone_id, {})
        return z.get(self.sdef.key)
