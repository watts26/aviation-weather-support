import json
import logging

import requests


METAR_URL = "https://aviationweather.gov/api/data/metar"
USER_AGENT = "aviation-weather-support/0.1.0 METAR CLI"
REQUEST_TIMEOUT = 10
logger = logging.getLogger(__name__)


class MetarApiError(RuntimeError):
    """Raised when the METAR API request or response cannot be used."""


def fetch_metar(airport: str) -> list[object]:
    """Fetch the latest METAR observations for an ICAO identifier."""

    try:
        logger.info("Starting METAR API request for %s", airport)
        logger.debug(
            "Requesting METAR endpoint %s with a %s-second timeout",
            METAR_URL,
            REQUEST_TIMEOUT,
        )
        response = requests.get(
            METAR_URL,
            params={"ids": airport, "format": "json"},
            headers={"User-Agent": USER_AGENT},
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        logger.warning("METAR API request failed for %s: %s", airport, exc)
        raise MetarApiError(f"unable to retrieve METAR for {airport}: {exc}") from exc

    try:
        observations = response.json()
    except (requests.exceptions.JSONDecodeError, json.JSONDecodeError, ValueError) as exc:
        logger.warning("METAR API response for %s was not valid JSON", airport)
        raise MetarApiError("the METAR API returned invalid JSON.") from exc

    logger.info("METAR API response successfully parsed for %s", airport)
    if not isinstance(observations, list) or not any(
        isinstance(observation, dict) and observation for observation in observations
    ):
        logger.warning("No METAR observation was returned for %s", airport)
        raise MetarApiError(f"no METAR observation found for {airport}.")

    logger.info("Received %d METAR observation(s) for %s", len(observations), airport)
    return observations
