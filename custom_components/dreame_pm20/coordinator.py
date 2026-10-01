"""Polling coordinator with optimistic state for writes."""
from __future__ import annotations

import logging
import time
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import DreameAuthError, DreameCloud, DreameError
from .const import DEBUG_ADDRESSES, DOMAIN, EXTRA_ADDRESSES, PROPS, SCAN_INTERVAL

_LOGGER = logging.getLogger(__name__)


class PM20Coordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Reads every mapped property every 30 s; keeps last good values if a read drops out."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, cloud: DreameCloud, device: dict[str, Any]) -> None:
        super().__init__(hass, _LOGGER, config_entry=entry, name=DOMAIN, update_interval=SCAN_INTERVAL)
        self.cloud = cloud
        self.device = device
        self.did = str(device["did"])
        self.bind_domain = device.get("bindDomain")
        self._addresses = [(p.siid, p.piid) for p in PROPS] + list(EXTRA_ADDRESSES)
        self._debug_left = 3  # read DEBUG_ADDRESSES on the next few polls only (not during first refresh)
        # key -> (value, expires_at). The cloud lags the device by up to minutes after a
        # write, so keep the written value until a poll agrees or it expires.
        self._optimistic: dict[str, tuple[object, float]] = {}

    def set_optimistic(self, values: dict[str, object], ttl: float = 90) -> None:
        exp = time.monotonic() + ttl
        for k, v in values.items():
            self._optimistic[k] = (v, exp)
        self.async_set_updated_data({**(self.data or {}), **values})

    async def heater_candidates_off(self) -> bool:
        """Fail closed: True only if both heater candidate addresses read -1 right now."""
        try:
            raw = await self.cloud.get_properties(self.did, self.bind_domain, [(2, 5), (2, 6)])
        except DreameError:
            return False
        return raw.get((2, 5)) == -1 and raw.get((2, 6)) == -1

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            raw = await self.cloud.get_properties(self.did, self.bind_domain, self._addresses)
        except DreameAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except DreameError as err:
            raise UpdateFailed(str(err)) from err
        if not raw and not self.data:
            raise UpdateFailed("no properties returned (device offline?)")
        data = dict(self.data or {})
        for prop in PROPS:
            if (prop.siid, prop.piid) in raw:
                data[prop.key] = raw[(prop.siid, prop.piid)]
        if self._debug_left > 0 and self.data is not None:
            self._debug_left -= 1
            try:
                dbg = await self.cloud.get_properties(self.did, self.bind_domain, list(DEBUG_ADDRESSES))
                data["debug"] = {f"{s},{p}": v for (s, p), v in sorted(dbg.items())}
            except DreameError:
                pass
        raw_extra = dict(data.get("raw") or {})
        raw_extra.update({f"{s},{p}": v for (s, p), v in raw.items() if (s, p) in EXTRA_ADDRESSES})
        data["raw"] = raw_extra
        now = time.monotonic()
        for key, (val, exp) in list(self._optimistic.items()):
            if now > exp or data.get(key) == val:
                del self._optimistic[key]
            else:
                data[key] = val
        return data
