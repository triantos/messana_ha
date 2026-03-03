from __future__ import annotations

from datetime import timedelta
from typing import Any
import logging

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import MessanaClient, MessanaApiError

_LOGGER = logging.getLogger(__name__)


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

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            system_on = await self.client.get_system_status()
            temp_unit = await self.client.get_temp_unit()
            api_zone_count = await self.client.get_zone_count()
            hc_count = await self.client.get_hc_group_count()

            zone_count = self.zone_count_override or api_zone_count

            hc_groups: dict[int, dict[str, Any]] = {}
            for gid in range(max(hc_count, 0)):
                mode = await self.client.get_hc_mode(gid)
                ex_season = await self.client.get_hc_executive_season(gid)
                hc_groups[gid] = {"mode": mode, "executive_season": ex_season}

            zones: dict[int, dict[str, Any]] = {}
            for zid in range(max(zone_count, 0)):
                name = await self.client.get_zone_name(zid)
                temp = await self.client.get_zone_temperature(zid)
                rh = await self.client.get_zone_humidity(zid)
                dp = await self.client.get_zone_dewpoint(zid)
                sp = await self.client.get_zone_setpoint(zid)
                on = await self.client.get_zone_status(zid)
                thermal_status = await self.client.get_zone_thermal_status(zid)
                schedule_on = await self.client.get_zone_schedule_on(zid)
                schedule_status = await self.client.get_zone_schedule_status(zid)

                zones[zid] = {
                    "id": zid,
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
