"""Read-only binary sensors."""
from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .entity import PM20Entity

# key -> (value meaning "on", device_class, entity_category)
_BINARY = {
    "power": (1, BinarySensorDeviceClass.RUNNING, None),          # 1 on / 2 standby
    "follow": (1, None, None),
    "auto_power_on": (1, None, EntityCategory.DIAGNOSTIC),
}


async def async_setup_entry(hass: HomeAssistant, entry, async_add_entities: AddEntitiesCallback) -> None:
    coordinator = entry.runtime_data.coordinator
    async_add_entities(PM20Binary(coordinator, key) for key in _BINARY)


class PM20Binary(PM20Entity, BinarySensorEntity):
    def __init__(self, coordinator, key: str) -> None:
        super().__init__(coordinator, key)
        on_value, device_class, category = _BINARY[key]
        self._on = on_value
        self._attr_device_class = device_class
        self._attr_entity_category = category

    @property
    def is_on(self) -> bool | None:
        return None if self.raw is None else self.raw == self._on
