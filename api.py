from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from aiohttp import ClientResponseError

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

import logging
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
        params = {"apikey": self.api_key}  # per swagger securityDefinitions in query :contentReference[oaicite:5]{index=5}

        _LOGGER.debug("Messana request: %s %s params=%s", method, self._url(path), params)
        try:
            async with session.request(
                method,
                self._url(path),
                params=params,
                json=json,
                timeout=self.timeout,
            ) as resp:
                # Messana docs mention 200 success, 400 error; swagger also lists 401/404/500 :contentReference[oaicite:6]{index=6}
                if resp.status == 401:
                    raise MessanaAuthError("Unauthorized (check API key)")
                resp.raise_for_status()
                data = await resp.json(content_type=None)
                if not isinstance(data, dict):
                    return {"value": data}
                return data
        except ClientResponseError as e:
            raise MessanaApiError(f"HTTP error {e.status}: {e.message}") from e
        except Exception as e:
            raise MessanaApiError(str(e)) from e

    # -------- System ----------
    async def get_system_status(self) -> int:
        data = await self._request("GET", "/api/system/status")
        return int(data.get("value", 0))

    async def set_system_status(self, on: bool) -> None:
        # PUT /api/system/status body schema is SetOnMcuResponse :contentReference[oaicite:7]{index=7}
        await self._request("PUT", "/api/system/status", json={"value": 1 if on else 0})

    async def get_temp_unit(self) -> str:
        data = await self._request("GET", "/api/system/tempUnit")
        return str(data.get("value", "Celsius"))

    async def get_zone_count(self) -> int:
        data = await self._request("GET", "/api/system/zoneCount")
        try:
            return int(data["count"])
        except (KeyError, TypeError, ValueError) as err:
            raise ValueError(f"Unexpected response for zoneCount: {data}") from err

    async def get_hc_group_count(self) -> int:
        data = await self._request("GET", "/api/system/HCgroupCount")
        return int(data.get("value", 0))

    # -------- H/C group ----------
    async def get_hc_mode(self, group_id: int) -> int:
        # GET /api/hc/mode/{id} returns GetModeResponse :contentReference[oaicite:8]{index=8}
        data = await self._request("GET", f"/api/hc/mode/{group_id}")
        return int(data.get("value", 2))  # 0 heat, 1 cool, 2 auto :contentReference[oaicite:9]{index=9}

    async def set_hc_mode(self, group_id: int, mode: int) -> None:
        await self._request("PUT", "/api/hc/mode", json={"id": group_id, "value": int(mode)})

    async def get_hc_executive_season(self, group_id: int) -> int:
        # 0 heating, 1 cooling :contentReference[oaicite:10]{index=10}
        data = await self._request("GET", f"/api/hc/executiveSeason/{group_id}")
        return int(data.get("value", 0))

    # -------- Zone ----------
    async def get_zone_name(self, zone_id: int) -> str:
        data = await self._request("GET", f"/api/zone/name/{zone_id}")  # :contentReference[oaicite:11]{index=11}
        return str(data.get("name", f"Zone {zone_id}"))

    async def get_zone_temperature(self, zone_id: int) -> float | None:
        data = await self._request("GET", f"/api/zone/temperature/{zone_id}")  # :contentReference[oaicite:12]{index=12}
        val = data.get("value")
        if val is None:
            return None
        # swagger notes -3276.8 placeholder for no-value :contentReference[oaicite:13]{index=13}
        try:
            f = float(val)
            return None if f <= -3000 else f
        except Exception:
            return None

    async def get_zone_humidity(self, zone_id: int) -> float | None:
        data = await self._request("GET", f"/api/zone/humidity/{zone_id}")  # :contentReference[oaicite:14]{index=14}
        val = data.get("value")
        try:
            return None if val is None else float(val)
        except Exception:
            return None

    async def get_zone_dewpoint(self, zone_id: int) -> float | None:
        data = await self._request("GET", f"/api/zone/dewpoint/{zone_id}")  # :contentReference[oaicite:15]{index=15}
        val = data.get("value")
        try:
            return None if val is None else float(val)
        except Exception:
            return None

    async def get_zone_setpoint(self, zone_id: int) -> float | None:
        data = await self._request("GET", f"/api/zone/setpoint/{zone_id}")  # :contentReference[oaicite:16]{index=16}
        val = data.get("value")
        try:
            return None if val is None else float(val)
        except Exception:
            return None

    async def set_zone_setpoint(self, zone_id: int, temperature: float) -> None:
        # PUT /api/zone/setpoint uses ChangeSetpoint {id,value} :contentReference[oaicite:17]{index=17}
        await self._request("PUT", "/api/zone/setpoint", json={"id": zone_id, "value": float(temperature)})

    async def get_zone_status(self, zone_id: int) -> int:
        data = await self._request("GET", f"/api/zone/status/{zone_id}")  # :contentReference[oaicite:18]{index=18}
        return int(data.get("value", 0))

    async def set_zone_status(self, zone_id: int, on: bool) -> None:
        # PUT /api/zone/status uses SetStatus {id,value} :contentReference[oaicite:19]{index=19}
        await self._request("PUT", "/api/zone/status", json={"id": zone_id, "value": 1 if on else 0})
