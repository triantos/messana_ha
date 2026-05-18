from __future__ import annotations

import asyncio
from datetime import timedelta
from typing import Any, Awaitable, Callable
import logging

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import MessanaClient, MessanaApiError

_LOGGER = logging.getLogger(__name__)

MAX_CONCURRENT_REQUESTS = 8


class MessanaCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    def __init__(
        self,
        hass: HomeAssistant,
        client: MessanaClient,
        scan_interval_seconds: int,
        zone_count_override: int = 0,
    ) -> None:
        super().__init__(
            hass,
            logger=_LOGGER,
            name="Messana Coordinator",
            update_interval=timedelta(seconds=scan_interval_seconds),
        )
        self.client = client
        self.zone_count_override = max(int(zone_count_override or 0), 0)

    async def _async_fetch_hc_group(
        self,
        group_id: int,
        semaphore: asyncio.Semaphore,
    ) -> tuple[int, dict[str, Any]]:
        mode, executive_season = await asyncio.gather(
            self._async_limited_call(semaphore, self.client.get_hc_mode, group_id),
            self._async_limited_call(semaphore, self.client.get_hc_executive_season, group_id),
        )
        return group_id, {"mode": mode, "executive_season": executive_season}

    async def _async_fetch_zone(
        self,
        zone_id: int,
        semaphore: asyncio.Semaphore,
    ) -> tuple[int, dict[str, Any]]:
        name, temp, rh, dp, sp, on, thermal_status, schedule_on, schedule_status = await asyncio.gather(
            self._async_limited_call(semaphore, self.client.get_zone_name, zone_id),
            self._async_limited_call(semaphore, self.client.get_zone_temperature, zone_id),
            self._async_limited_call(semaphore, self.client.get_zone_humidity, zone_id),
            self._async_limited_call(semaphore, self.client.get_zone_dewpoint, zone_id),
            self._async_limited_call(semaphore, self.client.get_zone_setpoint, zone_id),
            self._async_limited_call(semaphore, self.client.get_zone_status, zone_id),
            self._async_limited_call(semaphore, self.client.get_zone_thermal_status, zone_id),
            self._async_limited_call(semaphore, self.client.get_zone_schedule_on, zone_id),
            self._async_limited_call(semaphore, self.client.get_zone_schedule_status, zone_id),
        )

        return zone_id, {
            "id": zone_id,
            "name": name,
            "temperature": temp,
            "humidity": rh,
            "dewpoint": dp,
            "setpoint": sp,
            "status": on,
            "thermal_status": thermal_status,
            "schedule_on": schedule_on,
            "schedule_status": schedule_status,
        }

    @staticmethod
    async def _async_limited_call(
        semaphore: asyncio.Semaphore,
        func: Callable[..., Awaitable[Any]],
        *args: Any,
    ) -> Any:
        async with semaphore:
            return await func(*args)

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)
            system_on, temp_unit, api_zone_count, hc_count = await asyncio.gather(
                self._async_limited_call(semaphore, self.client.get_system_status),
                self._async_limited_call(semaphore, self.client.get_temp_unit),
                self._async_limited_call(semaphore, self.client.get_zone_count),
                self._async_limited_call(semaphore, self.client.get_hc_group_count),
            )

            zone_count = self.zone_count_override or api_zone_count

            hc_group_items = await asyncio.gather(
                *[
                    self._async_fetch_hc_group(gid, semaphore)
                    for gid in range(max(hc_count, 0))
                ]
            )
            hc_groups = dict(hc_group_items)

            zone_items = await asyncio.gather(
                *[
                    self._async_fetch_zone(zid, semaphore)
                    for zid in range(max(zone_count, 0))
                ]
            )
            zones = dict(zone_items)

            _LOGGER.debug(
                "Messana fetched: system_status=%s temp_unit=%s api_zone_count=%s effective_zone_count=%s hc_groups=%s zones=%s",
                system_on,
                temp_unit,
                api_zone_count,
                zone_count,
                list(hc_groups.keys()),
                list(zones.keys()),
            )

            return {
                "system": {
                    "status": system_on,
                    "temp_unit": temp_unit,
                    "api_zone_count": api_zone_count,
                    "effective_zone_count": zone_count,
                },
                "hc_groups": hc_groups,
                "zones": zones,
            }

        except MessanaApiError as e:
            raise UpdateFailed(str(e)) from e
