from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from aiohttp import ClientResponseError

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

_LOGGER = logging.getLogger(__name__)


class MessanaApiError(Exception):
    """Base exception for Messana API errors."""


class MessanaAuthError(MessanaApiError):
    """Auth/permission error."""


@dataclass(frozen=True)
class MessanaClient:
    hass: HomeAssistant
    base_url: str
    api_key: str
    timeout: float = 10.0

    def _url(self, path: str) -> str:
        return f"{self.base_url.rstrip('/')}{path}"

    async def _request(self, method: str, path: str, *, json: dict | None = None) -> dict[str, Any]:
        session = async_get_clientsession(self.hass)
        # Per swagger security scheme: api key is a query parameter named "apikey"
        params = {"apikey": self.api_key}

        # NOTE: This logs the URL but not the key value itself (it is in params)
        _LOGGER.debug("Messana request: %s %s", method, self._url(path))

        try:
            async with session.request(
                method,
                self._url(path),
                params=params,
                json=json,
                timeout=self.timeout,
            ) as resp:
                if resp.status == 401:
                    raise MessanaAuthError("Unauthorized (check API key)")
                resp.raise_for_status()
                data = await resp.json(content_type=None)
                if not isinstance(data, dict):
                    # Some endpoints might return raw numbers/strings; normalize.
                    return {"value": data}
                return data

        except ClientResponseError as e:
            raise MessanaApiError(f"HTTP error {e.status}: {e.message}") from e
        except MessanaApiError:
            raise
        except Exception as e:
            raise MessanaApiError(str(e)) from e

    @staticmethod
    def _float_or_none(val: Any, *, sentinel: float | None = None) -> float | None:
        """Parse float; return None for missing / unparseable / sentinel."""
        if val is None:
            return None
        try:
            f = float(val)
        except Exception:
            return None
        if sentinel is not None and f <= sentinel:
            return None
        return f

    @staticmethod
    def _int_or_default(val: Any, default: int = 0) -> int:
        try:
            return int(val)
        except Exception:
            return default

    # -------- System ----------
    async def get_system_status(self) -> int:
        # GetStatusResponse -> {"status": <int>}
        data = await self._request("GET", "/api/system/status")
        return self._int_or_default(data.get("status"), 0)

    async def set_system_status(self, on: bool) -> None:
        # PUT /api/system/status uses SetOnMcuResponse -> {"value": 0|1}
        await self._request("PUT", "/api/system/status", json={"value": 1 if on else 0})

    async def get_temp_unit(self) -> str:
        # GetUnitResponse -> {"value": "Celsius"|"Fahrenheit"}
        data = await self._request("GET", "/api/system/tempUnit")
        return str(data.get("value", "Celsius"))

    async def get_zone_count(self) -> int:
        # GetNumberResponse -> {"count": <int>}
        data = await self._request("GET", "/api/system/zoneCount")
        try:
            return int(data["count"])
        except (KeyError, TypeError, ValueError) as err:
            raise MessanaApiError(f"Unexpected response for zoneCount: {data}") from err

    async def get_hc_group_count(self) -> int:
        # GetNumberResponse -> {"count": <int>}
        data = await self._request("GET", "/api/system/HCgroupCount")
        try:
            return int(data["count"])
        except (KeyError, TypeError, ValueError) as err:
            raise MessanaApiError(f"Unexpected response for HCgroupCount: {data}") from err

    # -------- H/C group ----------
    async def get_hc_mode(self, group_id: int) -> int:
        # GetModeResponse -> {"value": <int>} (0 heat, 1 cool, 2 auto)
        data = await self._request("GET", f"/api/hc/mode/{group_id}")
        return self._int_or_default(data.get("value"), 2)

    async def set_hc_mode(self, group_id: int, mode: int) -> None:
        # PUT /api/hc/mode uses ChangeMode -> {"id": <int>, "value": <int>}
        await self._request("PUT", "/api/hc/mode", json={"id": group_id, "value": int(mode)})

    async def get_hc_executive_season(self, group_id: int) -> int:
        # GetExecutiveSeasonResponse -> {"value": 0|1}
        data = await self._request("GET", f"/api/hc/executiveSeason/{group_id}")
        return self._int_or_default(data.get("value"), 0)

    # -------- Zone ----------
    async def get_zone_name(self, zone_id: int) -> str:
        # Returns {"name": "..."}
        data = await self._request("GET", f"/api/zone/name/{zone_id}")
        return str(data.get("name", f"Zone {zone_id}"))

    async def get_zone_temperature(self, zone_id: int) -> float | None:
        # GetTemperatureResponse -> {"value": <float>} ; -3276.8 indicates no-value
        data = await self._request("GET", f"/api/zone/temperature/{zone_id}")
        return self._float_or_none(data.get("value"), sentinel=-3000.0)

    async def get_zone_humidity(self, zone_id: int) -> float | None:
        # Spec has an inconsistency: schema says "values", example shows "value".
        # Real devices commonly return "value", so prefer it but fall back to "values".
        data = await self._request("GET", f"/api/zone/humidity/{zone_id}")
        val = data.get("value", data.get("values"))
        return self._float_or_none(val)

    async def get_zone_dewpoint(self, zone_id: int) -> float | None:
        # GetDewpointResponse -> {"value": <float>} ; may use -3276.8 sentinel as well
        data = await self._request("GET", f"/api/zone/dewpoint/{zone_id}")
        return self._float_or_none(data.get("value"), sentinel=-3000.0)

    async def get_zone_setpoint(self, zone_id: int) -> float | None:
        # GetSetpointResponse -> {"value": <float>}
        data = await self._request("GET", f"/api/zone/setpoint/{zone_id}")
        return self._float_or_none(data.get("value"), sentinel=-3000.0)

    async def set_zone_setpoint(self, zone_id: int, temperature: float) -> None:
        # PUT /api/zone/setpoint uses ChangeSetpoint -> {"id": <int>, "value": <float>}
        await self._request("PUT", "/api/zone/setpoint", json={"id": zone_id, "value": float(temperature)})

    async def get_zone_status(self, zone_id: int) -> int:
        # GetStatusResponse -> {"status": <int>}
        data = await self._request("GET", f"/api/zone/status/{zone_id}")
        return self._int_or_default(data.get("status"), 0)

    async def set_zone_status(self, zone_id: int, on: bool) -> None:
        # PUT /api/zone/status uses SetStatus -> {"id": <int>, "value": 0|1}
        await self._request("PUT", "/api/zone/status", json={"id": zone_id, "value": 1 if on else 0})

    async def get_zone_thermal_status(self, zone_id: int) -> int:
        data = await self._request("GET", f"/api/zone/thermalStatus/{zone_id}")
        return self._int_or_default(data.get("status"), 0)
