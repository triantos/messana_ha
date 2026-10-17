"""Stored room and macrozone defaults, independent of active schedules."""
from __future__ import annotations

import math

from homeassistant.components.number import NumberDeviceClass, NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .entity import MessanaEntity


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry,
                            async_add_entities: AddEntitiesCallback) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    entities = [MessanaDefaultTemperature(coordinator, zid)
                for zid in coordinator.data.get("zones", {})]
    entities.extend(MessanaDefaultTemperature(coordinator, mid, macrozone=True)
                    for mid in coordinator.data.get("macrozones", {}))
    async_add_entities(entities)


class MessanaDefaultTemperature(MessanaEntity, NumberEntity):
    _attr_device_class = NumberDeviceClass.TEMPERATURE
    _attr_mode = NumberMode.BOX
    _attr_icon = "mdi:thermometer"
    _attr_native_step = 0.5

    def __init__(self, coordinator, index: int, *, macrozone: bool = False) -> None:
        zone = coordinator.data.get("zones", {}).get(index, {})
        super().__init__(coordinator, zone_id=None if macrozone else index,
                         zone_name=None if macrozone else zone.get("name"))
        self.index = index
        self.macrozone = macrozone
        kind = "macrozone" if macrozone else "zone"
        self._attr_unique_id = f"messana_{kind}_{index}_default_temperature"
        name = coordinator.data.get("macrozones", {}).get(index, {}).get("name", f"Macrozone {index}")
        self._attr_name = ("All rooms default temperature" if index == 0 else f"{name} default temperature") if macrozone else "Default temperature"

    @property
    def _temperature_data(self) -> dict:
        key = "macrozones" if self.macrozone else "zones"
        return self.coordinator.data.get(key, {}).get(self.index, {})

    @property
    def available(self) -> bool:
        data = self._temperature_data
        low, high = data.get("min_temp"), data.get("max_temp")
        return (super().available and data.get("default_setpoint") is not None
                and low is not None and high is not None and low < high)

    @property
    def native_value(self) -> float | None:
        return self._temperature_data.get("default_setpoint")

    @property
    def native_min_value(self) -> float:
        return self._temperature_data.get("min_temp") or 0

    @property
    def native_max_value(self) -> float:
        return self._temperature_data.get("max_temp") or 100

    @property
    def native_unit_of_measurement(self) -> str:
        unit = self.coordinator.data.get("system", {}).get("temp_unit", "Celsius")
        return UnitOfTemperature.FAHRENHEIT if unit.lower().startswith("f") else UnitOfTemperature.CELSIUS

    @property
    def extra_state_attributes(self) -> dict:
        return {"scope": "all_rooms" if self.macrozone and self.index == 0 else "macrozone" if self.macrozone else "room",
                "preserves_schedules": True,
                "season": self.coordinator.data.get("macrozones", {}).get(
                    self.index if self.macrozone else self._temperature_data.get("macrozone_id"), {}).get("season")}

    async def async_set_native_value(self, value: float) -> None:
        if not self.available or not math.isfinite(value) or not self.native_min_value <= value <= self.native_max_value:
            raise HomeAssistantError("Default temperature is unavailable or outside the Messana limits")
        try:
            if self.macrozone:
                await self.coordinator.client.set_macrozone_setpoint(self.index, value)
            else:
                await self.coordinator.client.set_zone_setpoint(self.index, value)
        finally:
            await self.coordinator.async_request_refresh()
