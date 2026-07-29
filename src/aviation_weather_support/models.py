from datetime import datetime
import logging

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator


Number = int | float
logger = logging.getLogger(__name__)


class MetarDataValidationError(ValueError):
    """Raised when a METAR observation does not contain usable data."""


class CloudLayer(BaseModel):
    """Cloud-layer fields used in the processed METAR output."""

    model_config = ConfigDict(extra="ignore")

    cover: str
    base: int | None = Field(default=None, ge=0)


class MetarObservation(BaseModel):
    """Validated Aviation Weather Center fields used by this project."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    icao_id: str = Field(alias="icaoId", pattern=r"^[A-Z0-9]{4}$", strict=True)
    airport_name: str | None = Field(default=None, alias="name")
    report_time: str = Field(alias="reportTime", min_length=1, strict=True)
    raw_metar: str = Field(alias="rawOb", min_length=1, strict=True)
    temperature_c: Number | None = Field(default=None, alias="temp")
    dewpoint_c: Number | None = Field(default=None, alias="dewp")
    wind_direction_deg: int | None = Field(
        default=None, alias="wdir", ge=0, le=360
    )
    wind_speed_kt: Number | None = Field(default=None, alias="wspd", ge=0)
    wind_gust_kt: Number | None = Field(default=None, alias="wgst", ge=0)
    visibility_miles: str | Number | None = Field(default=None, alias="visib")
    altimeter_hpa: Number | None = Field(default=None, alias="altim", gt=0)
    flight_category: str | None = Field(default=None, alias="fltCat")
    clouds: list[CloudLayer] | None = None

    @field_validator("report_time")
    @classmethod
    def validate_report_time(cls, value: str) -> str:
        try:
            datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("must be a valid ISO 8601 timestamp") from exc
        return value

    def to_processed_dict(self) -> dict[str, object]:
        return {
            "icao_id": self.icao_id,
            "airport_name": self.airport_name,
            "report_time": self.report_time,
            "raw_metar": self.raw_metar,
            "temperature_c": self.temperature_c,
            "dewpoint_c": self.dewpoint_c,
            "wind_direction_deg": self.wind_direction_deg,
            "wind_speed_kt": self.wind_speed_kt,
            "wind_gust_kt": self.wind_gust_kt,
            "visibility_miles": self.visibility_miles,
            "altimeter_hpa": self.altimeter_hpa,
            "flight_category": self.flight_category,
            "clouds": (
                [cloud.model_dump() for cloud in self.clouds]
                if self.clouds is not None
                else None
            ),
        }


def validate_metar_observation(observations: list[object]) -> MetarObservation:
    """Validate the first usable observation while retaining the raw response."""

    raw_observation = next(
        observation
        for observation in observations
        if isinstance(observation, dict) and observation
    )

    try:
        validated = MetarObservation.model_validate(raw_observation)
    except ValidationError as exc:
        first_problem = exc.errors(include_url=False)[0]
        location_parts = list(first_problem["loc"])
        if location_parts[-1] in {"int", "float", "str"}:
            location_parts.pop()
        location = ".".join(str(part) for part in location_parts)
        message = first_problem["msg"]
        logger.warning("METAR validation failed at %s: %s", location, message)
        raise MetarDataValidationError(
            f"METAR data could not be used at {location}: {message}"
        ) from exc

    logger.info("METAR observation validation succeeded for %s", validated.icao_id)
    return validated
