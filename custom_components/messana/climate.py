from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.components.climate import ClimateEntity
from homeassistant.components.climate.const import HVACAction, HVACMode, ClimateEntityFeature
from homeassistant.components.persistent_notification import async_create as async_create_persistent_notification
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_DETACH_ON_SETPOINT, DOMAIN, DEFAULT_DETACH_ON_SETPOINT
from .coordinator import MessanaCoordinator
from .api import MessanaClient
from .entity import MessanaEntity


def _ha_temp_unit(messana_unit: str) -> UnitOfTemperature:
    if messana_unit.lower().startswith("f"):
        return UnitOfTemperature.FAHRENHEIT
    return UnitOfTemperature.CELSIUS


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
        zone_name = (coordinator.data.get("zones", {}).get(zid, {}) or {}).get("name")
        entities.append(MessanaZoneClimate(coordinator, client, entry.entry_id, ZoneRef(zone_id=zid), zone_name))

    async_add_entities(entities)


class MessanaZoneClimate(MessanaEntity, ClimateEntity):
    _attr_has_entity_name = True
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE
        | ClimateEntityFeature.TURN_ON
        | ClimateEntityFeature.TURN_OFF
    )

    def __init__(
        self,
        coordinator: MessanaCoordinator,
        client: MessanaClient,
        entry_id: str,
        zone: ZoneRef,
        zone_name: str | None,
    ) -> None:
        super().__init__(coordinator, zone_id=zone.zone_id, zone_name=zone_name)
        self.client = client
        self.entry_id = entry_id
        self.zone_id = zone.zone_id
        self._attr_unique_id = f"messana_zone_{self.zone_id}_climate"

    @property
    def name(self) -> str | None:
        return None

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
        zone = self.coordinator.data["zones"][self.zone_id]
        # Missing/sentinel scheduled targets must stay unknown, not become defaults.
        return zone.get("effective_setpoint", zone.get("setpoint"))

    @property
    def min_temp(self) -> float:
        value = self.coordinator.data.get("zones", {}).get(self.zone_id, {}).get("min_temp")
        return value if value is not None else super().min_temp

    @property
    def max_temp(self) -> float:
        value = self.coordinator.data.get("zones", {}).get(self.zone_id, {}).get("max_temp")
        return value if value is not None else super().max_temp

    @property
    def _system_hvac_mode(self) -> HVACMode | None:
        """Report the shared season without offering changeover on a room."""
        zone = self.coordinator.data.get("zones", {}).get(self.zone_id, {})
        hc0 = self.coordinator.data.get("hc_groups", {}).get(zone.get("hc_group_id", 0), {})
        mode = hc0.get("mode")
        if mode == 2:
            mode = hc0.get("executive_season")
        return {0: HVACMode.HEAT, 1: HVACMode.COOL}.get(mode)

    @property
    def hvac_mode(self) -> HVACMode | None:
        system_on = bool(self.coordinator.data.get("system", {}).get("status", 0))
        zone_on = bool(self.coordinator.data.get("zones", {}).get(self.zone_id, {}).get("status", 0))
        if not system_on or not zone_on:
            return HVACMode.OFF
        return self._system_hvac_mode

    @property
    def hvac_modes(self) -> list[HVACMode]:
        mode = self._system_hvac_mode
        return [HVACMode.OFF, mode] if mode is not None else [HVACMode.OFF]

    @property
    def hvac_action(self) -> HVACAction | None:
        if self.hvac_mode == HVACMode.OFF:
            return HVACAction.OFF
        status = self.coordinator.data.get("zones", {}).get(self.zone_id, {}).get("thermal_status")
        if status == 3:
            # The radiant loop can only execute one season at a time.
            return {HVACMode.HEAT: HVACAction.HEATING, HVACMode.COOL: HVACAction.COOLING}.get(self._system_hvac_mode)
        return {0: HVACAction.IDLE, 1: HVACAction.HEATING, 2: HVACAction.COOLING}.get(status)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose coordinator zone fields as climate entity attributes for UI/templates."""
        zones = (self.coordinator.data or {}).get("zones", {})
        z = zones.get(self.zone_id, {})

        schedule_on = int(z.get("schedule_on") or 0)
        schedule_status = int(z.get("schedule_status") or 0)

        if schedule_on and schedule_status:
            control_source = "program"
        elif schedule_on:
            control_source = "program_enabled"
        else:
            control_source = "manual"

        return {
            "zone_id": self.zone_id,
            "default_temperature": z.get("default_setpoint", z.get("setpoint")),
            "default_temperature_unit": self.temperature_unit,
            "macrozone_id": z.get("macrozone_id"),
            "macrozone_default_temperature": z.get("macrozone_default"),
            "matches_macrozone_default": z.get("matches_macrozone_default"),
            "target_source": z.get("target_source", "default_only"),
            "schedule_name": z.get("schedule_name"),
            # Master on/off for the zone
            "zone_status": z.get("status"),
            # 0 none, 1 heat, 2 cool, 3 heat+cool
            "thermal_status": z.get("thermal_status"),

            # Schedule / program control
            "schedule_on": schedule_on,           # 0/1: schedule assigned/enabled
            "schedule_status": schedule_status,   # 0/1: schedule currently applied
            "control_source": control_source,     # program | program_enabled | manual

            # Convenience (so you don't *have* to reference separate sensors in templates)
            "humidity": z.get("humidity"),
            "dewpoint": z.get("dewpoint"),
        }

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set new target temperature.

        If zone is schedule-controlled and option enabled, detach schedule first.
        """
        temperature = kwargs.get("temperature")
        if temperature is None:
            return

        z = (self.coordinator.data or {}).get("zones", {}).get(self.zone_id, {})
        schedule_on = int(z.get("schedule_on") or 0)

        detach_on_setpoint = bool(
            self.coordinator.hass.data[DOMAIN][self.entry_id].get(
                CONF_DETACH_ON_SETPOINT,
                DEFAULT_DETACH_ON_SETPOINT,
            )
        )

        if detach_on_setpoint and schedule_on:
            # Detach (disable schedule control) before setting manual setpoint
            await self.coordinator.client.set_zone_schedule_on(self.zone_id, False)
            zone_name = z.get("name", f"Zone {self.zone_id + 1}")

            async_create_persistent_notification(
                self.coordinator.hass,
                title="Messana: Schedule detached",
                message=f"Detached '{zone_name}' from its schedule to set a manual temperature.",
            )

        await self.coordinator.client.set_zone_setpoint(self.zone_id, float(temperature))
        await self.coordinator.async_request_refresh()

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        if hvac_mode == HVACMode.OFF:
            await self.async_turn_off()
            return
        if hvac_mode != self._system_hvac_mode:
            raise HomeAssistantError(
                "Rooms follow the shared system season. Change Heating/Cooling/Auto "
                "using the Messana H/C group mode control."
            )
        await self.async_turn_on()

    async def async_turn_on(self) -> None:
        """Enable only this room, leaving system power and changeover alone."""
        await self.client.set_zone_status(self.zone_id, True)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self) -> None:
        """Disable only this room."""
        await self.client.set_zone_status(self.zone_id, False)
        await self.coordinator.async_request_refresh()
