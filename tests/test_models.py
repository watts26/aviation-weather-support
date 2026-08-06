import json
from copy import deepcopy
from pathlib import Path

import pytest

from aviation_weather_support.models import (
    MetarDataValidationError,
    validate_metar_observation,
)


FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(name: str):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_successful_katl_fixture_is_validated():
    observation = validate_metar_observation(
        load_fixture("metar-katl-success.json")
    )

    assert observation.icao_id == "KATL"
    assert observation.observation_time == 1785354720
    assert observation.receipt_time == "2026-07-29T19:57:49.891Z"
    assert observation.report_time == "2026-07-29T20:00:00.000Z"
    assert observation.raw_metar.startswith("METAR KATL")
    assert observation.wind_speed_kt == 9
    assert observation.model_extra is None


def test_optional_weather_fields_may_be_absent():
    observation = validate_metar_observation(
        [
            {
                "icaoId": "KATL",
                "reportTime": "2026-07-29T20:00:00Z",
                "rawOb": "METAR KATL 292000Z AUTO",
            }
        ]
    )

    processed = observation.to_processed_dict()
    assert processed["temperature_c"] is None
    assert processed["wind_gust_kt"] is None
    assert processed["clouds"] is None


def test_missing_required_data_is_rejected():
    data = deepcopy(load_fixture("metar-katl-success.json"))
    del data[0]["rawOb"]

    with pytest.raises(MetarDataValidationError, match=r"rawOb: Field required"):
        validate_metar_observation(data)


def test_invalid_weather_field_type_is_rejected():
    data = deepcopy(load_fixture("metar-katl-success.json"))
    data[0]["wspd"] = {"unexpected": "object"}

    with pytest.raises(MetarDataValidationError, match=r"at wspd:"):
        validate_metar_observation(data)


def test_invalid_fixture_has_clear_field_location_and_message():
    with pytest.raises(MetarDataValidationError) as exc_info:
        validate_metar_observation(load_fixture("metar-invalid.json"))

    assert str(exc_info.value) == (
        "METAR data could not be used at reportTime: "
        "Value error, must be a valid ISO 8601 timestamp"
    )


def test_processed_output_mapping_matches_practicum_four_fields():
    observation = validate_metar_observation(
        load_fixture("metar-katl-success.json")
    )

    assert observation.to_processed_dict() == {
        "icao_id": "KATL",
        "airport_name": "Atlanta/Hartsfield-Jackson Intl, GA, US",
        "observation_time": 1785354720,
        "receipt_time": "2026-07-29T19:57:49.891Z",
        "report_time": "2026-07-29T20:00:00.000Z",
        "raw_metar": (
            "METAR KATL 291952Z 32009KT 9SM SCT160 BKN200 BKN250 31/23 "
            "A2985 RMK AO2 SLP096 T03060228 $"
        ),
        "temperature_c": 30.6,
        "dewpoint_c": 22.8,
        "wind_direction_deg": 320,
        "wind_speed_kt": 9,
        "wind_gust_kt": None,
        "visibility_miles": 9,
        "weather_string": None,
        "altimeter_hpa": 1010.9,
        "flight_category": "VFR",
        "clouds": [
            {"cover": "SCT", "base": 16000, "cloud_type": None},
            {"cover": "BKN", "base": 20000, "cloud_type": None},
            {"cover": "BKN", "base": 25000, "cloud_type": None},
        ],
    }


def test_structured_weather_and_cloud_type_are_retained():
    observation = validate_metar_observation(
        [
            {
                "icaoId": "KATL",
                "reportTime": "2026-07-29T20:00:00Z",
                "rawOb": "METAR KATL 292000Z TSRA SCT030CB",
                "wxString": "TSRA",
                "clouds": [{"cover": "SCT", "base": 3000, "type": "CB"}],
            }
        ]
    )

    assert observation.weather_string == "TSRA"
    assert observation.clouds[0].cloud_type == "CB"
