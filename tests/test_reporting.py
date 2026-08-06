import json
from pathlib import Path

import pytest

from aviation_weather_support.operational_rules import ConcernLevel
from aviation_weather_support.reporting import (
    DEFAULT_REPORT_EVALUATED_AT,
    DEFAULT_REPORT_STATION,
    OfflineReportDataError,
    build_report_header,
    fixture_resource_for_station,
    load_offline_report_data,
    load_report_render_data,
    parse_report_evaluated_at,
    report_template_resource,
)


PROJECT_ROOT = Path(__file__).parents[1]


def test_quarto_parameter_cell_uses_reproducible_defaults():
    report_source = report_template_resource().read_text(encoding="utf-8")

    assert "#| tags: [parameters]" in report_source
    assert f'station = "{DEFAULT_REPORT_STATION}"' in report_source
    assert f'evaluated_at = "{DEFAULT_REPORT_EVALUATED_AT}"' in report_source
    front_matter = report_source.split("---", maxsplit=2)[1]
    assert 'title: "Aviation Weather Operational Assessment"' in front_matter
    assert "date:" not in front_matter


def test_quarto_header_and_sections_prioritize_validated_assessment_metadata():
    report_source = report_template_resource().read_text(encoding="utf-8")

    header_position = report_source.index("**Airport / Station:**")
    interpretation_position = report_source.index("## Interpretation")
    hazards_position = report_source.index("## Project-defined hazard screening")
    supporting_position = report_source.index("## Supporting data and provenance")
    sources_position = report_source.index("## Sources")
    assert "`{header.station}`" in report_source
    assert "{header.observation_time}" in report_source
    assert "{header.evaluated_at}" in report_source
    assert header_position < interpretation_position < hazards_position
    assert hazards_position < supporting_position < sources_position


def test_default_katl_parameters_load_committed_fixture():
    result = load_offline_report_data(
        PROJECT_ROOT,
        station=DEFAULT_REPORT_STATION,
        evaluated_at=DEFAULT_REPORT_EVALUATED_AT,
    )

    assert result.station == "KATL"
    assert result.fixture_reference == (
        "package:aviation_weather_support/resources/fixtures/"
        "metar-katl-success.json"
    )
    assert result.observation.icao_id == "KATL"


def test_default_report_header_uses_fixed_evaluation_metadata():
    report_data = load_report_render_data(
        PROJECT_ROOT,
        station=DEFAULT_REPORT_STATION,
        evaluated_at=DEFAULT_REPORT_EVALUATED_AT,
    )

    header = build_report_header(report_data)

    assert header.station == "KATL"
    assert header.report_date == "July 29, 2026"
    assert header.observation_time == "July 29, 2026 at 7:52 PM UTC"
    assert header.evaluated_at == "July 29, 2026 at 8:00 PM UTC"


def test_fixture_resource_is_derived_from_normalized_station():
    assert fixture_resource_for_station(" katl ").name == (
        "metar-katl-success.json"
    )


def test_fixture_station_must_match_requested_station(tmp_path, monkeypatch):
    fixture_path = tmp_path / "metar-kauo-success.json"
    katl_data = json.loads(
        (PROJECT_ROOT / "tests" / "fixtures" / "metar-katl-success.json").read_text(
            encoding="utf-8"
        )
    )
    fixture_path.write_text(
        json.dumps(katl_data), encoding="utf-8"
    )
    monkeypatch.setattr(
        "aviation_weather_support.reporting.fixture_resource_for_station",
        lambda station: fixture_path,
    )

    with pytest.raises(OfflineReportDataError, match="requested KAUO.*contains KATL"):
        load_offline_report_data(
            tmp_path,
            station="KAUO",
            evaluated_at=DEFAULT_REPORT_EVALUATED_AT,
        )


def test_missing_fixture_requires_a_committed_offline_fixture(tmp_path):
    with pytest.raises(
        OfflineReportDataError,
        match=(
            "No committed METAR fixture was found for KAUO.*"
            "Report rendering is offline"
        ),
    ):
        load_offline_report_data(
            tmp_path,
            station="KAUO",
            evaluated_at=DEFAULT_REPORT_EVALUATED_AT,
        )


@pytest.mark.parametrize("value", ["not-a-time", "2026-07-29T20:00:00", None])
def test_invalid_evaluated_at_is_rejected(value):
    with pytest.raises(OfflineReportDataError, match="evaluated_at"):
        parse_report_evaluated_at(value)


@pytest.mark.parametrize("station", ["ATL", "KATLX", "K@UO", None])
def test_invalid_station_is_rejected(station):
    with pytest.raises(OfflineReportDataError, match="station"):
        fixture_resource_for_station(station)


def test_packaged_resources_match_their_repository_mirrors():
    assert report_template_resource().read_text(encoding="utf-8") == (
        PROJECT_ROOT / "reports" / "practicum-6.qmd"
    ).read_text(encoding="utf-8")
    assert json.loads(
        fixture_resource_for_station("KATL").read_text(encoding="utf-8")
    ) == json.loads(
        (PROJECT_ROOT / "tests" / "fixtures" / "metar-katl-success.json").read_text(
            encoding="utf-8"
        )
    )


def test_default_evaluation_time_makes_freshness_deterministic():
    first = load_offline_report_data(
        PROJECT_ROOT,
        station=DEFAULT_REPORT_STATION,
        evaluated_at=DEFAULT_REPORT_EVALUATED_AT,
    )
    second = load_offline_report_data(
        PROJECT_ROOT,
        station="katl",
        evaluated_at=DEFAULT_REPORT_EVALUATED_AT,
    )
    first_freshness = next(
        hazard
        for hazard in first.assessment.hazards
        if hazard.id == "observation_freshness"
    )
    second_freshness = next(
        hazard
        for hazard in second.assessment.hazards
        if hazard.id == "observation_freshness"
    )

    assert first.assessment.evaluated_at == second.assessment.evaluated_at
    assert first_freshness.concern_level == ConcernLevel.NOT_TRIGGERED
    assert first_freshness.observed_value["age_minutes"] == 8.0
    assert first_freshness == second_freshness
