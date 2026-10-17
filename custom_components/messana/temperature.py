"""Interpret temperatures using the same precedence as the Messana web app.

Verified on controller API 0.10.0 / web app main.4c5ada0a35b81c5a.js:
season 0 = heating, 1 = cooling; schedule types 2/3 = variable/dual variable.
Macrozone defaults are copied into rooms, not a persistent inheritance flag.
"""
from __future__ import annotations

import math
from typing import Any


def valid_temperature(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) and value > -3000 else None


def current_season(group: dict[str, Any]) -> int | None:
    mode = group.get("mode")
    season = group.get("executive_season") if mode == 2 else mode
    return season if season in (0, 1) else None


def macrozone_temperatures(row: dict[str, Any], groups: dict) -> dict[str, Any]:
    season = current_season(groups.get(row.get("CFG_IdxGRP"), {}))
    if season is None:
        return {"name": row.get("CFG_Name"), "season": None}
    suffix = "H" if season == 0 else "C"
    return {
        "name": row.get("CFG_Name"), "season": season,
        "default_setpoint": valid_temperature(row.get(f"PAR_SetTemp{suffix}")),
        "min_temp": valid_temperature(row.get(f"TEC_SetTempMin{suffix}")),
        "max_temp": valid_temperature(row.get(f"TEC_SetTempMax{suffix}")),
    }


def room_temperatures(row: dict[str, Any], schedules: dict, groups: dict,
                      macrozones: dict) -> dict[str, Any]:
    group_id = row.get("CFG_IdxGRP")
    macrozone_id = row.get("CFG_IdxMCZ")
    group = groups.get(group_id, {})
    season = current_season(group)
    result = {"hc_group_id": group_id, "macrozone_id": macrozone_id,
              "effective_setpoint": None, "target_source": "unknown"}
    if season is None:
        return result
    suffix = "H" if season == 0 else "C"
    default = valid_temperature(row.get(f"PAR_SetTemp{suffix}"))
    macrozone = macrozones.get(macrozone_id, {})
    macro_default = macrozone.get("default_setpoint")
    result.update(default_setpoint=default, macrozone_default=macro_default,
                  min_temp=macrozone.get("min_temp"), max_temp=macrozone.get("max_temp"),
                  matches_macrozone_default=(math.isclose(default, macro_default, abs_tol=0.001)
                                             if default is not None and macro_default is not None else None))
    schedule_on = row.get(f"PAR_SchedOn{suffix}") in (True, 1)
    schedule = schedules.get(row.get(f"PAR_IdxSCH_{suffix}"), {}) if schedule_on else {}
    result["schedule_name"] = schedule.get("CFG_Name")
    # The UI prefers an active override, then a temperature schedule, then default.
    # Dual overrides use side-specific fields; single overrides use unsuffixed fields.
    dual = group.get("mode") == 2 and group.get("auto_mode_style") == 2
    override_suffix = suffix if dual else ""
    remaining = row.get(f"RTU_SpoRemain{override_suffix}") or 0
    if isinstance(remaining, (int, float)) and remaining > 0:
        result.update(effective_setpoint=valid_temperature(row.get(f"PAR_SpoSetTemp{override_suffix}")),
                      target_source="override")
        return result
    if schedule.get("CFG_Type") == (3 if dual else 2):
        field = f"RTU_SetPoint{suffix}" if dual else "RTU_SetPoint"
        result.update(effective_setpoint=valid_temperature(schedule.get(field)), target_source="schedule")
    elif schedule_on and not schedule:
        # Missing schedule data must not masquerade as an effective default.
        result["target_source"] = "unknown"
    else:
        result.update(effective_setpoint=default, target_source="default")
    return result
