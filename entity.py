from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import MessanaCoordinator


class MessanaEntity(CoordinatorEntity[MessanaCoordinator]):
    """Common base for all Messana entities."""

    _attr_has_entity_name = True

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, "messana_system")},
            name="Messana",
            manufacturer="Messana",
            model="mBox",
        )
