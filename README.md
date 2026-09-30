# Dreame AirPursue PM20 for Home Assistant (read-only, v0.1)

Unofficial, **read-only** Home Assistant integration for the Dreame AirPursue PM20 air purifier (`dreame.airp.u2402`). It is not affiliated with Dreame.

## What it does
- It polls the Dreame cloud every 30 s and exposes these entities:
  - **Sensors:** PM2.5, PM10, PM1, HCHO, TVOC, temperature, humidity, air quality level, dominant pollutant
  - **Device state:** mode, fan level, swing angle, off timer, running, follow-me, radar auto start
  - **Filters:** HEPA and carbon filter life and days left
- **It never writes to the device.** The API client refuses every RPC method except `get_properties`, so there is no power, mode, fan or **heater** control. Heater-related properties are intentionally not read.

## Install
1. In HACS, open ⋮ → Custom repositories, add `https://github.com/osmnnl/dreame-pm20` with category **Integration**, and install it.
2. Restart Home Assistant.
3. Go to Settings → Devices & Services → Add integration → **Dreame AirPursue PM20**.
4. Enter your Dreamehome account and the server region your account is registered in (for example `sg`, `eu`).

Use a **secondary Dreamehome account** that the PM20 is shared with. Dreame offers no OAuth, so the password is stored in Home Assistant.

## Property map
All properties below were found with a read-only sweep of a real PM20 (fw 1.8.17_1070). Their meanings are inferred from the PM30 (`u2403`) map.

| siid,piid | Meaning |
|---|---|
| 2,1 | power (1 on / 2 standby) |
| 2,3 | mode (0 auto, 3 custom, 4 pet, 5 comfort) |
| 2,4 | fan level (1–10) |
| 2,7 | swing angle |
| 3,2 / 3,3 | humidity / temperature |
| 3,4 | air quality level |
| 3,5 / 3,6 / 3,10 | PM2.5 / PM10 / PM1 |
| 3,7 / 3,8 | HCHO / TVOC |
| 3,13 | dominant pollutant |
| 4,1–4,4 | HEPA and carbon filter life / days |
| 6,8 | off timer |
| 6,19 | radar auto power-on |
| 6,20 | follow |

`tools/pm20_probe.py` is a stdlib-only read-only sweep, snapshot and diff tool you can use to verify the map on your own device.

## Credits and disclaimer
- The wire-protocol facts (endpoints, headers, request envelope, app constants) come from community reverse engineering of the Dreamehome app. They are documented in [KalfDmytro/dreame-pm30-integration](https://github.com/KalfDmytro/dreame-pm30-integration) (MIT) and [Tasshack/dreame-vacuum](https://github.com/Tasshack/dreame-vacuum) (MIT). The code in this repository was written independently.
- This integration depends on an undocumented cloud API that may change or break at any time. Use at your own risk; the Dreame terms of service may apply.
- The PM20 contains a 2 kW heater. **Never automate turning it on while nobody is home.**
