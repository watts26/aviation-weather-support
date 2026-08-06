"""Coordinate airport validation, METAR retrieval, and data assessment."""

import logging
import re
from dataclasses import dataclass
from datetime import datetime

from aviation_weather_support.api import fetch_metar
from aviation_weather_support.models import (
    MetarDataValidationError,
    MetarObservation,
    validate_metar_observation,
)
from aviation_weather_support.operational_rules import (
    OperationalAssessment,
    assess_current_conditions,
)


logger = logging.getLogger(__name__)


class AirportValidationError(ValueError):
    """Raised when an airport is not a four-character ICAO identifier."""


@dataclass(frozen=True)
class MetarResult:
    """Raw, validated, assessed, and processed forms of one METAR request."""

    airport: str
    raw_observations: list[object]
    observation: MetarObservation
    operational_assessment: OperationalAssessment
    processed: dict[str, object]


def normalize_airport(value: str) -> str:
    """Normalize and validate a four-character ICAO identifier."""

    airport = value.upper()
    if not re.fullmatch(r"[A-Z0-9]{4}", airport):
        raise AirportValidationError(
            "airport must be a four-character ICAO identifier containing only "
            "A-Z and 0-9 (for example KATL)"
        )
    return airport


def retrieve_metar(
    airport: str, *, evaluated_at: datetime | None = None
) -> MetarResult:
    """Normalize, fetch, validate, and process one airport's latest METAR."""

    normalized_airport = normalize_airport(airport)
    logger.info("Normalized airport identifier: %s", normalized_airport)
    raw_observations = fetch_metar(normalized_airport)
    return process_metar_observations(
        normalized_airport,
        raw_observations,
        evaluated_at=evaluated_at,
    )


def process_metar_observations(
    airport: str,
    raw_observations: list[object],
    *,
    evaluated_at: datetime | None = None,
) -> MetarResult:
    """Validate and assess an already-retrieved METAR response."""

    normalized_airport = normalize_airport(airport)
    observation = validate_metar_observation(raw_observations)
    if observation.icao_id != normalized_airport:
        raise MetarDataValidationError(
            "METAR station mismatch: requested "
            f"{normalized_airport}, but the response contains {observation.icao_id}."
        )
    operational_assessment = assess_current_conditions(
        observation, evaluated_at=evaluated_at
    )
    processed = observation.to_processed_dict()
    processed["operational_assessment"] = operational_assessment.model_dump(
        mode="json"
    )

    return MetarResult(
        airport=normalized_airport,
        raw_observations=raw_observations,
        observation=observation,
        operational_assessment=operational_assessment,
        processed=processed,
    )
