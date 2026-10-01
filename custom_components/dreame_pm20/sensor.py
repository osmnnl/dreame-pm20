"""Read-only sensors."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    PERCENTAGE,
    EntityCategory,
    UnitOfDensity,
    UnitOfTemperature,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import AIR_QUALITY_NAMES, MODE_NAMES
from .entity import PM20Entity

_UG = UnitOfDensity.MICROGRAMS_PER_CUBIC_METER
_M = SensorStateClass.MEASUREMENT


@dataclass(frozen=True, kw_only=True)
class PM20SensorDescription(SensorEntityDescription):
    value: Callable[[Any], Any] = lambda v: v
    # In standby (power == 2) the PM20 switches its air sensors off and reports 0.
    # Show "unknown" instead of a misleading 0 °C / 0 µg/m³.
    off_in_standby: bool = False


def _enum(names: dict[int, str]) -> Callable[[Any], Any]:
    # Unmapped values become "unknown"; the raw number stays visible in the "raw_value" attribute.
    return lambda v: names.get(v, "unknown") if isinstance(v, int) else None


SENSORS: tuple[PM20SensorDescription, ...] = (
    PM20SensorDescription(key="pm25", off_in_standby=True, device_class=SensorDeviceClass.PM25, native_unit_of_measurement=_UG, state_class=_M),
    PM20SensorDescription(key="pm10", off_in_standby=True, device_class=SensorDeviceClass.PM10, native_unit_of_measurement=_UG, state_class=_M),
    PM20SensorDescription(key="pm1", off_in_standby=True, device_class=SensorDeviceClass.PM1, native_unit_of_measurement=_UG, state_class=_M),
    # The device reports µg/m³; the Dreamehome app shows mg/m³, so do the same.
    PM20SensorDescription(key="hcho", off_in_standby=True, native_unit_of_measurement="mg/m³", state_class=_M,
                          suggested_display_precision=2,
                          value=lambda v: round(v / 1000, 3) if isinstance(v, (int, float)) else None),
    PM20SensorDescription(key="tvoc", native_unit_of_measurement=_UG, state_class=_M),
    PM20SensorDescription(key="temperature", off_in_standby=True, device_class=SensorDeviceClass.TEMPERATURE,
                          native_unit_of_measurement=UnitOfTemperature.CELSIUS, state_class=_M),
    PM20SensorDescription(key="humidity", off_in_standby=True, device_class=SensorDeviceClass.HUMIDITY,
                          native_unit_of_measurement=PERCENTAGE, state_class=_M),
    PM20SensorDescription(key="air_quality", device_class=SensorDeviceClass.ENUM,
                          options=[*AIR_QUALITY_NAMES.values(), "unknown"], value=_enum(AIR_QUALITY_NAMES)),
    PM20SensorDescription(key="dominant_pollutant", entity_registry_enabled_default=False),
    PM20SensorDescription(key="mode", device_class=SensorDeviceClass.ENUM,
                          options=[*MODE_NAMES.values(), "unknown"], value=_enum(MODE_NAMES)),
    PM20SensorDescription(key="fan_level", state_class=_M),
    # Matches the app's "Salınım" control: OFF / Takip (follow) / 45° / 90° / 180°.
    PM20SensorDescription(key="swing_angle", device_class=SensorDeviceClass.ENUM,
                          options=["off", "follow", "45", "90", "180", "unknown"]),
    PM20SensorDescription(key="off_timer", native_unit_of_measurement=UnitOfTime.HOURS),
    PM20SensorDescription(key="hepa_life", native_unit_of_measurement=PERCENTAGE, entity_category=EntityCategory.DIAGNOSTIC),
    PM20SensorDescription(key="hepa_days", native_unit_of_measurement=UnitOfTime.DAYS, entity_category=EntityCategory.DIAGNOSTIC),
    PM20SensorDescription(key="carbon_life", native_unit_of_measurement=PERCENTAGE, entity_category=EntityCategory.DIAGNOSTIC),
    PM20SensorDescription(key="carbon_days", native_unit_of_measurement=UnitOfTime.DAYS, entity_category=EntityCategory.DIAGNOSTIC),
    PM20SensorDescription(key="fault", entity_category=EntityCategory.DIAGNOSTIC, entity_registry_enabled_default=False),
)


async def async_setup_entry(hass: HomeAssistant, entry, async_add_entities: AddEntitiesCallback) -> None:
    coordinator = entry.runtime_data.coordinator
    async_add_entities(PM20Sensor(coordinator, d) for d in SENSORS)


class PM20Sensor(PM20Entity, SensorEntity):
    entity_description: PM20SensorDescription

    def __init__(self, coordinator, description: PM20SensorDescription) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def extra_state_attributes(self):
        if self.entity_description.device_class == SensorDeviceClass.ENUM:
            return {"raw_value": self.raw}
        return None

    @property
    def native_value(self):
        if self._key == "swing_angle":
            data = self.coordinator.data or {}
            if data.get("follow") == 1:
                return "follow"
            angle = data.get("swing_angle")
            if angle in (None, 0):
                return "off" if angle == 0 else None
            return str(angle) if angle in (45, 90, 180) else "unknown"
        if self.entity_description.off_in_standby and (self.coordinator.data or {}).get("power") == 2:
            return None
        return self.entity_description.value(self.raw)
