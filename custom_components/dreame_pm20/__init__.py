"""Dreame AirPursue PM20 Home Assistant integration (heater is never controlled)."""
from __future__ import annotations

from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import DreameAuthError, DreameCloud, DreameError
from .const import CONF_REGION, MODEL
from .coordinator import PM20Coordinator

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.BINARY_SENSOR, Platform.FAN, Platform.SELECT]


@dataclass
class PM20Data:
    coordinator: PM20Coordinator


PM20ConfigEntry = ConfigEntry  # typed alias kept simple for older Python tooling


async def async_setup_entry(hass: HomeAssistant, entry: PM20ConfigEntry) -> bool:
    cloud = DreameCloud(async_get_clientsession(hass), entry.data[CONF_USERNAME],
                        entry.data[CONF_PASSWORD], entry.data[CONF_REGION])
    try:
        await cloud.login()
        devices = await cloud.devices()
    except DreameAuthError as err:
        raise ConfigEntryAuthFailed(str(err)) from err
    except DreameError as err:
        raise ConfigEntryNotReady(str(err)) from err

    device = next((d for d in devices if str(d.get("did")) == entry.unique_id), None)
    if device is None or device.get("model") != MODEL:
        raise ConfigEntryNotReady("PM20 not found on this account")

    coordinator = PM20Coordinator(hass, entry, cloud, device)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = PM20Data(coordinator)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: PM20ConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
