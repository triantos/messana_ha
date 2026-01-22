from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.components.climate import ClimateEntity
from homeassistant.components.climate.const import HVACMode, ClimateEntityFeature
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import MessanaCoordinator
from .api import MessanaClient
from .entity import MessanaEntity


def _ha_temp_unit(messana_unit: str) -> UnitOfTemperature:
    # /api/system/tempUnit returns "Celsius" or "Fahrenheit" :contentReference[oaicite:33]{index=33}
    if messana_unit.lower().startswith("f"):
        return UnitOfTemperature.FAHRENHEIT
    return UnitOfTemperature.CELSIUS


def _hvac_mode_from_hc(mode: int, system_on: bool) -> HVACMode:
    if not system_on:
        return HVACMode.OFF
    # /api/hc/mode: 0 heat, 1 cool, 2 auto :contentReference[oaicite:34]{index=34}
    if mode == 0:
        return HVACMode.HEAT
    if mode == 1:
        return HVACMode.COOL
    return HVACMode.HEAT_COOL


@dataclass(frozen=True)
class ZoneRef:
    zone_id: int


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator: MessanaCoordinator = data["coordinator"]
    client: MessanaClient = data["client"]

    # IMPORTANT: Create entities based on effective zone count (not current coordinator zones dict),
    # because coordinator.data["zones"] can be empty during initial platform setup and HA won't
    # auto-create entities later.
    zone_count = int(coordinator.data.get("system", {}).get("effective_zone_count", 0))

    entities: list[MessanaZoneClimate] = []
    for zid in range(zone_count):
        entities.append(MessanaZoneClimate(coordinator, client, ZoneRef(zone_id=zid)))

    async_add_entities(entities)


class MessanaZoneClimate(MessanaEntity, ClimateEntity):
    _attr_has_entity_name = True
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_supported_features = ClimateEntityFeature.TARGET_TEMPERATURE

    def __init__(self, coordinator: MessanaCoordinator, client: MessanaClient, zone: ZoneRef) -> None:
        super().__init__(coordinator)
        self.client = client
        self.zone_id = zone.zone_id
        self._attr_unique_id = f"messana_zone_{self.zone_id}_climate"

    @property
    def name(self) -> str:
        zones = (self.coordinator.data or {}).get("zones", {})
        z = zones.get(self.zone_id, {})
        return z.get("name", f"Zone {self.zone_id}")

    @property
    def available(self) -> bool:
        return super().available and self.zone_id in self.coordinator.data.get("zones", {})

    @property
    def temperature_unit(self) -> UnitOfTemperature:
        unit = self.coordinator.data.get("system", {}).get("temp_unit", "Celsius")
        return _ha_temp_unit(unit)

    @property
    def current_temperature(self) -> float | None:
        return self.coordinator.data["zones"][self.zone_id].get("temperature")

    @property
    def target_temperature(self) -> float | None:
        return self.coordinator.data["zones"][self.zone_id].get("setpoint")

    @property
    def hvac_mode(self) -> HVACMode:
        system_on = bool(self.coordinator.data.get("system", {}).get("status", 0))
        # Use HC group 0 as default “global mode” if present
        hc0 = self.coordinator.data.get("hc_groups", {}).get(0, {})
        mode = int(hc0.get("mode", 2))
        return _hvac_mode_from_hc(mode, system_on)

    @property
    def hvac_modes(self) -> list[HVACMode]:
        return [HVACMode.OFF, HVACMode.HEAT, HVACMode.COOL, HVACMode.HEAT_COOL]

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose coordinator zone fields as climate entity attributes for UI/templates."""
        zones = (self.coordinator.data or {}).get("zones", {})
        z = zones.get(self.zone_id, {})

        return {
            "zone_id": self.zone_id,
            # Master on/off for the zone
            "zone_status": z.get("status"),
            # 0 none, 1 heat, 2 cool, 3 heat+cool
            "thermal_status": z.get("thermal_status"),
            # Convenience (so you don't *have* to reference separate sensors in templates)
            "humidity": z.get("humidity"),
            "dewpoint": z.get("dewpoint"),
        }

    async def async_set_temperature(self, **kwargs: Any) -> None:
        temp = kwargs.get("temperature")
        if temp is None:
            return
        await self.client.set_zone_setpoint(self.zone_id, float(temp))  # :contentReference[oaicite:35]{index=35}
        await self.coordinator.async_request_refresh()

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        # Map HA hvac_mode to:
        # - system power /api/system/status :contentReference[oaicite:36]{index=36}
        # - hc group 0 mode /api/hc/mode :contentReference[oaicite:37]{index=37}
        if hvac_mode == HVACMode.OFF:
            await self.client.set_system_status(False)
            await self.coordinator.async_request_refresh()
            return

        await self.client.set_system_status(True)
        if hvac_mode == HVACMode.HEAT:
            await self.client.set_hc_mode(0, 0)
        elif hvac_mode == HVACMode.COOL:
            await self.client.set_hc_mode(0, 1)
        elif hvac_mode == HVACMode.HEAT_COOL:
            await self.client.set_hc_mode(0, 2)

        await self.coordinator.async_request_refresh()
