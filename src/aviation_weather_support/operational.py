"""Project-defined operational flags for validated current METAR conditions."""

from enum import Enum
from fractions import Fraction

from pydantic import BaseModel, ConfigDict

from aviation_weather_support.models import MetarObservation


VISIBILITY_CAUTION_SM = 5.0
VISIBILITY_SEVERE_SM = 3.0
CEILING_CAUTION_FT = 3000
CEILING_SEVERE_FT = 1000
SUSTAINED_WIND_CAUTION_KT = 15.0
SUSTAINED_WIND_SEVERE_KT = 25.0
WIND_GUST_CAUTION_KT = 20.0
WIND_GUST_SEVERE_KT = 30.0

CEILING_COVERS = frozenset({"BKN", "OVC", "VV"})
INFORMATIONAL_DISCLAIMER = (
    "Informational screening only. These project-defined thresholds are not "
    "official flight guidance and do not replace official weather products, "
    "aircraft or operator limitations, or pilot and dispatcher judgment."
)


class FlagStatus(str, Enum):
    """Severity levels used by the current-condition assessment."""

    NORMAL = "normal"
    CAUTION = "caution"
    SEVERE = "severe"
    UNAVAILABLE = "unavailable"


class OperationalFlag(BaseModel):
    """One explicit, serializable current-condition flag."""

    model_config = ConfigDict(frozen=True)

    id: str
    label: str
    status: FlagStatus
    observed: dict[str, int | float | str | None]
    message: str


class CurrentConditionsAssessment(BaseModel):
    """Combined informational assessment of one validated observation."""

    model_config = ConfigDict(frozen=True)

    overall_status: FlagStatus
    data_complete: bool
    flags: tuple[OperationalFlag, ...]
    disclaimer: str = INFORMATIONAL_DISCLAIMER


def parse_visibility_miles(value: str | int | float | None) -> float | None:
    """Convert an API visibility value to statute miles when possible."""

    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)

    text = value.strip().removesuffix("+").strip()
    try:
        if " " in text:
            whole, fraction = text.split(maxsplit=1)
            return float(whole) + float(Fraction(fraction))
        return float(Fraction(text))
    except (ValueError, ZeroDivisionError):
        return None


def assess_visibility(observation: MetarObservation) -> OperationalFlag:
    visibility = parse_visibility_miles(observation.visibility_miles)
    if visibility is None:
        return OperationalFlag(
            id="visibility",
            label="Visibility",
            status=FlagStatus.UNAVAILABLE,
            observed={},
            message="Visibility data was not reported in a usable form.",
        )
    if visibility < VISIBILITY_SEVERE_SM:
        status = FlagStatus.SEVERE
        message = "Visibility is below 3 statute miles."
    elif visibility < VISIBILITY_CAUTION_SM:
        status = FlagStatus.CAUTION
        message = "Visibility is from 3 to less than 5 statute miles."
    else:
        status = FlagStatus.NORMAL
        message = "Visibility is at least 5 statute miles."
    return OperationalFlag(
        id="visibility",
        label="Visibility",
        status=status,
        observed={"visibility_sm": visibility},
        message=message,
    )


def assess_ceiling(observation: MetarObservation) -> OperationalFlag:
    if observation.clouds is None:
        return OperationalFlag(
            id="ceiling",
            label="Ceiling",
            status=FlagStatus.UNAVAILABLE,
            observed={},
            message="Cloud-layer data was not reported.",
        )

    ceiling_layers = [
        layer for layer in observation.clouds if layer.cover.upper() in CEILING_COVERS
    ]
    if any(layer.base is None for layer in ceiling_layers):
        return OperationalFlag(
            id="ceiling",
            label="Ceiling",
            status=FlagStatus.UNAVAILABLE,
            observed={},
            message="A ceiling layer was reported without a usable base.",
        )
    if not ceiling_layers:
        return OperationalFlag(
            id="ceiling",
            label="Ceiling",
            status=FlagStatus.NORMAL,
            observed={"ceiling_ft_agl": None},
            message="No BKN, OVC, or vertical-visibility ceiling was reported.",
        )

    ceiling = min(layer.base for layer in ceiling_layers if layer.base is not None)
    if ceiling < CEILING_SEVERE_FT:
        status = FlagStatus.SEVERE
        message = "Ceiling is below 1,000 feet AGL."
    elif ceiling < CEILING_CAUTION_FT:
        status = FlagStatus.CAUTION
        message = "Ceiling is from 1,000 to 2,999 feet AGL."
    else:
        status = FlagStatus.NORMAL
        message = "Ceiling is at least 3,000 feet AGL."
    return OperationalFlag(
        id="ceiling",
        label="Ceiling",
        status=status,
        observed={"ceiling_ft_agl": ceiling},
        message=message,
    )


def assess_wind(observation: MetarObservation) -> OperationalFlag:
    sustained = observation.wind_speed_kt
    gust = observation.wind_gust_kt
    observed = {"sustained_kt": sustained, "gust_kt": gust}
    if sustained is None and gust is None:
        return OperationalFlag(
            id="wind",
            label="Wind",
            status=FlagStatus.UNAVAILABLE,
            observed=observed,
            message="Sustained wind and gust data were not reported.",
        )

    severe = (
        sustained is not None and sustained >= SUSTAINED_WIND_SEVERE_KT
    ) or (gust is not None and gust >= WIND_GUST_SEVERE_KT)
    caution = (
        sustained is not None and sustained >= SUSTAINED_WIND_CAUTION_KT
    ) or (gust is not None and gust >= WIND_GUST_CAUTION_KT)

    if severe:
        status = FlagStatus.SEVERE
        message = "Sustained wind or gusts meet a project severe threshold."
    elif caution:
        status = FlagStatus.CAUTION
        message = "Sustained wind or gusts meet a project caution threshold."
    else:
        status = FlagStatus.NORMAL
        message = "Reported wind is below the project caution thresholds."
    return OperationalFlag(
        id="wind",
        label="Wind",
        status=status,
        observed=observed,
        message=message,
    )


def assess_current_conditions(
    observation: MetarObservation,
) -> CurrentConditionsAssessment:
    """Assess reusable current-condition flags from validated METAR data."""

    flags = (
        assess_visibility(observation),
        assess_ceiling(observation),
        assess_wind(observation),
    )
    known_statuses = {
        flag.status for flag in flags if flag.status != FlagStatus.UNAVAILABLE
    }
    if FlagStatus.SEVERE in known_statuses:
        overall = FlagStatus.SEVERE
    elif FlagStatus.CAUTION in known_statuses:
        overall = FlagStatus.CAUTION
    elif FlagStatus.NORMAL in known_statuses:
        overall = FlagStatus.NORMAL
    else:
        overall = FlagStatus.UNAVAILABLE

    return CurrentConditionsAssessment(
        overall_status=overall,
        data_complete=all(
            flag.status != FlagStatus.UNAVAILABLE for flag in flags
        ),
        flags=flags,
    )
