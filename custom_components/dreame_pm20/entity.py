"""Base entity."""
from __future__ import annotations

from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER, MODEL
from .coordinator import PM20Coordinator


class PM20Entity(CoordinatorEntity[PM20Coordinator]):
    _attr_has_entity_name = True

    def __init__(self, coordinator: PM20Coordinator, key: str) -> None:
        super().__init__(coordinator)
        self._key = key
        self._attr_translation_key = key
        self._attr_unique_id = f"{coordinator.did}_{key}"
        dev = coordinator.device
        mac = dev.get("mac")
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.did)},
            connections={(CONNECTION_NETWORK_MAC, mac)} if mac else set(),
            manufacturer=MANUFACTURER,
            model="AirPursue PM20",
            model_id=MODEL,
            name=dev.get("customName") or "Dreame AirPursue PM20",
            sw_version=str((coordinator.data or {}).get("firmware", "")).strip('"') or None,
        )

    @property
    def available(self) -> bool:
        return super().available and self._key in (self.coordinator.data or {})

    @property
    def raw(self):
        return (self.coordinator.data or {}).get(self._key)
