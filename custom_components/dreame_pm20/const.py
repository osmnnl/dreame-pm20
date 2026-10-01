"""Constants and the u2402 property map for Dreame AirPursue PM20.

v0.1 is READ-ONLY. Nothing in this integration writes to the device: the only
RPC method the API client will send is ``get_properties`` (see api.py).

Addresses come from the PM30 (dreame.airp.u2403) map published by
KalfDmytro/dreame-pm30-integration (MIT). A read-only sweep of a real PM20 on
2026-10-01 (fw 1.8.17_1070, region sg) found every address below readable with
plausible values; semantics of M/L rows still need app-side diffs. 2,5 and 2,6
(both -1) are heater candidates and are intentionally NOT read. Confidence:
H = confirmed on PM30 and the PM20 has the same public feature,
M = confirmed on PM30, less certain on PM20, L = guess.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

DOMAIN = "dreame_pm20"
MODEL = "dreame.airp.u2402"
MANUFACTURER = "Dreame"

CONF_REGION = "region"
REGIONS = ["eu", "sg", "ru", "us", "kr", "cn"]
DEFAULT_REGION = "eu"

SCAN_INTERVAL = timedelta(seconds=30)
READ_BATCH_SIZE = 10


@dataclass(frozen=True)
class Prop:
    key: str          # translation_key / data key (hassfest-safe snake_case)
    siid: int
    piid: int
    confidence: str   # H / M / L


# Sensors the v0.1 integration reads. Heater-related addresses are unknown and
# deliberately absent.
PROPS: tuple[Prop, ...] = (
    Prop("power", 2, 1, "H"),            # 1 = on, 2 = standby
    Prop("mode", 2, 3, "M"),             # 0 auto, 3 custom, 4 pet, 5 comfort (PM30); PM20 may add more
    Prop("fan_level", 2, 4, "H"),        # 1-10
    Prop("swing_angle", 2, 7, "H"),      # 0 / 45 / 90 / 180
    Prop("fault", 2, 2, "L"),
    Prop("humidity", 3, 2, "H"),
    Prop("temperature", 3, 3, "H"),
    Prop("air_quality", 3, 4, "H"),      # 1 excellent, 2 good, ... (lower is better)
    Prop("pm25", 3, 5, "H"),
    Prop("pm10", 3, 6, "H"),
    Prop("hcho", 3, 7, "M"),             # µg/m³ (FP10 uses 3,7 for TVOC: verify!)
    Prop("tvoc", 3, 8, "M"),             # µg/m³
    Prop("pm1", 3, 10, "H"),
    Prop("dominant_pollutant", 3, 13, "M"),
    Prop("hepa_life", 4, 1, "H"),        # %
    Prop("hepa_days", 4, 2, "H"),
    Prop("carbon_life", 4, 3, "H"),      # %
    Prop("carbon_days", 4, 4, "H"),
    Prop("off_timer", 6, 8, "M"),        # hours 0-12
    Prop("auto_power_on", 6, 19, "M"),   # radar auto start (manual: TR says default ON)
    Prop("follow", 6, 20, "M"),          # airflow follows person
    Prop("firmware", 1, 4, "M"),
)

PROP_BY_KEY = {p.key: p for p in PROPS}

# Every address the 2026-10-01 sweep found readable that is not mapped above.
# Read-only, exposed only in diagnostics ("raw"), used to locate the heater.
EXTRA_ADDRESSES: tuple[tuple[int, int], ...] = (
    (1, 5), (2, 5), (2, 6), (2, 8), (3, 9), (3, 11), (3, 12),
    (6, 1), (6, 2), (6, 3), (6, 4), (6, 7), (6, 14), (6, 15),
)

MODE_NAMES = {0: "auto", 3: "custom", 4: "pet", 5: "comfort"}  # 0, 3, 5 confirmed on PM20 (2026-10-01)
# Levels as named in the PM20 manual: excellent, good, mild pollution, heavy pollution.
AIR_QUALITY_NAMES = {1: "excellent", 2: "good", 3: "mild_pollution", 4: "heavy_pollution"}
