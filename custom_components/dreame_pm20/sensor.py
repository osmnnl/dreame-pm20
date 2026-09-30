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
    CONCENTRATION_MICROGRAMS_PER_CUBIC_METER,
    PERCENTAGE,
    EntityCategory,
    UnitOfTemperature,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import AIR_QUALITY_NAMES, MODE_NAMES
from .entity import PM20Entity

_UG = CONCENTRATION_MICROGRAMS_PER_CUBIC_METER
_M = SensorStateClass.MEASUREMENT


@dataclass(frozen=True, kw_only=True)
class PM20SensorDescription(SensorEntityDescription):
    value: Callable[[Any], Any] = lambda v: v


def _enum(names: dict[int, str]) -> Callable[[Any], Any]:
    # Unknown values are shown as "value_<n>" so an unmapped mode is visible instead of hidden.
    return lambda v: names.get(v, f"value_{v}") if isinstance(v, int) else None


SENSORS: tuple[PM20SensorDescription, ...] = (
    PM20SensorDescription(key="pm25", device_class=SensorDeviceClass.PM25, native_unit_of_measurement=_UG, state_class=_M),
    PM20SensorDescription(key="pm10", device_class=SensorDeviceClass.PM10, native_unit_of_measurement=_UG, state_class=_M),
    PM20SensorDescription(key="pm1", device_class=SensorDeviceClass.PM1, native_unit_of_measurement=_UG, state_class=_M),
    PM20SensorDescription(key="hcho", native_unit_of_measurement=_UG, state_class=_M),
    PM20SensorDescription(key="tvoc", native_unit_of_measurement=_UG, state_class=_M),
    PM20SensorDescription(key="temperature", device_class=SensorDeviceClass.TEMPERATURE,
                          native_unit_of_measurement=UnitOfTemperature.CELSIUS, state_class=_M),
    PM20SensorDescription(key="humidity", device_class=SensorDeviceClass.HUMIDITY,
                          native_unit_of_measurement=PERCENTAGE, state_class=_M),
    # Not an ENUM sensor on purpose: only levels 1-2 are confirmed, unknown values must not raise.
    PM20SensorDescription(key="air_quality", value=_enum(AIR_QUALITY_NAMES)),
    PM20SensorDescription(key="dominant_pollutant", entity_registry_enabled_default=False),
    PM20SensorDescription(key="mode", value=_enum(MODE_NAMES)),
    PM20SensorDescription(key="fan_level", state_class=_M),
    PM20SensorDescription(key="swing_angle", native_unit_of_measurement="°"),
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
    def native_value(self):
        return self.entity_description.value(self.raw)
