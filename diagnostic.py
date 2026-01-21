from __future__ import annotations

import json
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.components.sensor import SensorEntity

from .coordinator import MessanaCoordinator


class MessanaRawSampleSensor(CoordinatorEntity[MessanaCoordinator], SensorEntity):
    """Shows a compact snapshot of coordinator data for debugging."""

    _attr_has_entity_name = True
    _attr_name = "Debug Snapshot"
    _attr_icon = "mdi:bug-outline"

    def __init__(self, coordinator: MessanaCoordinator, entry_id: str) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"messana_{entry_id}_debug_snapshot"

    @property
    def native_value(self) -> str:
        data = self.coordinator.data or {}
        # Keep it small: system + zone0 key fields
        system = data.get("system", {})
        z0 = (data.get("zones", {}) or {}).get(0, {})
        payload = {
            "system": system,
            "zone0": {
                "name": z0.get("name"),
                "temperature": z0.get("temperature"),
                "humidity": z0.get("humidity"),
                "dewpoint": z0.get("dewpoint"),
                "setpoint": z0.get("setpoint"),
                "status": z0.get("status"),
            },
        }
        return json.dumps(payload, ensure_ascii=False)
