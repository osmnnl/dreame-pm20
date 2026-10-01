"""Swing select, matching the app: OFF / Takip (follow) / 45° / 90° / 180°."""
from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api import DreameError
from .const import DOMAIN
from .entity import PM20Entity

PARALLEL_UPDATES = 1
OPTIONS = ["off", "follow", "45", "90", "180"]


async def async_setup_entry(hass: HomeAssistant, entry, async_add_entities: AddEntitiesCallback) -> None:
    async_add_entities([PM20Swing(entry.runtime_data.coordinator)])


class PM20Swing(PM20Entity, SelectEntity):
    _attr_options = OPTIONS

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "swing_angle")
        self._attr_unique_id = f"{coordinator.did}_swing_select"
        self._attr_translation_key = "swing"

    @property
    def current_option(self) -> str | None:
        d = self.coordinator.data or {}
        if d.get("follow") == 1:
            return "follow"
        a = d.get("swing_angle")
        return {0: "off", 45: "45", 90: "90", 180: "180"}.get(a)

    async def async_select_option(self, option: str) -> None:
        c = self.coordinator
        if option == "follow":
            values, opt = {(6, 20): 1}, {"follow": 1}
        else:
            angle = 0 if option == "off" else int(option)
            values, opt = {(2, 7): angle, (6, 20): 0}, {"swing_angle": angle, "follow": 0}
        try:
            await c.cloud.set_properties(c.did, c.bind_domain, values)
        except DreameError as err:
            raise HomeAssistantError(translation_domain=DOMAIN, translation_key="write_failed",
                                     translation_placeholders={"error": str(err)}) from err
        c.set_optimistic(opt)
