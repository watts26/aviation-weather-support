import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from aviation_weather_support.dashboard import (
    celsius_to_fahrenheit,
    clear_dashboard_state,
    cloud_rows,
    find_hazard,
    format_altimeter,
    format_hazard_observation,
    format_speed,
    format_temperature,
    format_visibility,
    format_wind,
    hazard_table_rows,
    hpa_to_inhg,
    json_text,
    knots_to_mph,
    statute_miles_to_km,
    summary_fields,
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


def test_dashboard_displays_variable_wind_and_other_decoded_weather():
    observation = validate_metar_observation(
        [
            {
                "icaoId": "KRDU",
                "name": "Raleigh-Durham International Airport",
                "reportTime": "2026-08-06T18:00:00Z",
                "obsTime": 1786039200,
                "rawOb": "METAR KRDU 061800Z VRB04KT 10SM SCT050 26/18 A3011",
                "temp": 26,
                "dewp": 18,
                "wdir": "VRB",
                "wspd": 4,
                "visib": 10,
                "altim": 1019.6,
                "fltCat": "VFR",
                "clouds": [{"cover": "SCT", "base": 5000}],
            }
        ]
    )

    assert format_wind(
        observation.wind_direction_deg, observation.wind_speed_kt
    ) == "Variable at 4 kt / 4.6 mph"
    assert format_temperature(observation.temperature_c) == "26.0 °C / 78.8 °F"
    assert format_visibility(observation.visibility_miles) == "10 mi / 16.1 km"
    assert cloud_rows(observation) == [{"cover": "SCT", "base": 5000}]


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


def test_clear_dashboard_state_clears_only_input_and_displayed_result():
    state = {
        "airport_input": "KATL",
        "metar_result": object(),
        "saved_file_reference": "data/processed/existing.json",
    }

    clear_dashboard_state(state)

    assert state == {
        "airport_input": "",
        "saved_file_reference": "data/processed/existing.json",
    }


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


def test_summary_fields_prioritize_station_time_age_category_and_concern():
    observation = validate_metar_observation(
        [
            {
                "icaoId": "KATL",
                "name": "Hartsfield-Jackson Atlanta International Airport",
                "reportTime": "2026-07-29T20:00:00Z",
                "obsTime": 1785355200,
                "rawOb": "METAR KATL 292000Z 18015KT 10SM SCT040",
                "visib": 10,
                "wspd": 15,
                "clouds": [{"cover": "SCT", "base": 4000}],
            }
        ]
    )
    assessment = assess_current_conditions(
        observation,
        evaluated_at=datetime(2026, 7, 29, 20, 30, tzinfo=timezone.utc),
    )
    result = type(
        "DashboardResult",
        (),
        {"observation": observation, "operational_assessment": assessment},
    )()

    assert summary_fields(result) == (
        (
            "Airport / station",
            "Hartsfield-Jackson Atlanta International Airport (KATL)",
        ),
        ("Observation time", "2026-07-29T20:00:00+00:00"),
        ("Observation age", "30 minutes old"),
        ("Official flight category", "VFR"),
        ("Overall concern level", "No listed hazard trigger"),
    )


def test_summary_fields_make_unavailable_observation_time_and_age_clear():
    observation = validate_metar_observation(
        [
            {
                "icaoId": "KATL",
                "reportTime": "2026-07-29T20:00:00Z",
                "rawOb": "METAR KATL 292000Z AUTO",
            }
        ]
    )
    assessment = assess_current_conditions(
        observation,
        evaluated_at=datetime(2026, 7, 29, 20, 30, tzinfo=timezone.utc),
    )
    result = type(
        "DashboardResult",
        (),
        {"observation": observation, "operational_assessment": assessment},
    )()

    fields = dict(summary_fields(result))

    assert fields["Observation time"] == "Unavailable"
    assert fields["Observation age"] == "Time unavailable"


def test_hazard_table_rows_are_compact_and_preserve_assessment_values():
    observation = validate_metar_observation(
        [
            {
                "icaoId": "KATL",
                "reportTime": "2026-07-29T20:00:00Z",
                "obsTime": 1785355200,
                "rawOb": "METAR KATL 292000Z 18015KT 10SM SCT040",
                "visib": 10,
                "wspd": 15,
                "clouds": [{"cover": "SCT", "base": 4000}],
            }
        ]
    )
    assessment = assess_current_conditions(
        observation,
        evaluated_at=datetime(2026, 7, 29, 20, 0, tzinfo=timezone.utc),
    )
    rows = hazard_table_rows(assessment)
    wind = find_hazard(assessment, "wind")

    assert wind is not None
    assert tuple(rows[0]) == (
        "Hazard",
        "Concern level",
        "Observed value",
        "Trigger",
    )
    assert rows[3] == {
        "Hazard": wind.label,
        "Concern level": wind.display_label,
        "Observed value": format_hazard_observation(wind),
        "Trigger": wind.trigger,
    }
    assert len(rows) == len(assessment.hazards)


def test_dashboard_result_section_order_prioritizes_summary_and_context_last():
    source = (
        Path(__file__).parents[1]
        / "src"
        / "aviation_weather_support"
        / "dashboard.py"
    ).read_text(encoding="utf-8")

    result_renderer = source.split("def render_result", maxsplit=1)[1]
    assert result_renderer.index("render_summary(result)") < result_renderer.index(
        "render_operational_assessment(result.operational_assessment)"
    )
    assert result_renderer.index(
        "render_operational_assessment(result.operational_assessment)"
    ) < result_renderer.index('st.subheader("Detailed weather")')
    assert result_renderer.index('st.subheader("Detailed weather")') < (
        result_renderer.index(
            "render_sources_limitations_disclaimer("
            "result.operational_assessment)"
        )
    )


def test_dashboard_styles_do_not_add_side_borders_to_section_headings():
    source = (
        Path(__file__).parents[1]
        / "src"
        / "aviation_weather_support"
        / "dashboard.py"
    ).read_text(encoding="utf-8")
    styles = source.split('AUBURN_STYLES = f"""', maxsplit=1)[1].split(
        '"""', maxsplit=1
    )[0]

    assert "h2, h3 {{" not in styles


def test_summary_cards_wrap_values_and_give_long_fields_more_room():
    source = (
        Path(__file__).parents[1]
        / "src"
        / "aviation_weather_support"
        / "dashboard.py"
    ).read_text(encoding="utf-8")
    styles = source.split('AUBURN_STYLES = f"""', maxsplit=1)[1].split(
        '"""', maxsplit=1
    )[0]

    assert 'div[data-testid="stMetricValue"] p' in styles
    assert "overflow: visible !important;" in styles
    assert "overflow-wrap: anywhere !important;" in styles
    assert "text-overflow: clip !important;" in styles
    assert "white-space: normal !important;" in styles
    assert "first_row = st.columns((2, 1.35, 1))" in source


def test_dashboard_controls_include_guidance_reset_and_json_downloads():
    source = (
        Path(__file__).parents[1]
        / "src"
        / "aviation_weather_support"
        / "dashboard.py"
    ).read_text(encoding="utf-8")

    assert (
        "Enter a four-letter ICAO airport identifier, such as KATL or KJFK."
        in source
    )
    assert 'if "airport_input" not in st.session_state:' in source
    assert 'st.session_state["airport_input"] = "KATL"' in source
    assert 'value="KATL"' not in source
    assert '"Clear / Reset", on_click=clear_dashboard_state' in source
    assert '"Download raw JSON"' in source
    assert '"Download processed JSON"' in source
    assert "Download PDF" not in source
