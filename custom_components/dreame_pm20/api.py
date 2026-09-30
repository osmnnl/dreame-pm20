"""Minimal async Dreame cloud client — READ-ONLY.

Wire-format facts (endpoints, headers, app salt, request envelope) were
extracted from the Dreamehome app by the community; they are documented in
KalfDmytro/dreame-pm30-integration (MIT) ``api/protocol.py``. This file is an
independent re-implementation.

Safety: ``_rpc`` refuses every method except ``get_properties``. There is no
code path that writes a property or calls an action.
"""
from __future__ import annotations

import asyncio
import hashlib
import itertools
import logging
import time
from typing import Any
from urllib.parse import quote

import aiohttp

from .const import READ_BATCH_SIZE

_LOGGER = logging.getLogger(__name__)

_SALT = "RAylYC%fmSKp7%Tq"
_AUTH_BASIC = "Basic ZHJlYW1lX2FwcHYxOkFQXmR2QHpAU1FZVnhOODg="
_USER_AGENT = "Dreame_Smarthome/2.1.9 (iPhone; iOS 18.4.1; Scale/3.00)"
_DEFAULT_TENANT = "000000"
_PORT = 13267
_TIMEOUT = aiohttp.ClientTimeout(total=15)
_ALLOWED_METHODS = frozenset({"get_properties"})
_CODE_DEVICE_TIMEOUT = 80001

_ids = itertools.count(int(time.time()) % 100000)


class DreameError(Exception):
    """Generic cloud failure."""


class DreameAuthError(DreameError):
    """Login rejected (wrong credentials or wrong region)."""


class DreameCloud:
    """One authenticated session against one Dreame region."""

    def __init__(self, session: aiohttp.ClientSession, username: str, password: str, region: str) -> None:
        self._session = session
        self._username = username
        self._password = password
        self.region = region
        self._base = f"https://{region}.iot.dreame.tech:{_PORT}"
        self._token: str | None = None
        self._refresh: str | None = None
        self._expires = 0.0
        self._tenant = _DEFAULT_TENANT
        self._lock = asyncio.Lock()

    # ── auth ──────────────────────────────────────────────────────────
    def _form_headers(self) -> dict[str, str]:
        return {"User-Agent": _USER_AGENT, "Authorization": _AUTH_BASIC, "Tenant-Id": self._tenant,
                "Content-Type": "application/x-www-form-urlencoded", "Accept": "*/*"}

    async def _token_request(self, body: str) -> None:
        try:
            async with self._session.post(f"{self._base}/dreame-auth/oauth/token", data=body,
                                          headers=self._form_headers(), timeout=_TIMEOUT) as resp:
                data = await resp.json(content_type=None)
                status = resp.status
        except (aiohttp.ClientError, asyncio.TimeoutError) as err:
            raise DreameError(f"cannot reach Dreame cloud: {err}") from err
        if status != 200 or not isinstance(data, dict) or not data.get("access_token"):
            raise DreameAuthError(str(data.get("error") if isinstance(data, dict) else status))
        self._token = data["access_token"]
        self._refresh = data.get("refresh_token")
        self._tenant = data.get("tenant_id") or _DEFAULT_TENANT
        self._expires = time.monotonic() + float(data.get("expires_in", 3600))

    async def login(self) -> None:
        pw = hashlib.md5((self._password + _SALT).encode()).hexdigest()  # noqa: S324 (Dreame's scheme)
        await self._token_request("platform=IOS&scope=all&grant_type=password&type=account"
                                  f"&username={quote(self._username)}&password={pw}")

    async def _ensure_token(self) -> None:
        async with self._lock:
            if self._token and time.monotonic() < self._expires - 300:
                return
            if self._refresh:
                try:
                    await self._token_request("platform=IOS&scope=all&grant_type=refresh_token"
                                              f"&refresh_token={self._refresh}")
                    return
                except DreameError:
                    _LOGGER.debug("token refresh failed, logging in again")
            await self.login()

    async def _api(self, path: str, payload: dict[str, Any]) -> Any:
        await self._ensure_token()
        headers = {"User-Agent": _USER_AGENT, "Authorization": _AUTH_BASIC, "Tenant-Id": self._tenant,
                   "Dreame-Auth": self._token or "", "Content-Type": "application/json", "Accept": "*/*"}
        try:
            async with self._session.post(f"{self._base}{path}", json=payload, headers=headers,
                                          timeout=_TIMEOUT) as resp:
                if resp.status == 401:
                    self._token = None
                    raise DreameAuthError("unauthorized")
                return await resp.json(content_type=None)
        except (aiohttp.ClientError, asyncio.TimeoutError) as err:
            raise DreameError(f"request failed: {err}") from err

    # ── devices ───────────────────────────────────────────────────────
    async def devices(self) -> list[dict[str, Any]]:
        data = await self._api("/dreame-user-iot/iotuserbind/device/listV2", {})
        try:
            return list(data["data"]["page"]["records"])
        except (KeyError, TypeError) as err:
            raise DreameError(f"unexpected device list: {str(data)[:200]}") from err

    # ── read-only RPC ─────────────────────────────────────────────────
    async def _rpc(self, did: str, bind_domain: str | None, method: str, params: list) -> Any:
        if method not in _ALLOWED_METHODS:
            raise DreameError(f"method {method!r} is not allowed: this integration is read-only")
        shard = f"-{bind_domain.split('.')[0]}" if bind_domain else ""
        for delay in (1, 3, None):
            rid = next(_ids)  # must be unique, or replies get crossed
            payload = {"did": str(did), "id": rid,
                       "data": {"did": str(did), "id": rid, "method": method, "params": params}}
            data = await self._api(f"/dreame-iot-com{shard}/device/sendCommand", payload)
            code = data.get("code") if isinstance(data, dict) else None
            if code == 0:
                inner = data.get("data")
                if isinstance(inner, dict) and "result" in inner:
                    return inner["result"]
            if code != _CODE_DEVICE_TIMEOUT or delay is None:
                raise DreameError(f"device RPC failed (code {code})")
            await asyncio.sleep(delay)
        raise DreameError("device RPC failed")

    async def get_properties(self, did: str, bind_domain: str | None,
                             addresses: list[tuple[int, int]]) -> dict[tuple[int, int], Any]:
        """Read addresses in small batches; split a failed batch and retry one by one."""
        out: dict[tuple[int, int], Any] = {}
        for i in range(0, len(addresses), READ_BATCH_SIZE):
            batch = addresses[i:i + READ_BATCH_SIZE]
            try:
                results = await self._rpc(did, bind_domain, "get_properties",
                                          [{"did": str(did), "siid": s, "piid": p} for s, p in batch])
            except DreameError:
                results = []
                for s, p in batch:
                    try:
                        results += await self._rpc(did, bind_domain, "get_properties",
                                                   [{"did": str(did), "siid": s, "piid": p}])
                    except DreameError:
                        continue
            for entry in results or []:
                if isinstance(entry, dict) and entry.get("code") == 0 and entry.get("value") is not None:
                    out[(entry["siid"], entry["piid"])] = entry["value"]
        return out
