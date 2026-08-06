import json
from datetime import datetime, timezone

import pytest

from aviation_weather_support.dashboard import (
    celsius_to_fahrenheit,
    cloud_rows,
    format_altimeter,
    format_hazard_observation,
    format_speed,
    format_temperature,
    format_visibility,
    format_wind,
    hpa_to_inhg,
    json_text,
    knots_to_mph,
    statute_miles_to_km,
)
from aviation_weather_support.models import validate_metar_observation
from aviation_weather_support.operational_rules import assess_current_conditions


def test_celsius_to_fahrenheit_handles_values_zero_and_missing_data():
    assert celsius_to_fahrenheit(22) == pytest.approx(71.6)
    assert celsius_to_fahrenheit(0) == pytest.approx(32)
    assert celsius_to_fahrenheit(None) is None


def test_knots_to_mph_handles_values_zero_and_missing_data():
    assert knots_to_mph(12) == pytest.approx(13.809353376)
    assert knots_to_mph(0) == pytest.approx(0)
    assert knots_to_mph(None) is None


def test_statute_miles_to_km_handles_values_markers_and_missing_data():
    assert statute_miles_to_km(10) == pytest.approx(16.09344)
    assert statute_miles_to_km("10+") == pytest.approx(16.09344)
    assert statute_miles_to_km(0) == pytest.approx(0)
    assert statute_miles_to_km(None) is None


def test_hpa_to_inhg_handles_values_zero_and_missing_data():
    assert hpa_to_inhg(1013.2) == pytest.approx(29.91997, rel=1e-5)
    assert hpa_to_inhg(0) == pytest.approx(0)
    assert hpa_to_inhg(None) is None


def test_dashboard_formatting_keeps_original_units_first():
    assert format_temperature(22) == "22.0 °C / 71.6 °F"
    assert format_speed(12) == "12 kt / 13.8 mph"
    assert format_visibility(10) == "10 mi / 16.1 km"
    assert format_altimeter(1013.2) == "1013.2 hPa / 29.92 inHg"
    assert format_wind(320, 9) == "320° at 9 kt / 10.4 mph"
    assert format_temperature(None) == "Not reported"
    assert format_wind(None, None) == "Not reported"


def test_cloud_rows_are_plain_dashboard_records():
    observation = validate_metar_observation(
        [
            {
                "icaoId": "KATL",
                "reportTime": "2026-07-29T20:00:00Z",
                "rawOb": "METAR KATL 292000Z AUTO",
                "clouds": [{"cover": "BKN", "base": 2500}],
            }
        ]
    )

    assert cloud_rows(observation) == [{"cover": "BKN", "base": 2500}]


def test_json_text_is_readable_and_round_trips():
    data = {"icao_id": "KATL", "temperature_c": 30.6}

    text = json_text(data)

    assert text.endswith("\n")
    assert json.loads(text) == data


def test_operational_hazard_observations_are_readable():
    observation = validate_metar_observation(
        [
            {
                "icaoId": "KATL",
                "reportTime": "2026-07-29T20:00:00Z",
                "obsTime": 1785355200,
                "rawOb": "METAR KATL 292000Z 18015G20KT 4SM BKN020",
                "visib": 4,
                "wspd": 15,
                "wgst": 20,
                "clouds": [{"cover": "BKN", "base": 2000}],
            }
        ]
    )
    hazard_by_id = {
        hazard.id: hazard
        for hazard in assess_current_conditions(
            observation,
            evaluated_at=datetime(2026, 7, 29, 20, 0, tzinfo=timezone.utc),
        ).hazards
    }

    assert format_hazard_observation(hazard_by_id["wind"]) == (
        "15 kt sustained / 20 kt gust"
    )
