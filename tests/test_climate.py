"""Regression tests for room controls on a shared-season radiant system."""
from types import SimpleNamespace
from unittest.mock import AsyncMock, create_autospec

import pytest
from homeassistant.components.climate.const import ClimateEntityFeature, HVACAction, HVACMode
from homeassistant.exceptions import HomeAssistantError
from homeassistant.util.unit_system import METRIC_SYSTEM

from custom_components.messana.api import MessanaClient
from custom_components.messana.climate import MessanaZoneClimate, ZoneRef


@pytest.fixture
def room():
    client = create_autospec(MessanaClient, instance=True)
    coordinator = SimpleNamespace(
        data={
            "system": {"status": 1, "temp_unit": "Celsius"},
            "hc_groups": {0: {"mode": 0, "executive_season": 0}},
            "zones": {7: {"status": 1, "thermal_status": 0, "schedule_on": 1, "schedule_status": 1}},
        },
        last_update_success=True,
        async_request_refresh=AsyncMock(),
        client=client,
    )
    entity = MessanaZoneClimate(coordinator, client, "entry", ZoneRef(7), "Master Bedroom")
    entity.hass = SimpleNamespace(config=SimpleNamespace(units=METRIC_SYSTEM))
    return entity


@pytest.mark.asyncio
@pytest.mark.parametrize("operation,expected", [("async_turn_off", False), ("async_turn_on", True)])
async def test_room_power_never_changes_house(room, operation, expected):
    await getattr(room, operation)()
    room.client.set_zone_status.assert_awaited_once_with(7, expected)
    room.client.set_system_status.assert_not_called()
    room.client.set_hc_mode.assert_not_called()
    room.coordinator.async_request_refresh.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("mode,on", [(HVACMode.OFF, False), (HVACMode.HEAT, True)])
async def test_hvac_service_operates_only_room(room, mode, on):
    await room.async_set_hvac_mode(mode)
    room.client.set_zone_status.assert_awaited_once_with(7, on)
    room.client.set_system_status.assert_not_called()
    room.client.set_hc_mode.assert_not_called()
    assert room.coordinator.data["zones"][7]["schedule_on"] == 1
    room.client.set_zone_schedule_on.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", [HVACMode.COOL, HVACMode.HEAT_COOL, HVACMode.AUTO])
async def test_room_rejects_season_change(room, mode):
    with pytest.raises(HomeAssistantError, match="shared system season"):
        await room.async_set_hvac_mode(mode)
    assert not room.client.mock_calls


@pytest.mark.parametrize("system_on,zone_on", [(0, 1), (1, 0), (0, 0)])
def test_disabled_room_or_system_reports_off(room, system_on, zone_on):
    room.coordinator.data["system"]["status"] = system_on
    room.coordinator.data["zones"][7]["status"] = zone_on
    room.coordinator.data["zones"][7]["thermal_status"] = 1
    assert room.hvac_mode == HVACMode.OFF
    assert room.hvac_action == HVACAction.OFF


@pytest.mark.parametrize("mode,season,expected", [(0, 1, HVACMode.HEAT), (1, 0, HVACMode.COOL), (2, 0, HVACMode.HEAT), (2, 1, HVACMode.COOL)])
def test_system_changeover_updates_room_capabilities(room, mode, season, expected):
    room.coordinator.data["hc_groups"][0] = {"mode": mode, "executive_season": season}
    assert room.hvac_mode == expected
    assert room.hvac_modes == [HVACMode.OFF, expected]
    assert room.capability_attributes["hvac_modes"] == [HVACMode.OFF, expected]


@pytest.mark.parametrize("status,action", [(0, HVACAction.IDLE), (1, HVACAction.HEATING), (2, HVACAction.COOLING), (3, HVACAction.HEATING), (None, None)])
def test_thermal_request_is_reported_separately(room, status, action):
    room.coordinator.data["zones"][7]["thermal_status"] = status
    assert room.hvac_action == action


def test_both_requests_follow_executive_cooling_season(room):
    room.coordinator.data["hc_groups"][0] = {"mode": 2, "executive_season": 1}
    room.coordinator.data["zones"][7]["thermal_status"] = 3
    assert room.hvac_action == HVACAction.COOLING


def test_unknown_season_is_not_invented(room):
    room.coordinator.data["hc_groups"][0] = {"mode": 2}
    assert room.hvac_mode is None
    assert room.hvac_modes == [HVACMode.OFF]


def test_schedule_attributes_and_identity_are_preserved(room):
    assert room.unique_id == "messana_zone_7_climate"
    assert room.extra_state_attributes["control_source"] == "program"
    assert room.supported_features & ClimateEntityFeature.TURN_ON
    assert room.supported_features & ClimateEntityFeature.TURN_OFF
    assert not room.supported_features & ClimateEntityFeature.TARGET_TEMPERATURE_RANGE


@pytest.mark.asyncio
async def test_turning_on_room_does_not_power_on_disabled_house(room):
    room.coordinator.data["system"]["status"] = 0
    await room.async_turn_on()
    room.client.set_zone_status.assert_awaited_once_with(7, True)
    room.client.set_system_status.assert_not_called()
    assert room.hvac_mode == HVACMode.OFF


def test_schedule_target_and_default_are_distinct(room):
    room.coordinator.data["zones"][7].update(
        setpoint=25, default_setpoint=25, effective_setpoint=23,
        target_source="schedule", schedule_name="Day Time 23°", min_temp=15, max_temp=30)
    assert room.target_temperature == 23
    assert room.extra_state_attributes["default_temperature"] == 25
    assert room.extra_state_attributes["default_temperature_unit"] == "°C"
    assert room.extra_state_attributes["schedule_name"] == "Day Time 23°"
    assert (room.min_temp, room.max_temp) == (15, 30)


def test_missing_schedule_target_is_not_replaced_by_default(room):
    room.coordinator.data["zones"][7].update(setpoint=25, effective_setpoint=None)
    assert room.target_temperature is None
