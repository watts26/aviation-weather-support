import logging
import re
from dataclasses import dataclass

from aviation_weather_support.api import fetch_metar
from aviation_weather_support.models import (
    MetarObservation,
    validate_metar_observation,
)


logger = logging.getLogger(__name__)


class AirportValidationError(ValueError):
    """Raised when an airport is not a four-character ICAO identifier."""


@dataclass(frozen=True)
class MetarResult:
    """Raw and validated forms of one METAR request."""

    airport: str
    raw_observations: list[object]
    observation: MetarObservation
    processed: dict[str, object]


def normalize_airport(value: str) -> str:
    airport = value.upper()
    if not re.fullmatch(r"[A-Z0-9]{4}", airport):
        raise AirportValidationError(
            "airport must be a four-character ICAO identifier containing only "
            "A-Z and 0-9 (for example KATL)"
        )
    return airport


def retrieve_metar(airport: str) -> MetarResult:
    """Normalize, fetch, validate, and process one airport's latest METAR."""

    normalized_airport = normalize_airport(airport)
    logger.info("Normalized airport identifier: %s", normalized_airport)
    raw_observations = fetch_metar(normalized_airport)
    observation = validate_metar_observation(raw_observations)

    return MetarResult(
        airport=normalized_airport,
        raw_observations=raw_observations,
        observation=observation,
        processed=observation.to_processed_dict(),
    )
