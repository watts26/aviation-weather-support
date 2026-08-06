import json
from pathlib import Path
from unittest.mock import Mock

import pytest
import requests

from aviation_weather_support.api import (
    METAR_URL,
    REQUEST_TIMEOUT,
    USER_AGENT,
    MetarApiError,
    fetch_metar,
)


FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(name: str):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_fetch_metar_returns_fixture_and_sends_expected_request(monkeypatch):
    expected = load_fixture("metar-katl-success.json")
    response = Mock()
    response.status_code = 200
    response.json.return_value = expected
    get = Mock(return_value=response)
    monkeypatch.setattr("aviation_weather_support.api.requests.get", get)

    observations = fetch_metar("KATL")

    assert observations == expected
    get.assert_called_once_with(
        METAR_URL,
        params={"ids": "KATL", "format": "json"},
        headers={"User-Agent": USER_AGENT},
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status.assert_called_once_with()


def test_fetch_metar_explains_an_http_failure(monkeypatch):
    response = Mock()
    response.raise_for_status.side_effect = requests.HTTPError(
        "503 Service Unavailable"
    )
    monkeypatch.setattr(
        "aviation_weather_support.api.requests.get", Mock(return_value=response)
    )

    with pytest.raises(MetarApiError, match="503 Service Unavailable"):
        fetch_metar("KATL")


def test_fetch_metar_rejects_malformed_json(monkeypatch):
    response = Mock()
    response.status_code = 200
    response.json.side_effect = json.JSONDecodeError(
        "Expecting property name", "{", 1
    )
    monkeypatch.setattr(
        "aviation_weather_support.api.requests.get", Mock(return_value=response)
    )

    with pytest.raises(MetarApiError, match="returned invalid JSON"):
        fetch_metar("KATL")


def test_fetch_metar_rejects_a_200_empty_json_list(monkeypatch):
    response = Mock()
    response.status_code = 200
    response.json.return_value = load_fixture("metar-empty.json")
    monkeypatch.setattr(
        "aviation_weather_support.api.requests.get", Mock(return_value=response)
    )

    with pytest.raises(
        MetarApiError,
        match="No current METAR observation was found for KATL",
    ):
        fetch_metar("KATL")


def test_fetch_metar_treats_204_as_no_observation_without_parsing_json(
    monkeypatch,
):
    response = Mock()
    response.status_code = 204
    monkeypatch.setattr(
        "aviation_weather_support.api.requests.get", Mock(return_value=response)
    )

    with pytest.raises(
        MetarApiError,
        match="No current METAR observation was found for KAUO",
    ):
        fetch_metar("KAUO")

    response.raise_for_status.assert_called_once_with()
    response.json.assert_not_called()


def test_fetch_metar_rejects_a_200_empty_body_as_invalid_json(monkeypatch):
    response = Mock()
    response.status_code = 200
    response.json.side_effect = requests.exceptions.JSONDecodeError(
        "Expecting value", "", 0
    )
    monkeypatch.setattr(
        "aviation_weather_support.api.requests.get", Mock(return_value=response)
    )

    with pytest.raises(MetarApiError, match="returned invalid JSON"):
        fetch_metar("KATL")
