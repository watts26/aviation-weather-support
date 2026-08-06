import json
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock

import pytest

from aviation_weather_support.api import MetarApiError
from aviation_weather_support.models import MetarDataValidationError
from aviation_weather_support.operational_rules import ConcernLevel
from aviation_weather_support import workflow
from aviation_weather_support.workflow import (
    AirportValidationError,
    normalize_airport,
    process_metar_observations,
    retrieve_metar,
)


FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(name: str):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_shared_workflow_returns_untouched_raw_and_processed_data(monkeypatch):
    raw = load_fixture("metar-katl-success.json")
    fetch = Mock(return_value=raw)
    monkeypatch.setattr(workflow, "fetch_metar", fetch)

    result = retrieve_metar(
        "katl", evaluated_at=datetime(2026, 7, 29, 20, 0, tzinfo=timezone.utc)
    )

    assert result.airport == "KATL"
    assert result.raw_observations is raw
    assert result.observation.icao_id == "KATL"
    assert result.processed["airport_name"] == (
        "Atlanta/Hartsfield-Jackson Intl, GA, US"
    )
    assert "receiptTime" in result.raw_observations[0]
    assert (
        result.operational_assessment.overall_concern
        == ConcernLevel.NOT_TRIGGERED
    )
    assert result.processed["operational_assessment"] == (
        result.operational_assessment.model_dump(mode="json")
    )
    fetch.assert_called_once_with("KATL")


def test_variable_wind_preserves_raw_and_processes_remaining_data():
    raw = deepcopy(load_fixture("metar-katl-success.json"))
    raw[0]["wdir"] = "VRB"
    original = deepcopy(raw)

    result = process_metar_observations(
        "KATL",
        raw,
        evaluated_at=datetime(2026, 7, 29, 20, 0, tzinfo=timezone.utc),
    )

    assert result.raw_observations is raw
    assert result.raw_observations == original
    assert result.processed["wind_direction_deg"] == "VRB"
    assert result.processed["wind_speed_kt"] == 9
    assert result.processed["visibility_miles"] == 9
    assert result.operational_assessment.hazards[3].id == "wind"


def test_invalid_airport_is_rejected_before_api_retrieval(monkeypatch):
    fetch = Mock()
    monkeypatch.setattr(workflow, "fetch_metar", fetch)

    with pytest.raises(AirportValidationError, match="four-character ICAO"):
        retrieve_metar("ATL")

    fetch.assert_not_called()


def test_api_failure_passes_through_the_shared_workflow(monkeypatch):
    monkeypatch.setattr(
        workflow,
        "fetch_metar",
        Mock(side_effect=MetarApiError("API unavailable")),
    )

    with pytest.raises(MetarApiError, match="API unavailable"):
        retrieve_metar("KATL")


def test_validation_failure_passes_through_the_shared_workflow(monkeypatch):
    monkeypatch.setattr(
        workflow,
        "fetch_metar",
        Mock(return_value=load_fixture("metar-invalid.json")),
    )

    with pytest.raises(MetarDataValidationError, match="at reportTime"):
        retrieve_metar("KATL")


def test_normalize_airport_accepts_alphanumeric_identifiers():
    assert normalize_airport("k1a2") == "K1A2"
