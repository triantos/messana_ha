"""Web-app comparison fixtures observed on October 16, 2026 (API 0.10.0)."""
import pytest

from custom_components.messana.temperature import macrozone_temperatures, room_temperatures, valid_temperature


@pytest.fixture
def groups():
    return {0: {"mode": 0, "executive_season": 0, "auto_mode_style": 0}}


@pytest.fixture
def macros(groups):
    return {0: macrozone_temperatures({"CFG_Name": "All", "CFG_IdxGRP": 0,
        "PAR_SetTempH": 23, "PAR_SetTempC": 24, "TEC_SetTempMinH": 15,
        "TEC_SetTempMaxH": 30, "TEC_SetTempMinC": 16, "TEC_SetTempMaxC": 29}, groups)}


@pytest.fixture
def row():
    return {"CFG_IdxGRP": 0, "CFG_IdxMCZ": 0, "PAR_SetTempH": 27,
        "PAR_SetTempC": 24.5, "PAR_SchedOnH": True, "PAR_SchedOnC": False,
        "PAR_IdxSCH_H": 1, "PAR_IdxSCH_C": 1, "RTU_SpoRemain": 0}


@pytest.fixture
def schedules():
    return {1: {"CFG_Type": 2, "CFG_Name": "Day Time 23°", "RTU_SetPoint": 23}}


def test_great_room_defaults_differ_from_web_app_target(row, schedules, groups, macros):
    result = room_temperatures(row, schedules, groups, macros)
    assert result["default_setpoint"] == 27
    assert result["macrozone_default"] == 23
    assert result["effective_setpoint"] == 23
    assert result["matches_macrozone_default"] is False
    assert result["target_source"] == "schedule"
    assert result["schedule_name"] == "Day Time 23°"
    assert (result["min_temp"], result["max_temp"]) == (15, 30)


def test_foyer_schedule_off_uses_room_default(row, schedules, groups, macros):
    row["PAR_SchedOnH"] = False
    result = room_temperatures(row, schedules, groups, macros)
    assert result["effective_setpoint"] == 27
    assert result["target_source"] == "default"
    assert result["schedule_name"] is None


def test_matching_global_default_is_value_comparison_not_inheritance(row, schedules, groups, macros):
    row["PAR_SetTempH"] = 23
    assert room_temperatures(row, schedules, groups, macros)["matches_macrozone_default"] is True


def test_cooling_uses_c_side_and_its_enabled_flag(row, schedules, groups, macros):
    groups[0]["mode"] = 1
    result = room_temperatures(row, schedules, groups, macros)
    assert result["effective_setpoint"] == 24.5
    assert result["target_source"] == "default"


def test_auto_uses_executive_season(row, schedules, groups, macros):
    groups[0].update(mode=2, executive_season=1)
    assert room_temperatures(row, schedules, groups, macros)["default_setpoint"] == 24.5


def test_override_precedes_schedule(row, schedules, groups, macros):
    row.update(RTU_SpoRemain=3600, PAR_SpoSetTemp=26)
    result = room_temperatures(row, schedules, groups, macros)
    assert result["effective_setpoint"] == 26
    assert result["target_source"] == "override"


def test_stale_side_override_does_not_override_single_mode(row, schedules, groups, macros):
    row.update(RTU_SpoRemainH=3600, PAR_SpoSetTempH=26)
    assert room_temperatures(row, schedules, groups, macros)["effective_setpoint"] == 23


@pytest.mark.parametrize("season,target", [(0, 21), (1, 25)])
def test_dual_schedule_uses_executive_side(row, schedules, groups, macros, season, target):
    groups[0].update(mode=2, executive_season=season, auto_mode_style=2)
    row["PAR_SchedOnC"] = True
    schedules[1].update(CFG_Type=3, RTU_SetPointH=21, RTU_SetPointC=25)
    assert room_temperatures(row, schedules, groups, macros)["effective_setpoint"] == target


def test_on_off_schedule_uses_default_temperature(row, schedules, groups, macros):
    schedules[1]["CFG_Type"] = 0
    assert room_temperatures(row, schedules, groups, macros)["effective_setpoint"] == 27


@pytest.mark.parametrize("missing", [False, True])
def test_unknown_schedule_target_does_not_display_default(row, schedules, groups, macros, missing):
    if missing:
        schedules.clear()
    else:
        schedules[1]["RTU_SetPoint"] = -3276.8
    assert room_temperatures(row, schedules, groups, macros)["effective_setpoint"] is None


@pytest.mark.parametrize("value", [None, -3276.8, float("nan"), float("inf"), True, "bad"])
def test_invalid_temperatures_are_unavailable(value):
    assert valid_temperature(value) is None


def test_unknown_season_disables_default_controls(row, schedules, macros):
    assert room_temperatures(row, schedules, {}, macros)["effective_setpoint"] is None
    assert macrozone_temperatures({"CFG_IdxGRP": 0}, {})["season"] is None
