"""Config flow: the user enters their own Dreame account (secondary account recommended)."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import SelectSelector, SelectSelectorConfig

from .api import DreameAuthError, DreameCloud, DreameError
from .const import CONF_REGION, DEFAULT_REGION, DOMAIN, MODEL, REGIONS


def _schema(username: str = "", region: str = DEFAULT_REGION) -> vol.Schema:
    return vol.Schema({
        vol.Required(CONF_USERNAME, default=username): str,
        vol.Required(CONF_PASSWORD): str,
        vol.Required(CONF_REGION, default=region): SelectSelector(
            SelectSelectorConfig(options=REGIONS, translation_key="region")),
    })


class PM20ConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def _find_pm20(self, data: dict[str, Any]) -> dict[str, Any]:
        cloud = DreameCloud(async_get_clientsession(self.hass), data[CONF_USERNAME],
                            data[CONF_PASSWORD], data[CONF_REGION])
        await cloud.login()
        for dev in await cloud.devices():
            if dev.get("model") == MODEL:
                return dev
        raise LookupError

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                dev = await self._find_pm20(user_input)
            except DreameAuthError:
                errors["base"] = "invalid_auth"
            except DreameError:
                errors["base"] = "cannot_connect"
            except LookupError:
                errors["base"] = "no_device"
            else:
                await self.async_set_unique_id(str(dev["did"]))
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title=dev.get("customName") or "Dreame AirPursue PM20", data=user_input)
        return self.async_show_form(step_id="user", data_schema=_schema(), errors=errors)

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        entry = self._get_reauth_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            data = {**entry.data, **user_input}
            try:
                await self._find_pm20(data)
            except DreameAuthError:
                errors["base"] = "invalid_auth"
            except (DreameError, LookupError):
                errors["base"] = "cannot_connect"
            else:
                return self.async_update_reload_and_abort(entry, data=data)
        return self.async_show_form(step_id="reauth_confirm",
                                    data_schema=vol.Schema({vol.Required(CONF_PASSWORD): str}), errors=errors)
