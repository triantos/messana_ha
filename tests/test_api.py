"""Response fixtures from API 0.10.0 and older controllers."""
from unittest.mock import AsyncMock

import pytest

from custom_components.messana.api import MessanaClient


@pytest.mark.asyncio
@pytest.mark.parametrize("response,expected", [({"value": 1}, 1), ({"value": 0}, 0), ({"status": 1}, 1), ({"status": 0}, 0), ({"value": 0, "status": 1}, 0)])
async def test_schedule_applied_status_uses_value(monkeypatch, response, expected):
    request = AsyncMock(return_value=response)
    monkeypatch.setattr(MessanaClient, "_request", request)
    client = MessanaClient(hass=None, base_url="http://example.invalid", api_key="test")
    assert await client.get_zone_schedule_status(7) == expected
    request.assert_awaited_once_with("GET", "/api/zone/scheduleStatus/7")


@pytest.mark.asyncio
async def test_global_default_public_api_payload(monkeypatch):
    request = AsyncMock(return_value={"status": "success"})
    monkeypatch.setattr(MessanaClient, "_request", request)
    client = MessanaClient(hass=None, base_url="http://example.invalid", api_key="test")
    await client.set_macrozone_setpoint(0, 24.5)
    request.assert_awaited_once_with("PUT", "/api/macrozone/setpoint", json={"id": 0, "value": 24.5})


@pytest.mark.asyncio
async def test_tables_are_read_only_and_strip_unneeded_fields(monkeypatch):
    request = AsyncMock(side_effect=[{"content": {"0": {"PAR_AutoModeStyle": 2}}},
        {"content": {"0": {"PAR_SetTempH": 27, "CFG_Address": "unused"}, "GLB": {}}},
        {"content": {"0": {"PAR_SetTempH": 23}}},
        {"content": {"1": {"CFG_Type": 2, "RTU_SetPoint": 23}}}])
    monkeypatch.setattr(MessanaClient, "_request", request)
    tables = await MessanaClient(hass=None, base_url="http://example.invalid", api_key="test").get_temperature_tables()
    assert tables["RMS"] == {0: {"PAR_SetTempH": 27}}
    assert all(call.args[0] == "GET" for call in request.await_args_list)
