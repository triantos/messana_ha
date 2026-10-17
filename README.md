# Messana HVAC Integration for Home Assistant

Custom integration for [Messana](https://www.messana.com/) hydronic radiant heating/cooling systems (mBox controller).

## Installation (HACS)

1. Add this repository as a custom repository in HACS
2. Install "Messana" from the HACS integrations list
3. Restart Home Assistant
4. Add the integration via Settings > Devices & Services > Add Integration > Messana

## Configuration

You'll need:
- **Base URL**: The URL of your Messana mBox (e.g. `http://192.168.1.100`)
- **API Key**: Your Messana API key

## Features

- Climate entities per zone (temperature, setpoint, room-only on/off, heating/cooling/idle activity)
- Zone humidity and dew point sensors
- H/C group mode select (Heating / Cooling / Auto)
- Executive season sensor (heating vs cooling)
- Zone schedule status and detach buttons
- System on/off switch

## Shared system mode and room controls

The H/C group selector controls house-wide Heating, Cooling, or Auto changeover.
Each room follows that season; in Auto, its climate entity reports the executive
season actually selected by Messana. The room offers Off and the current season,
and its on/off actions change only that room. They never change system power or
season. If system power is off, enabling a room leaves it off until the system is
explicitly powered on with the system switch.

Schedule status distinguishes an enabled schedule from one currently applied.
Climate targets now use the web app's precedence: a temporary override, then a
variable temperature schedule, then the stored room default. Temperature bounds
come from the room's macrozone. Attributes include `default_temperature`, its
native `default_temperature_unit`, `macrozone_default_temperature`,
`matches_macrozone_default`, `target_source`, and `schedule_name`.

Each room has a **Default temperature** number and a **Copy global default**
button (or **Copy macrozone default** for other macrozones). These only change
the stored room default; they do not disable schedules or turn the room on.
Copying a default is a one-time copy, not a persistent inheritance setting.

The system's **All rooms default temperature** number uses the public macrozone
setpoint API. **It applies that default to every associated room, including
rooms with differing defaults.** Schedules remain enabled; a variable schedule
continues to supply the effective target. Both room and macrozone default
controls operate on the currently selected season, as in the web app.

The read-only `/api/table/GRP`, `RMS`, `MCZ`, and `SCH` endpoints used by the
Messana web app supplement the public API. No table writes are used. If those
reads fail, default controls become unavailable and existing REST-based climate
entities continue to work (with `target_source: default_only`). Table endpoints
were verified on controller API 0.10.0; they are not in the public 0.9.1 spec.

The existing "Detach zone schedule when manually setting temperature" option
still controls whether a manual setpoint disables that room's schedule. This is
not a temporary override. Named schedule selection is not yet exposed. The temperature range feature is not
advertised until separate heating/cooling setpoints can be verified in the API.

## Development

Test with Python 3.14 and the same Home Assistant release as the server:

```sh
uv venv .venv --python 3.14
uv pip install --python .venv/bin/python -r requirements-test.txt
.venv/bin/python -m pytest -q
```

`deploy.sh` copies the integration through the configured `homeassistant` SSH
alias (default user `hassio`, port 22). It does not delete remote files or restart
HA. The SSH user needs passwordless sudo to write the integration directory.
Restart Home Assistant after changing Python source; reloading the integration
alone reuses its already-imported modules. Reloading is sufficient for option
changes that do not change the source.
