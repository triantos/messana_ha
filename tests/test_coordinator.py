from types import SimpleNamespace
from unittest.mock import AsyncMock, create_autospec

import pytest
from homeassistant.core import HomeAssistant

from custom_components.messana.api import MessanaClient, MessanaApiError
from custom_components.messana.coordinator import MessanaCoordinator


@pytest.mark.asyncio
@pytest.mark.parametrize("tables_available", [True, False])
async def test_coordinator_preserves_rest_when_web_tables_unavailable(tables_available):
    hass = HomeAssistant("/private/tmp/messana-coordinator-test")
    client = create_autospec(MessanaClient, instance=True)
    returns = {"get_system_status": 1, "get_temp_unit": "Celsius", "get_zone_count": 1,
        "get_hc_group_count": 1, "get_hc_mode": 0, "get_hc_executive_season": 0,
        "get_zone_name": "Foyer", "get_zone_temperature": 31.3, "get_zone_humidity": 42,
        "get_zone_dewpoint": 16.6, "get_zone_setpoint": 27, "get_zone_status": 1,
        "get_zone_thermal_status": 0, "get_zone_schedule_on": 0, "get_zone_schedule_status": 0}
    for name, value in returns.items():
        getattr(client, name).return_value = value
    client.get_temperature_tables.return_value = {
        "GRP": {0: {"PAR_AutoModeStyle": 0}}, "SCH": {},
        "RMS": {0: {"CFG_IdxGRP": 0, "CFG_IdxMCZ": 0, "PAR_SetTempH": 27, "PAR_SchedOnH": False}},
        "MCZ": {0: {"CFG_IdxGRP": 0, "CFG_Name": "All", "PAR_SetTempH": 23,
            "TEC_SetTempMinH": 15, "TEC_SetTempMaxH": 30}}}
    if not tables_available:
        client.get_temperature_tables.side_effect = MessanaApiError("unsupported")
    coordinator = MessanaCoordinator(hass, client, 30)
    result = await coordinator._async_update_data()
    assert result["zones"][0]["default_setpoint"] == 27
    assert result["system"]["status"] == 1
    if tables_available:
        assert result["zones"][0]["effective_setpoint"] == 27
        assert result["zones"][0]["macrozone_default"] == 23
    else:
        assert "effective_setpoint" not in result["zones"][0]
        assert result["macrozones"] == {}
    assert not client.set_zone_setpoint.called
    await hass.async_stop()
