import pytest

from aviation_weather_support.models import MetarObservation
from aviation_weather_support.operational import (
    INFORMATIONAL_DISCLAIMER,
    FlagStatus,
    assess_current_conditions,
    parse_visibility_miles,
)


def observation(**weather) -> MetarObservation:
    data = {
        "icaoId": "KATL",
        "reportTime": "2026-07-29T20:00:00Z",
        "rawOb": "METAR KATL 292000Z AUTO",
    }
    data.update(weather)
    return MetarObservation.model_validate(data)


def statuses(assessment) -> dict[str, FlagStatus]:
    return {flag.id: flag.status for flag in assessment.flags}


def test_normal_current_conditions_have_three_normal_flags():
    assessment = assess_current_conditions(
        observation(
            visib=10,
            clouds=[{"cover": "SCT", "base": 4000}],
            wspd=9,
        )
    )

    assert assessment.overall_status == FlagStatus.NORMAL
    assert assessment.data_complete is True
    assert statuses(assessment) == {
        "visibility": FlagStatus.NORMAL,
        "ceiling": FlagStatus.NORMAL,
        "wind": FlagStatus.NORMAL,
    }
    assert assessment.disclaimer == INFORMATIONAL_DISCLAIMER


def test_caution_current_conditions_have_three_caution_flags():
    assessment = assess_current_conditions(
        observation(
            visib=4,
            clouds=[{"cover": "BKN", "base": 2000}],
            wspd=15,
            wgst=20,
        )
    )

    assert assessment.overall_status == FlagStatus.CAUTION
    assert statuses(assessment) == {
        "visibility": FlagStatus.CAUTION,
        "ceiling": FlagStatus.CAUTION,
        "wind": FlagStatus.CAUTION,
    }


def test_severe_current_conditions_have_three_severe_flags():
    assessment = assess_current_conditions(
        observation(
            visib=2,
            clouds=[{"cover": "OVC", "base": 900}],
            wspd=25,
            wgst=30,
        )
    )

    assert assessment.overall_status == FlagStatus.SEVERE
    assert statuses(assessment) == {
        "visibility": FlagStatus.SEVERE,
        "ceiling": FlagStatus.SEVERE,
        "wind": FlagStatus.SEVERE,
    }


def test_all_missing_data_returns_unavailable_assessment():
    assessment = assess_current_conditions(observation())

    assert assessment.overall_status == FlagStatus.UNAVAILABLE
    assert assessment.data_complete is False
    assert set(statuses(assessment).values()) == {FlagStatus.UNAVAILABLE}


def test_partial_missing_data_does_not_hide_known_severity():
    assessment = assess_current_conditions(
        observation(visib=2, clouds=None, wspd=8)
    )

    assert assessment.overall_status == FlagStatus.SEVERE
    assert assessment.data_complete is False
    assert statuses(assessment) == {
        "visibility": FlagStatus.SEVERE,
        "ceiling": FlagStatus.UNAVAILABLE,
        "wind": FlagStatus.NORMAL,
    }


@pytest.mark.parametrize(
    ("visibility", "expected"),
    [
        (5, FlagStatus.NORMAL),
        (3, FlagStatus.CAUTION),
        (2.99, FlagStatus.SEVERE),
    ],
)
def test_visibility_threshold_boundaries(visibility, expected):
    assessment = assess_current_conditions(
        observation(visib=visibility, clouds=[], wspd=0)
    )

    assert statuses(assessment)["visibility"] == expected


@pytest.mark.parametrize(
    ("ceiling", "expected"),
    [
        (3000, FlagStatus.NORMAL),
        (1000, FlagStatus.CAUTION),
        (999, FlagStatus.SEVERE),
    ],
)
def test_ceiling_threshold_boundaries(ceiling, expected):
    assessment = assess_current_conditions(
        observation(
            visib=10,
            clouds=[{"cover": "BKN", "base": ceiling}],
            wspd=0,
        )
    )

    assert statuses(assessment)["ceiling"] == expected


@pytest.mark.parametrize(
    ("wind_fields", "expected"),
    [
        ({"wspd": 14.99}, FlagStatus.NORMAL),
        ({"wspd": 15}, FlagStatus.CAUTION),
        ({"wspd": 25}, FlagStatus.SEVERE),
        ({"wspd": 5, "wgst": 20}, FlagStatus.CAUTION),
        ({"wspd": 5, "wgst": 30}, FlagStatus.SEVERE),
    ],
)
def test_wind_threshold_boundaries(wind_fields, expected):
    assessment = assess_current_conditions(
        observation(visib=10, clouds=[], **wind_fields)
    )

    assert statuses(assessment)["wind"] == expected


def test_ceiling_layer_without_base_is_unavailable():
    assessment = assess_current_conditions(
        observation(visib=10, clouds=[{"cover": "VV"}], wspd=5)
    )

    assert statuses(assessment)["ceiling"] == FlagStatus.UNAVAILABLE
    assert assessment.data_complete is False


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("10+", 10.0), ("1/2", 0.5), ("1 1/2", 1.5), ("unknown", None)],
)
def test_visibility_parser_handles_api_markers_and_fractions(raw, expected):
    assert parse_visibility_miles(raw) == expected
