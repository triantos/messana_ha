from types import SimpleNamespace
from unittest.mock import AsyncMock, create_autospec

import pytest
from homeassistant.exceptions import HomeAssistantError

from custom_components.messana.api import MessanaClient, MessanaApiError
from custom_components.messana.button import MessanaUseMacrozoneDefaultButton
from custom_components.messana.number import MessanaDefaultTemperature


@pytest.fixture
def coordinator():
    return SimpleNamespace(client=create_autospec(MessanaClient, instance=True),
        last_update_success=True, async_request_refresh=AsyncMock(),
        data={"system": {"temp_unit": "Celsius"}, "zones": {7: {
            "name": "Master Bedroom", "macrozone_id": 0, "macrozone_default": 23,
            "default_setpoint": 25, "effective_setpoint": 23,
            "min_temp": 15, "max_temp": 30, "schedule_on": 1}},
            "macrozones": {0: {"name": "All", "default_setpoint": 23,
                "min_temp": 15, "max_temp": 30, "season": 0}}})


@pytest.mark.asyncio
async def test_room_default_write_keeps_schedule_and_power(coordinator):
    number = MessanaDefaultTemperature(coordinator, 7)
    await number.async_set_native_value(25.5)
    coordinator.client.set_zone_setpoint.assert_awaited_once_with(7, 25.5)
    assert len(coordinator.client.mock_calls) == 1
    coordinator.async_request_refresh.assert_awaited_once()


@pytest.mark.asyncio
async def test_global_default_has_explicit_bulk_scope(coordinator):
    number = MessanaDefaultTemperature(coordinator, 0, macrozone=True)
    assert number.extra_state_attributes["scope"] == "all_rooms"
    assert number.name == "All rooms default temperature"
    await number.async_set_native_value(24)
    coordinator.client.set_macrozone_setpoint.assert_awaited_once_with(0, 24)
    assert len(coordinator.client.mock_calls) == 1


@pytest.mark.asyncio
async def test_copy_macrozone_default_only_writes_this_room(coordinator):
    button = MessanaUseMacrozoneDefaultButton(coordinator, 7, "Master Bedroom")
    await button.async_press()
    coordinator.client.set_zone_setpoint.assert_awaited_once_with(7, 23)
    assert len(coordinator.client.mock_calls) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("value", [14.5, 30.5, float("nan"), float("inf")])
async def test_write_respects_actual_controller_limits(coordinator, value):
    with pytest.raises(HomeAssistantError):
        await MessanaDefaultTemperature(coordinator, 7).async_set_native_value(value)
    assert not coordinator.client.mock_calls


@pytest.mark.asyncio
async def test_missing_metadata_disables_writes(coordinator):
    coordinator.data["zones"][7].pop("min_temp")
    number = MessanaDefaultTemperature(coordinator, 7)
    assert not number.available
    with pytest.raises(HomeAssistantError):
        await number.async_set_native_value(23)
    assert not coordinator.client.mock_calls


@pytest.mark.asyncio
async def test_write_failure_refreshes_without_detaching(coordinator):
    coordinator.client.set_zone_setpoint.side_effect = MessanaApiError("failure")
    with pytest.raises(MessanaApiError):
        await MessanaDefaultTemperature(coordinator, 7).async_set_native_value(24)
    coordinator.async_request_refresh.assert_awaited_once()
    coordinator.client.set_zone_schedule_on.assert_not_called()


def test_ha_fahrenheit_display_and_input_convert_to_controller_celsius(coordinator):
    from homeassistant.util.unit_system import US_CUSTOMARY_SYSTEM
    number = MessanaDefaultTemperature(coordinator, 7)
    number.hass = SimpleNamespace(config=SimpleNamespace(units=US_CUSTOMARY_SYSTEM))
    assert number.state == 77.0
    assert number.unit_of_measurement == "°F"
    assert number.convert_to_native_value(77.9) == pytest.approx(25.5)
    assert number.capability_attributes["min"] == 59
    assert number.capability_attributes["max"] == 86
