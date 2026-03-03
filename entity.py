from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import MessanaCoordinator


class MessanaEntity(CoordinatorEntity[MessanaCoordinator]):
    """Common base for all Messana entities."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: MessanaCoordinator,
        *,
        zone_id: int | None = None,
        zone_name: str | None = None,
    ) -> None:
        super().__init__(coordinator)
        self._zone_id = zone_id
        self._zone_name = zone_name

    @property
    def device_info(self) -> DeviceInfo:
        # System-level device (mBox)
        system_ident = (DOMAIN, "messana_system")

        # Zone-specific device
        if self._zone_id is not None:
            zone_ident = (DOMAIN, f"messana_zone_{self._zone_id}")

            return DeviceInfo(
                identifiers={zone_ident},
                name=self._zone_name or f"Zone {self._zone_id + 1}",
                manufacturer="Messana",
                model="mBox Zone",
                via_device=system_ident,
            )

        return DeviceInfo(
            identifiers={system_ident},
            name="Messana",
            manufacturer="Messana",
            model="mBox",
        )
