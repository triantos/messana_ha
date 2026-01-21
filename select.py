from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import MessanaCoordinator
from .api import MessanaClient
from .entity import MessanaEntity


# /api/hc/mode: 0 Heating, 1 Cooling, 2 Auto :contentReference[oaicite:40]{index=40}
OPTIONS = ["Heating", "Cooling", "Auto"]
OPTION_TO_VALUE = {"Heating": 0, "Cooling": 1, "Auto": 2}
VALUE_TO_OPTION = {0: "Heating", 1: "Cooling", 2: "Auto"}


@dataclass(frozen=True)
class HCGroupRef:
    group_id: int


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator: MessanaCoordinator = data["coordinator"]
    client: MessanaClient = data["client"]

    hc_groups = coordinator.data.get("hc_groups", {})
    entities: list[MessanaHCModeSelect] = []
    for gid in sorted(hc_groups.keys()):
        entities.append(MessanaHCModeSelect(coordinator, client, HCGroupRef(int(gid))))
    async_add_entities(entities)


class MessanaHCModeSelect(MessanaEntity, SelectEntity):
    _attr_has_entity_name = True
    _attr_options = OPTIONS

    def __init__(self, coordinator: MessanaCoordinator, client: MessanaClient, ref: HCGroupRef) -> None:
        super().__init__(coordinator)
        self.client = client
        self.group_id = ref.group_id
        self._attr_unique_id = f"messana_hc_group_{self.group_id}_mode"
        self._attr_name = f"H/C Group {self.group_id} Mode"

    @property
    def current_option(self) -> str | None:
        mode = int(self.coordinator.data.get("hc_groups", {}).get(self.group_id, {}).get("mode", 2))
        return VALUE_TO_OPTION.get(mode, "Auto")

    async def async_select_option(self, option: str) -> None:
        value = OPTION_TO_VALUE[option]
        await self.client.set_hc_mode(self.group_id, value)  # :contentReference[oaicite:41]{index=41}
        await self.coordinator.async_request_refresh()
