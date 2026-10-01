"""PM20 heater as a guarded climate entity.

Safety rules (enforced here, so they cover every automation, script and voice command):
- Heater control is OFF by default; it must be enabled in the integration options.
- Turning heat ON is refused unless the presence entity says someone is home
  (zone.home > 0 or a person/device_tracker "home"); unknown means refused.
- Target is capped at HEAT_MAX_C (26 °C).
- Heat is switched off automatically after the configured max time (default 120 min, max 240), when everyone leaves,
  and at startup if it is on while nobody is home.
- Turning heat OFF is always allowed.
"""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.climate import ClimateEntity, ClimateEntityFeature, HVACMode
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_call_later, async_track_state_change_event

from .api import DreameError
from .const import (CONF_ALLOW_HEATER, CONF_MAX_MINUTES, CONF_PRESENCE_ENTITY, DEFAULT_PRESENCE_ENTITY, DOMAIN, HEAT_MAX_C,
                    HEAT_MAX_MINUTES, HEAT_MIN_C, HEAT_OFF, HEAT_TARGET)
from .entity import PM20Entity

_LOGGER = logging.getLogger(__name__)
PARALLEL_UPDATES = 1


async def async_setup_entry(hass: HomeAssistant, entry, async_add_entities: AddEntitiesCallback) -> None:
    async_add_entities([PM20Heater(entry.runtime_data.coordinator, entry)])


class PM20Heater(PM20Entity, ClimateEntity):
    _attr_hvac_modes = [HVACMode.OFF, HVACMode.HEAT]
    _attr_supported_features = (ClimateEntityFeature.TARGET_TEMPERATURE
                                | ClimateEntityFeature.TURN_ON | ClimateEntityFeature.TURN_OFF)
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_min_temp = HEAT_MIN_C
    _attr_max_temp = HEAT_MAX_C
    _attr_target_temperature_step = 1
    _enable_turn_on_off_backwards_compatibility = False

    def __init__(self, coordinator, entry) -> None:
        super().__init__(coordinator, "heat_target")
        self._attr_unique_id = f"{coordinator.did}_heater"
        self._attr_translation_key = "heater"
        self._entry = entry
        self._timer = None

    # ── state ────────────────────────────────────────────────────────
    @property
    def _target(self):
        return (self.coordinator.data or {}).get("heat_target")

    @property
    def hvac_mode(self) -> HVACMode | None:
        t = self._target
        if t is None:
            return None
        return HVACMode.OFF if t == HEAT_OFF else HVACMode.HEAT

    @property
    def target_temperature(self) -> float | None:
        t = self._target
        return None if t in (None, HEAT_OFF) else float(t)

    @property
    def current_temperature(self) -> float | None:
        t = (self.coordinator.data or {}).get("temperature")
        return float(t) if isinstance(t, (int, float)) and (self.coordinator.data or {}).get("power") == 1 else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"control_allowed": self._allowed, "max_minutes": self._max_minutes}

    # ── guards ───────────────────────────────────────────────────────
    @property
    def _allowed(self) -> bool:
        return bool(self._entry.options.get(CONF_ALLOW_HEATER, False))

    @property
    def _max_minutes(self) -> int:
        return int(self._entry.options.get(CONF_MAX_MINUTES, HEAT_MAX_MINUTES))

    @property
    def _presence_entity(self) -> str:
        return self._entry.options.get(CONF_PRESENCE_ENTITY, DEFAULT_PRESENCE_ENTITY)

    def _someone_home(self) -> bool:
        st = self.hass.states.get(self._presence_entity)
        if st is None:
            return False
        if st.domain == "zone":
            try:
                return int(st.state) > 0
            except ValueError:
                return False
        return st.state == "home"

    def _refuse(self, key: str) -> None:
        # A refusal is expected behaviour, not a failure: shown to the user as a validation error.
        raise ServiceValidationError(translation_domain=DOMAIN, translation_key=key)

    async def _write(self, value: int) -> None:
        c = self.coordinator
        try:
            await c.cloud.set_properties(c.did, c.bind_domain, {HEAT_TARGET: value})
        except DreameError as err:
            raise HomeAssistantError(translation_domain=DOMAIN, translation_key="write_failed",
                                     translation_placeholders={"error": str(err)}) from err
        c.set_optimistic({"heat_target": value})

    # ── actions ──────────────────────────────────────────────────────
    async def _heat(self, temp: int) -> None:
        if not self._allowed:
            self._refuse("heater_disabled")
        if not self._someone_home():
            self._refuse("heater_nobody_home")
        if (self.coordinator.data or {}).get("power") != 1:
            self._refuse("heater_device_off")
        temp = max(HEAT_MIN_C, min(HEAT_MAX_C, int(round(temp))))
        await self._write(temp)
        self._arm_timer()

    async def _off(self, reason: str) -> None:
        self._cancel_timer()
        _LOGGER.warning("PM20 heater turned off by Home Assistant (%s)", reason)
        await self._write(HEAT_OFF)

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        if hvac_mode == HVACMode.OFF:
            await self._off("user")
        else:
            await self._heat(int(self.target_temperature or 22))

    async def async_turn_on(self) -> None:
        await self.async_set_hvac_mode(HVACMode.HEAT)

    async def async_turn_off(self) -> None:
        await self._off("user")

    async def async_set_temperature(self, **kwargs: Any) -> None:
        temp = kwargs.get(ATTR_TEMPERATURE)
        if temp is None:
            return
        if self.hvac_mode == HVACMode.HEAT or kwargs.get("hvac_mode") == HVACMode.HEAT:
            await self._heat(int(temp))
        # While off, a new setpoint alone does not start heating.

    # ── watchdogs ────────────────────────────────────────────────────
    def _arm_timer(self) -> None:
        self._cancel_timer()
        self._timer = async_call_later(self.hass, self._max_minutes * 60, self._timeout)

    def _cancel_timer(self) -> None:
        if self._timer:
            self._timer()
            self._timer = None

    async def _timeout(self, _now) -> None:
        self._timer = None
        if self.hvac_mode == HVACMode.HEAT:
            await self._off(f"max {self._max_minutes} min")

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(async_track_state_change_event(
            self.hass, [self._presence_entity], self._presence_changed))
        self.async_on_remove(self._cancel_timer)
        # Startup safety: never leave heating on with nobody home; otherwise start the max-time timer.
        if self.hvac_mode == HVACMode.HEAT:
            if not self._someone_home():
                self.hass.async_create_task(self._off("startup, nobody home"))
            else:
                self._arm_timer()

    @callback
    def _presence_changed(self, event: Event) -> None:
        if self.hvac_mode == HVACMode.HEAT and not self._someone_home():
            self.hass.async_create_task(self._off("everyone left"))

    @callback
    def _handle_coordinator_update(self) -> None:
        # Heating started from the app/device also gets the max-time timer.
        if self.hvac_mode == HVACMode.HEAT and self._timer is None:
            self._arm_timer()
        elif self.hvac_mode == HVACMode.OFF:
            self._cancel_timer()
        super()._handle_coordinator_update()
