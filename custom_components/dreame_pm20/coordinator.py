"""Polling coordinator (read-only)."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import DreameAuthError, DreameCloud, DreameError
from .const import DOMAIN, PROPS, SCAN_INTERVAL

_LOGGER = logging.getLogger(__name__)


class PM20Coordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Reads every mapped property every 30 s; keeps last good values if a read drops out."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, cloud: DreameCloud, device: dict[str, Any]) -> None:
        super().__init__(hass, _LOGGER, config_entry=entry, name=DOMAIN, update_interval=SCAN_INTERVAL)
        self.cloud = cloud
        self.device = device
        self.did = str(device["did"])
        self.bind_domain = device.get("bindDomain")
        self._addresses = [(p.siid, p.piid) for p in PROPS]

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
        return data
