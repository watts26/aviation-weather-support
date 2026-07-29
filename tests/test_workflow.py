import json
from pathlib import Path
from unittest.mock import Mock

import pytest

from aviation_weather_support.api import MetarApiError
from aviation_weather_support.models import MetarDataValidationError
from aviation_weather_support import workflow
from aviation_weather_support.workflow import (
    AirportValidationError,
    normalize_airport,
    retrieve_metar,
)


FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(name: str):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_shared_workflow_returns_untouched_raw_and_processed_data(monkeypatch):
    raw = load_fixture("metar-katl-success.json")
    fetch = Mock(return_value=raw)
    monkeypatch.setattr(workflow, "fetch_metar", fetch)

    result = retrieve_metar("katl")

    assert result.airport == "KATL"
    assert result.raw_observations is raw
    assert result.observation.icao_id == "KATL"
    assert result.processed["airport_name"] == (
        "Atlanta/Hartsfield-Jackson Intl, GA, US"
    )
    assert "receiptTime" in result.raw_observations[0]
    fetch.assert_called_once_with("KATL")


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
