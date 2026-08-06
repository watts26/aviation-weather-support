from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from aviation_weather_support.models import MetarObservation
from aviation_weather_support.operational_rules import (
    ConcernLevel,
    DataConfidence,
    OfficialFlightCategory,
    RuleClassification,
    assess_current_conditions,
    assess_flight_category,
    parse_present_weather,
    parse_visibility_miles,
)


EVALUATED_AT = datetime(2026, 7, 29, 20, 0, tzinfo=timezone.utc)


def observation(**weather) -> MetarObservation:
    data = {
        "icaoId": "KATL",
        "reportTime": "2026-07-29T20:00:00Z",
        "obsTime": int((EVALUATED_AT - timedelta(minutes=10)).timestamp()),
        "rawOb": "METAR KATL 291950Z AUTO 00000KT 10SM CLR RMK AO2",
        "visib": 10,
        "clouds": [],
        "wspd": 0,
        "wxString": None,
    }
    data.update(weather)
    return MetarObservation.model_validate(data)


def hazards(assessment):
    return {hazard.id: hazard for hazard in assessment.hazards}


@pytest.mark.parametrize(
    ("ceiling", "expected"),
    [
        (3001, OfficialFlightCategory.VFR),
        (3000, OfficialFlightCategory.MVFR),
        (1000, OfficialFlightCategory.MVFR),
        (999, OfficialFlightCategory.IFR),
        (500, OfficialFlightCategory.IFR),
        (499, OfficialFlightCategory.LIFR),
    ],
)
def test_official_ceiling_boundaries(ceiling, expected):
    result = assess_flight_category(
        observation(clouds=[{"cover": "BKN", "base": ceiling}])
    )
    assert result.category == expected
    assert result.rule_classification == RuleClassification.OFFICIAL


@pytest.mark.parametrize(
    ("visibility", "expected"),
    [
        (5.01, OfficialFlightCategory.VFR),
        (5, OfficialFlightCategory.MVFR),
        (3, OfficialFlightCategory.MVFR),
        (2.99, OfficialFlightCategory.IFR),
        (1, OfficialFlightCategory.IFR),
        (0.99, OfficialFlightCategory.LIFR),
    ],
)
def test_official_visibility_boundaries(visibility, expected):
    result = assess_flight_category(observation(visib=visibility))
    assert result.category == expected


def test_worse_ceiling_or_visibility_category_wins():
    result = assess_flight_category(
        observation(visib=0.5, clouds=[{"cover": "BKN", "base": 2000}])
    )
    assert result.category == OfficialFlightCategory.LIFR


@pytest.mark.parametrize(
    "clouds",
    [[], [{"cover": "CLR"}], [{"cover": "SKC"}], [{"cover": "SCT", "base": 500}]],
)
def test_valid_no_ceiling_observations_are_not_missing(clouds):
    result = assess_flight_category(observation(clouds=clouds))
    assert result.category == OfficialFlightCategory.VFR
    assert result.data_complete is True
    assert result.observed_value["ceiling_ft_agl"] is None


def test_missing_clouds_make_category_unavailable_without_lifr_dimension():
    result = assess_flight_category(observation(clouds=None, visib=10))
    assert result.category == OfficialFlightCategory.UNAVAILABLE
    assert result.data_complete is False


def test_known_lifr_dimension_remains_lifr_when_other_dimension_is_missing():
    result = assess_flight_category(observation(clouds=None, visib=0.5))
    assert result.category == OfficialFlightCategory.LIFR
    assert result.data_complete is False


def test_missing_ceiling_base_and_malformed_visibility_are_unavailable():
    result = assess_flight_category(
        observation(visib="unknown", clouds=[{"cover": "OVC"}])
    )
    assert result.category == OfficialFlightCategory.UNAVAILABLE
    assert result.data_complete is False


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("10+", 10.0), ("1/2", 0.5), ("1 1/2", 1.5), ("unknown", None)],
)
def test_visibility_parser_handles_markers_fractions_and_malformed_data(raw, expected):
    assert parse_visibility_miles(raw) == expected


@pytest.mark.parametrize("weather", [None, "", "   "])
def test_absent_decoded_weather_is_valid_normal_absence(weather):
    result = assess_current_conditions(
        observation(wxString=weather), evaluated_at=EVALUATED_AT
    )
    by_id = hazards(result)
    assert by_id["thunderstorm"].concern_level == ConcernLevel.NOT_TRIGGERED
    assert by_id["freezing_precipitation"].concern_level == ConcernLevel.NOT_TRIGGERED


def test_valid_weather_without_listed_tokens_is_not_triggered():
    result = assess_current_conditions(
        observation(wxString="-RA BR"), evaluated_at=EVALUATED_AT
    )
    by_id = hazards(result)
    assert by_id["thunderstorm"].concern_level == ConcernLevel.NOT_TRIGGERED
    assert by_id["freezing_precipitation"].concern_level == ConcernLevel.NOT_TRIGGERED


@pytest.mark.parametrize("weather", ["TS", "TSRA", "+TSRA"])
def test_thunderstorm_at_station_is_high_attention(weather):
    flag = hazards(
        assess_current_conditions(
            observation(wxString=weather), evaluated_at=EVALUATED_AT
        )
    )["thunderstorm"]
    assert flag.concern_level == ConcernLevel.HIGH_ATTENTION


def test_vicinity_thunderstorm_is_attention():
    flag = hazards(
        assess_current_conditions(
            observation(wxString="VCTS"), evaluated_at=EVALUATED_AT
        )
    )["thunderstorm"]
    assert flag.concern_level == ConcernLevel.ATTENTION


def test_malformed_nonempty_weather_makes_weather_hazards_unavailable():
    result = assess_current_conditions(
        observation(wxString="NOT-WEATHER"), evaluated_at=EVALUATED_AT
    )
    by_id = hazards(result)
    assert by_id["thunderstorm"].concern_level == ConcernLevel.UNAVAILABLE
    assert by_id["freezing_precipitation"].concern_level == ConcernLevel.UNAVAILABLE
    assert parse_present_weather("NOT-WEATHER") is None


def test_non_string_weather_is_rejected_by_validation():
    with pytest.raises(ValidationError):
        observation(wxString={"TS": True})


@pytest.mark.parametrize("cloud_type", ["CB", "TCU"])
def test_convective_cloud_types_are_attention(cloud_type):
    flag = hazards(
        assess_current_conditions(
            observation(
                clouds=[{"cover": "SCT", "base": 3000, "type": cloud_type}]
            ),
            evaluated_at=EVALUATED_AT,
        )
    )["convective_cloud"]
    assert flag.concern_level == ConcernLevel.ATTENTION


def test_missing_and_malformed_convective_cloud_data_are_unavailable():
    missing = hazards(
        assess_current_conditions(
            observation(clouds=None), evaluated_at=EVALUATED_AT
        )
    )["convective_cloud"]
    malformed = hazards(
        assess_current_conditions(
            observation(clouds=[{"cover": "SCT", "type": "BAD"}]),
            evaluated_at=EVALUATED_AT,
        )
    )["convective_cloud"]
    assert missing.concern_level == ConcernLevel.UNAVAILABLE
    assert malformed.concern_level == ConcernLevel.UNAVAILABLE


@pytest.mark.parametrize("weather", ["-FZDZ", "FZDZ", "FZRA", "+FZRA"])
def test_freezing_precipitation_at_any_intensity_is_high_attention(weather):
    flag = hazards(
        assess_current_conditions(
            observation(wxString=weather), evaluated_at=EVALUATED_AT
        )
    )["freezing_precipitation"]
    assert flag.concern_level == ConcernLevel.HIGH_ATTENTION


def test_ao1_is_limited_confidence_not_unavailable():
    flag = hazards(
        assess_current_conditions(
            observation(rawOb="METAR KATL 291950Z AUTO 00000KT 10SM CLR RMK AO1"),
            evaluated_at=EVALUATED_AT,
        )
    )["freezing_precipitation"]
    assert flag.concern_level == ConcernLevel.NOT_TRIGGERED
    assert flag.data_confidence == DataConfidence.LIMITED
    assert flag.data_complete is True


def test_explicit_freezing_precipitation_triggers_under_ao1():
    flag = hazards(
        assess_current_conditions(
            observation(
                rawOb="METAR KATL 291950Z AUTO 00000KT 10SM FZRA CLR RMK AO1",
                wxString="FZRA",
            ),
            evaluated_at=EVALUATED_AT,
        )
    )["freezing_precipitation"]
    assert flag.concern_level == ConcernLevel.HIGH_ATTENTION
    assert flag.data_confidence == DataConfidence.LIMITED


@pytest.mark.parametrize(
    ("wind", "gust", "expected"),
    [
        (24.99, None, ConcernLevel.NOT_TRIGGERED),
        (25, None, ConcernLevel.ATTENTION),
        (29.99, None, ConcernLevel.ATTENTION),
        (30, None, ConcernLevel.HIGH_ATTENTION),
        (5, 24.99, ConcernLevel.NOT_TRIGGERED),
        (5, 25, ConcernLevel.ATTENTION),
        (5, 49.99, ConcernLevel.ATTENTION),
        (5, 50, ConcernLevel.HIGH_ATTENTION),
    ],
)
def test_wind_boundaries_are_project_defined(wind, gust, expected):
    flag = hazards(
        assess_current_conditions(
            observation(wspd=wind, wgst=gust), evaluated_at=EVALUATED_AT
        )
    )["wind"]
    assert flag.concern_level == expected
    assert flag.rule_classification == RuleClassification.PROJECT_DEFINED
    assert "universal" in flag.operational_judgment


def test_missing_sustained_wind_is_unavailable_but_missing_gust_is_not():
    missing_speed = hazards(
        assess_current_conditions(
            observation(wspd=None, wgst=30), evaluated_at=EVALUATED_AT
        )
    )["wind"]
    missing_gust = hazards(
        assess_current_conditions(
            observation(wspd=10, wgst=None), evaluated_at=EVALUATED_AT
        )
    )["wind"]
    assert missing_speed.concern_level == ConcernLevel.UNAVAILABLE
    assert missing_gust.concern_level == ConcernLevel.NOT_TRIGGERED


@pytest.mark.parametrize("field", ["wspd", "wgst"])
def test_malformed_wind_is_rejected(field):
    with pytest.raises(ValidationError):
        observation(**{field: "bad"})


@pytest.mark.parametrize(
    ("offset", "expected"),
    [
        (timedelta(minutes=75), ConcernLevel.NOT_TRIGGERED),
        (timedelta(minutes=75, seconds=1), ConcernLevel.ATTENTION),
        (timedelta(minutes=-5), ConcernLevel.NOT_TRIGGERED),
        (timedelta(minutes=-5, seconds=-1), ConcernLevel.UNAVAILABLE),
    ],
)
def test_freshness_boundaries_are_project_defined(offset, expected):
    obs_time = EVALUATED_AT - offset
    flag = hazards(
        assess_current_conditions(
            observation(obsTime=obs_time.isoformat()), evaluated_at=EVALUATED_AT
        )
    )["observation_freshness"]
    assert flag.concern_level == expected
    assert flag.rule_classification == RuleClassification.PROJECT_DEFINED


@pytest.mark.parametrize("obs_time", [None, "not-a-time"])
def test_missing_or_malformed_observation_time_is_unavailable(obs_time):
    flag = hazards(
        assess_current_conditions(
            observation(obsTime=obs_time), evaluated_at=EVALUATED_AT
        )
    )["observation_freshness"]
    assert flag.concern_level == ConcernLevel.UNAVAILABLE


def test_freshness_uses_obs_time_not_report_time():
    flag = hazards(
        assess_current_conditions(
            observation(
                obsTime=(EVALUATED_AT - timedelta(minutes=76)).timestamp(),
                reportTime=EVALUATED_AT.isoformat(),
            ),
            evaluated_at=EVALUATED_AT,
        )
    )["observation_freshness"]
    assert flag.concern_level == ConcernLevel.ATTENTION


def test_overall_concern_is_highest_active_project_concern():
    high = assess_current_conditions(
        observation(wxString="TS", wspd=25), evaluated_at=EVALUATED_AT
    )
    attention = assess_current_conditions(
        observation(wspd=25), evaluated_at=EVALUATED_AT
    )
    none = assess_current_conditions(observation(), evaluated_at=EVALUATED_AT)
    assert high.overall_concern == ConcernLevel.HIGH_ATTENTION
    assert attention.overall_concern == ConcernLevel.ATTENTION
    assert none.overall_concern == ConcernLevel.NOT_TRIGGERED


def test_unavailable_hazards_do_not_hide_known_attention():
    result = assess_current_conditions(
        observation(clouds=None, wspd=25, obsTime=None), evaluated_at=EVALUATED_AT
    )
    assert result.overall_concern == ConcernLevel.ATTENTION
    assert result.data_complete is False


def test_all_unavailable_project_hazards_make_overall_unavailable():
    result = assess_current_conditions(
        observation(
            wxString="BAD-TOKEN",
            clouds=None,
            wspd=None,
            obsTime=None,
        ),
        evaluated_at=EVALUATED_AT,
    )
    assert result.overall_concern == ConcernLevel.UNAVAILABLE


def test_official_category_does_not_raise_project_concern():
    result = assess_current_conditions(
        observation(visib=0.5, clouds=[{"cover": "OVC", "base": 300}]),
        evaluated_at=EVALUATED_AT,
    )
    assert result.flight_category.category == OfficialFlightCategory.LIFR
    assert result.overall_concern == ConcernLevel.NOT_TRIGGERED
