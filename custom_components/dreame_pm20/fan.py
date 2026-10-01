"""Purifier fan: power, speed 1-10, presets. Never touches the heater."""
from __future__ import annotations

import math
from typing import Any

from homeassistant.components.fan import FanEntity, FanEntityFeature
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util.percentage import percentage_to_ranged_value, ranged_value_to_percentage

from .api import DreameError
from .const import DOMAIN
from .entity import PM20Entity

PARALLEL_UPDATES = 1
SPEED_RANGE = (1, 10)
CUSTOM = 3
PRESETS = {"auto": 0, "pet": 4, "comfort": 5}   # "custom" is not a preset: set a speed instead


async def async_setup_entry(hass: HomeAssistant, entry, async_add_entities: AddEntitiesCallback) -> None:
    async_add_entities([PM20Fan(entry.runtime_data.coordinator)])


class PM20Fan(PM20Entity, FanEntity):
    _attr_supported_features = (FanEntityFeature.TURN_ON | FanEntityFeature.TURN_OFF
                                | FanEntityFeature.SET_SPEED | FanEntityFeature.PRESET_MODE)
    _attr_speed_count = 10
    _attr_preset_modes = list(PRESETS)
    _attr_name = None  # the device itself

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "power")
        self._attr_unique_id = f"{coordinator.did}_fan"
        self._attr_translation_key = "purifier"

    @property
    def _d(self) -> dict:
        return self.coordinator.data or {}

    @property
    def is_on(self) -> bool | None:
        p = self._d.get("power")
        return None if p is None else p == 1

    @property
    def percentage(self) -> int | None:
        lvl = self._d.get("fan_level")
        return ranged_value_to_percentage(SPEED_RANGE, lvl) if isinstance(lvl, int) and lvl > 0 else None

    @property
    def preset_mode(self) -> str | None:
        return next((k for k, v in PRESETS.items() if v == self._d.get("mode")), None)

    async def _guarded(self, coro) -> None:
        try:
            await coro
        except DreameError as err:
            raise HomeAssistantError(translation_domain=DOMAIN, translation_key="write_failed",
                                     translation_placeholders={"error": str(err)}) from err

    async def async_turn_on(self, percentage: int | None = None, preset_mode: str | None = None, **kwargs: Any) -> None:
        c = self.coordinator
        # The PM20 resumes its last settings on power-up, which could include heating.
        if self._d.get("power") != 1 and not await c.heater_candidates_off():
            raise HomeAssistantError(translation_domain=DOMAIN, translation_key="heater_guard")
        if self._d.get("power") != 1:
            await self._guarded(c.cloud.call_action(c.did, c.bind_domain, 2, 1, 1))
            c.set_optimistic({"power": 1})
        if preset_mode:
            await self.async_set_preset_mode(preset_mode)
        elif percentage:
            await self.async_set_percentage(percentage)

    async def async_turn_off(self, **kwargs: Any) -> None:
        c = self.coordinator
        await self._guarded(c.cloud.call_action(c.did, c.bind_domain, 2, 1, 0))
        c.set_optimistic({"power": 2})

    async def async_set_percentage(self, percentage: int) -> None:
        if percentage == 0:
            await self.async_turn_off()
            return
        level = max(1, min(10, math.ceil(percentage_to_ranged_value(SPEED_RANGE, percentage))))
        c = self.coordinator
        await self._guarded(c.cloud.set_properties(c.did, c.bind_domain, {(2, 3): CUSTOM, (2, 4): level}))
        c.set_optimistic({"mode": CUSTOM, "fan_level": level})

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        c = self.coordinator
        await self._guarded(c.cloud.set_properties(c.did, c.bind_domain, {(2, 3): PRESETS[preset_mode]}))
        c.set_optimistic({"mode": PRESETS[preset_mode]})

    @property
    def available(self) -> bool:
        return self.coordinator.last_update_success and "power" in self._d
