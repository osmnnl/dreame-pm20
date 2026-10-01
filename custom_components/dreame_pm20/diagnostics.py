"""Diagnostics with credentials and identifiers redacted."""
from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant

TO_REDACT = {CONF_PASSWORD, CONF_USERNAME, "did", "mac", "sn", "uid", "bindDomain", "localip", "1,5"}  # 1,5 = serial number


async def async_get_config_entry_diagnostics(hass: HomeAssistant, entry) -> dict[str, Any]:
    coordinator = entry.runtime_data.coordinator
    return {
        "entry": async_redact_data(dict(entry.data), TO_REDACT),
        "device": async_redact_data(coordinator.device, TO_REDACT),
        "data": async_redact_data(coordinator.data or {}, TO_REDACT),
    }
