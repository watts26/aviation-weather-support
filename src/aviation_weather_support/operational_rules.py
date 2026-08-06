"""Central official flight-category and project hazard classification rules."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from fractions import Fraction
import math
import re
from typing import Any

from pydantic import BaseModel, ConfigDict

from aviation_weather_support.models import MetarObservation


WIND_ATTENTION_KT = 25.0
SUSTAINED_WIND_HIGH_ATTENTION_KT = 30.0
WIND_GUST_HIGH_ATTENTION_KT = 50.0
STALE_OBSERVATION_MINUTES = 75.0
FUTURE_TIME_TOLERANCE_MINUTES = 5.0

CEILING_COVERS = frozenset({"BKN", "OVC", "VV"})
VALID_CLOUD_COVERS = frozenset(
    {"CLR", "SKC", "NSC", "NCD", "FEW", "SCT", "BKN", "OVC", "VV"}
)
VALID_CONVECTIVE_TYPES = frozenset({"CB", "TCU"})

FAA_AIM_URL = (
    "https://www.faa.gov/air_traffic/publications/ATpubs/AIM/aim0701.html"
)
FAA_WIND_MINIMUMS_URL = (
    "https://www.faa.gov/newsroom/safety-briefing/personal-minimums-wind"
)
NWS_METAR_URL = "https://www.weather.gov/asos/METAR.html"
NWS_DATA_HELP_URL = "https://www.weather.gov/tg/datahelp"

INFORMATIONAL_DISCLAIMER = (
    "Informational screening only. Official flight categories are weather "
    "classifications, and project-defined concern levels are not universal "
    "aircraft operating limits or official flight guidance. Review applicable "
    "weather products, procedures, limitations, and pilot or dispatcher judgment."
)

_WEATHER_TOKEN = re.compile(
    r"^[+-]?(?:VC)?(?:MI|PR|BC|DR|BL|SH|TS|FZ)?"
    r"(?:(?:DZ|RA|SN|SG|IC|PL|GR|GS|UP|BR|FG|FU|VA|DU|SA|HZ|PY|PO|SQ|FC|SS|DS)){0,3}$"
)
_AO_REMARK = re.compile(r"(?:^|\s)(AO1|AO2)(?=\s|$)")


class OfficialFlightCategory(str, Enum):
    """Official ceiling-and-visibility weather categories."""

    VFR = "VFR"
    MVFR = "MVFR"
    IFR = "IFR"
    LIFR = "LIFR"
    UNAVAILABLE = "unavailable"


class ConcernLevel(str, Enum):
    """Project-defined concern levels for non-category hazards."""

    NOT_TRIGGERED = "not_triggered"
    ATTENTION = "attention"
    HIGH_ATTENTION = "high_attention"
    UNAVAILABLE = "unavailable"


class DataConfidence(str, Enum):
    """Confidence in the inputs used for one classification."""

    STANDARD = "standard"
    LIMITED = "limited"
    UNAVAILABLE = "unavailable"


class RuleClassification(str, Enum):
    """Whether a result is official or a project-owned interpretation."""

    OFFICIAL = "official"
    PROJECT_DEFINED = "project_defined"


CONCERN_DISPLAY_LABELS = {
    ConcernLevel.NOT_TRIGGERED: "No listed hazard trigger",
    ConcernLevel.ATTENTION: "Operational attention",
    ConcernLevel.HIGH_ATTENTION: "Elevated operational attention",
    ConcernLevel.UNAVAILABLE: "Assessment unavailable",
}


class SourceBasis(BaseModel):
    """One authoritative source supporting a rule or contextual anchor."""

    model_config = ConfigDict(frozen=True)

    title: str
    url: str
    relevance: str


class FlightCategoryAssessment(BaseModel):
    """Official flight-category classification kept separate from concerns."""

    model_config = ConfigDict(frozen=True)

    category: OfficialFlightCategory
    observed_value: dict[str, Any]
    trigger: str
    source_basis: tuple[SourceBasis, ...]
    rule_classification: RuleClassification = RuleClassification.OFFICIAL
    operational_judgment: str
    data_complete: bool


class HazardAssessment(BaseModel):
    """One project-defined hazard concern with its evidence and basis."""

    model_config = ConfigDict(frozen=True)

    id: str
    label: str
    concern_level: ConcernLevel
    display_label: str
    observed_value: dict[str, Any]
    trigger: str
    source_basis: tuple[SourceBasis, ...]
    rule_classification: RuleClassification = RuleClassification.PROJECT_DEFINED
    operational_judgment: str
    data_complete: bool
    data_confidence: DataConfidence
    confidence_note: str | None = None


class OperationalAssessment(BaseModel):
    """Official category and project concerns for one current observation."""

    model_config = ConfigDict(frozen=True)

    flight_category: FlightCategoryAssessment
    hazards: tuple[HazardAssessment, ...]
    overall_concern: ConcernLevel
    overall_display_label: str
    data_complete: bool
    evaluated_at: datetime
    disclaimer: str = INFORMATIONAL_DISCLAIMER


FLIGHT_CATEGORY_SOURCE = SourceBasis(
    title="FAA AIM categorical outlook definitions",
    url=FAA_AIM_URL,
    relevance=(
        "Defines VFR, MVFR, IFR, and LIFR ceiling and visibility categories; "
        "these weather categories are not aircraft operating approvals."
    ),
)
THUNDERSTORM_SOURCE = SourceBasis(
    title="FAA AIM thunderstorm avoidance and METAR weather codes",
    url=FAA_AIM_URL,
    relevance="Defines TS and VC coding and describes thunderstorm hazards.",
)
FREEZING_SOURCE = SourceBasis(
    title="FAA AIM icing definitions",
    url=FAA_AIM_URL,
    relevance="Defines freezing rain and freezing drizzle as freezing precipitation.",
)
AO_SOURCE = SourceBasis(
    title="FAA AIM automated weather observation capabilities",
    url=FAA_AIM_URL,
    relevance=(
        "AO1 identifies a station without a precipitation discriminator; AO2 "
        "identifies a station with one."
    ),
)
WIND_SOURCE = SourceBasis(
    title="FAA AIM aviation weather product wind criteria",
    url=FAA_AIM_URL,
    relevance=(
        "Provides contextual anchors for categorical-outlook WIND notation, "
        "sustained surface wind AIRMETs, and severe-thunderstorm gust criteria."
    ),
)
WIND_CONTEXT_SOURCE = SourceBasis(
    title="FAA Personal Minimums for Wind",
    url=FAA_WIND_MINIMUMS_URL,
    relevance=(
        "Explains that wind limits must reflect the pilot, aircraft, runway, "
        "and operating context."
    ),
)
FRESHNESS_SOURCES = (
    SourceBasis(
        title="NWS METAR overview",
        url=NWS_METAR_URL,
        relevance="Describes the routine hourly METAR cadence and one-hour validity.",
    ),
    SourceBasis(
        title="NWS aviation data retrieval guidance",
        url=NWS_DATA_HELP_URL,
        relevance="Describes expected central processing time for hourly observations.",
    ),
)


def parse_visibility_miles(value: str | int | float | None) -> float | None:
    """Convert a decoded visibility value to statute miles when possible."""

    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        parsed = float(value)
        return parsed if math.isfinite(parsed) and parsed >= 0 else None

    text = value.strip().removesuffix("+").strip()
    try:
        if " " in text:
            whole, fraction = text.split(maxsplit=1)
            parsed = float(whole) + float(Fraction(fraction))
        else:
            parsed = float(Fraction(text))
    except (ValueError, ZeroDivisionError):
        return None
    return parsed if math.isfinite(parsed) and parsed >= 0 else None


def parse_present_weather(value: str | None) -> tuple[str, ...] | None:
    """Return validated decoded METAR weather tokens; null means no phenomena."""

    if value is None or not value.strip():
        return ()
    tokens = tuple(value.upper().split())
    if any(not _WEATHER_TOKEN.fullmatch(token) for token in tokens):
        return None
    return tokens


def parse_observation_time(value: object) -> datetime | None:
    """Parse an AWC observation time represented as epoch seconds or ISO text."""

    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        numeric = float(value)
        if not math.isfinite(numeric):
            return None
        try:
            return datetime.fromtimestamp(numeric, tz=timezone.utc)
        except (OSError, OverflowError, ValueError):
            return None
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        if parsed.tzinfo is None:
            return None
        return parsed.astimezone(timezone.utc)
    return None


def _hazard(
    *,
    id: str,
    label: str,
    concern_level: ConcernLevel,
    observed_value: dict[str, Any],
    trigger: str,
    source_basis: tuple[SourceBasis, ...],
    operational_judgment: str,
    data_complete: bool = True,
    data_confidence: DataConfidence = DataConfidence.STANDARD,
    confidence_note: str | None = None,
) -> HazardAssessment:
    """Build a hazard with its stable user-facing concern label."""

    return HazardAssessment(
        id=id,
        label=label,
        concern_level=concern_level,
        display_label=CONCERN_DISPLAY_LABELS[concern_level],
        observed_value=observed_value,
        trigger=trigger,
        source_basis=source_basis,
        operational_judgment=operational_judgment,
        data_complete=data_complete,
        data_confidence=data_confidence,
        confidence_note=confidence_note,
    )


def _category_for_ceiling(ceiling_ft: int | None) -> OfficialFlightCategory:
    if ceiling_ft is None or ceiling_ft > 3000:
        return OfficialFlightCategory.VFR
    if ceiling_ft >= 1000:
        return OfficialFlightCategory.MVFR
    if ceiling_ft >= 500:
        return OfficialFlightCategory.IFR
    return OfficialFlightCategory.LIFR


def _category_for_visibility(visibility_sm: float) -> OfficialFlightCategory:
    if visibility_sm > 5:
        return OfficialFlightCategory.VFR
    if visibility_sm >= 3:
        return OfficialFlightCategory.MVFR
    if visibility_sm >= 1:
        return OfficialFlightCategory.IFR
    return OfficialFlightCategory.LIFR


def assess_flight_category(observation: MetarObservation) -> FlightCategoryAssessment:
    """Classify official flight category from structured ceiling and visibility."""

    visibility = parse_visibility_miles(observation.visibility_miles)
    visibility_category = (
        _category_for_visibility(visibility) if visibility is not None else None
    )

    ceiling: int | None = None
    ceiling_category: OfficialFlightCategory | None = None
    cloud_data_usable = observation.clouds is not None
    if observation.clouds is not None:
        covers = [layer.cover.upper() for layer in observation.clouds]
        cloud_data_usable = all(cover in VALID_CLOUD_COVERS for cover in covers)
        ceiling_layers = [
            layer
            for layer in observation.clouds
            if layer.cover.upper() in CEILING_COVERS
        ]
        if any(layer.base is None for layer in ceiling_layers):
            cloud_data_usable = False
        if cloud_data_usable:
            usable_bases = [
                layer.base for layer in ceiling_layers if layer.base is not None
            ]
            ceiling = min(usable_bases) if usable_bases else None
            ceiling_category = _category_for_ceiling(ceiling)

    known_categories = [
        category
        for category in (ceiling_category, visibility_category)
        if category is not None
    ]
    complete = ceiling_category is not None and visibility_category is not None
    rank = {
        OfficialFlightCategory.VFR: 0,
        OfficialFlightCategory.MVFR: 1,
        OfficialFlightCategory.IFR: 2,
        OfficialFlightCategory.LIFR: 3,
    }
    if complete:
        category = max(known_categories, key=rank.__getitem__)
    elif OfficialFlightCategory.LIFR in known_categories:
        category = OfficialFlightCategory.LIFR
    else:
        category = OfficialFlightCategory.UNAVAILABLE

    trigger = {
        OfficialFlightCategory.VFR: "Ceiling >3,000 ft AGL and visibility >5 SM.",
        OfficialFlightCategory.MVFR: (
            "Ceiling 1,000-3,000 ft AGL inclusive and/or visibility 3-5 SM inclusive."
        ),
        OfficialFlightCategory.IFR: (
            "Ceiling 500 to <1,000 ft AGL and/or visibility 1 to <3 SM."
        ),
        OfficialFlightCategory.LIFR: "Ceiling <500 ft AGL and/or visibility <1 SM.",
        OfficialFlightCategory.UNAVAILABLE: (
            "A complete category requires usable ceiling and visibility data; "
            "a known LIFR dimension remains classifiable when the other is missing."
        ),
    }[category]
    return FlightCategoryAssessment(
        category=category,
        observed_value={
            "ceiling_ft_agl": ceiling,
            "visibility_sm": visibility,
            "awc_reported_category": observation.flight_category,
        },
        trigger=trigger,
        source_basis=(FLIGHT_CATEGORY_SOURCE,),
        operational_judgment=(
            "Describes the point observation's official ceiling and visibility "
            "weather category without determining flight suitability."
        ),
        data_complete=complete,
    )


def assess_thunderstorm(observation: MetarObservation) -> HazardAssessment:
    """Assess decoded thunderstorm weather tokens."""

    weather = parse_present_weather(observation.weather_string)
    observed = {"present_weather": observation.weather_string}
    if weather is None:
        return _hazard(
            id="thunderstorm",
            label="Thunderstorm",
            concern_level=ConcernLevel.UNAVAILABLE,
            observed_value=observed,
            trigger="Decoded present-weather data is malformed or unusable.",
            source_basis=(THUNDERSTORM_SOURCE,),
            operational_judgment="Obtain usable current weather data before relying on this screening result.",
            data_complete=False,
            data_confidence=DataConfidence.UNAVAILABLE,
        )
    station_ts = any("TS" in token and "VCTS" not in token for token in weather)
    vicinity_ts = any("VCTS" in token for token in weather)
    if station_ts:
        level = ConcernLevel.HIGH_ATTENTION
        trigger = "A decoded present-weather token contains TS at the station."
        judgment = "Review radar and official convective products and plan for thunderstorm avoidance."
    elif vicinity_ts:
        level = ConcernLevel.ATTENTION
        trigger = "A decoded present-weather token contains VCTS (5-10 SM vicinity in a U.S. METAR)."
        judgment = "Review the location and movement of nearby convection using official spatial products."
    else:
        level = ConcernLevel.NOT_TRIGGERED
        trigger = "No TS or VCTS token is present in decoded present weather."
        judgment = "No listed thunderstorm trigger was found in this point observation."
    return _hazard(
        id="thunderstorm",
        label="Thunderstorm",
        concern_level=level,
        observed_value=observed,
        trigger=trigger,
        source_basis=(THUNDERSTORM_SOURCE,),
        operational_judgment=judgment,
    )


def assess_convective_cloud(observation: MetarObservation) -> HazardAssessment:
    """Assess decoded cumulonimbus and towering-cumulus cloud types."""

    if observation.clouds is None:
        return _hazard(
            id="convective_cloud",
            label="Convective cloud",
            concern_level=ConcernLevel.UNAVAILABLE,
            observed_value={"cloud_types": None},
            trigger="Structured cloud data is unavailable.",
            source_basis=(THUNDERSTORM_SOURCE,),
            operational_judgment="Use other current official weather products to assess convective development.",
            data_complete=False,
            data_confidence=DataConfidence.UNAVAILABLE,
        )
    cloud_types = [layer.cloud_type.upper() for layer in observation.clouds if layer.cloud_type]
    if any(cloud_type not in VALID_CONVECTIVE_TYPES for cloud_type in cloud_types):
        return _hazard(
            id="convective_cloud",
            label="Convective cloud",
            concern_level=ConcernLevel.UNAVAILABLE,
            observed_value={"cloud_types": cloud_types},
            trigger="A structured cloud type is malformed or unusable.",
            source_basis=(THUNDERSTORM_SOURCE,),
            operational_judgment="Use other current official weather products to assess convective development.",
            data_complete=False,
            data_confidence=DataConfidence.UNAVAILABLE,
        )
    detected = sorted(set(cloud_types) & VALID_CONVECTIVE_TYPES)
    level = ConcernLevel.ATTENTION if detected else ConcernLevel.NOT_TRIGGERED
    return _hazard(
        id="convective_cloud",
        label="Convective cloud",
        concern_level=level,
        observed_value={"cloud_types": detected},
        trigger=(
            "A structured cloud layer is typed CB or TCU."
            if detected
            else "No structured cloud layer is typed CB or TCU."
        ),
        source_basis=(THUNDERSTORM_SOURCE,),
        operational_judgment=(
            "Review radar and official convective products for development and extent."
            if detected
            else "No listed convective-cloud trigger was found in the structured layers."
        ),
    )


def _automated_station_type(raw_metar: str) -> str | None:
    """Extract only the AO1/AO2 capability token from METAR remarks evidence."""

    match = _AO_REMARK.search(raw_metar.upper())
    return match.group(1) if match else None


def assess_freezing_precipitation(observation: MetarObservation) -> HazardAssessment:
    """Assess decoded freezing rain or freezing drizzle tokens."""

    weather = parse_present_weather(observation.weather_string)
    station_type = _automated_station_type(observation.raw_metar)
    observed = {
        "present_weather": observation.weather_string,
        "automated_station_type": station_type,
    }
    if weather is None:
        return _hazard(
            id="freezing_precipitation",
            label="Freezing precipitation",
            concern_level=ConcernLevel.UNAVAILABLE,
            observed_value=observed,
            trigger="Decoded present-weather data is malformed or unusable.",
            source_basis=(FREEZING_SOURCE, AO_SOURCE),
            operational_judgment="Obtain usable current weather data before relying on this screening result.",
            data_complete=False,
            data_confidence=DataConfidence.UNAVAILABLE,
        )
    detected = [token for token in weather if "FZRA" in token or "FZDZ" in token]
    level = ConcernLevel.HIGH_ATTENTION if detected else ConcernLevel.NOT_TRIGGERED
    limited = station_type == "AO1"
    return _hazard(
        id="freezing_precipitation",
        label="Freezing precipitation",
        concern_level=level,
        observed_value=observed,
        trigger=(
            "A decoded present-weather token contains FZRA or FZDZ at any intensity."
            if detected
            else "No FZRA or FZDZ token is present in decoded present weather."
        ),
        source_basis=(FREEZING_SOURCE, AO_SOURCE),
        operational_judgment=(
            "Review official icing information and applicable aircraft, operator, and ground-contamination procedures."
            if detected
            else "No listed freezing-precipitation trigger was found in this point observation."
        ),
        data_confidence=DataConfidence.LIMITED if limited else DataConfidence.STANDARD,
        confidence_note=(
            "AO1 indicates that the automated station lacks a precipitation discriminator; this limits confidence but does not make the result unavailable."
            if limited
            else None
        ),
    )


def assess_wind(observation: MetarObservation) -> HazardAssessment:
    """Assess project-defined sustained-wind and gust concern thresholds."""

    sustained = observation.wind_speed_kt
    gust = observation.wind_gust_kt
    observed = {"sustained_kt": sustained, "gust_kt": gust}
    if sustained is None:
        return _hazard(
            id="wind",
            label="Wind",
            concern_level=ConcernLevel.UNAVAILABLE,
            observed_value=observed,
            trigger="Structured sustained-wind speed is unavailable.",
            source_basis=(WIND_SOURCE, WIND_CONTEXT_SOURCE),
            operational_judgment="Obtain usable wind data and compare it with the applicable operating context.",
            data_complete=False,
            data_confidence=DataConfidence.UNAVAILABLE,
        )
    if sustained >= SUSTAINED_WIND_HIGH_ATTENTION_KT or (
        gust is not None and gust >= WIND_GUST_HIGH_ATTENTION_KT
    ):
        level = ConcernLevel.HIGH_ATTENTION
        trigger = "Sustained wind is >=30 kt or reported gust is >=50 kt."
    elif sustained >= WIND_ATTENTION_KT or (
        gust is not None and gust >= WIND_ATTENTION_KT
    ):
        level = ConcernLevel.ATTENTION
        trigger = "Sustained wind or reported gust is >=25 kt."
    else:
        level = ConcernLevel.NOT_TRIGGERED
        trigger = "Sustained wind and any reported gust are <25 kt."
    return _hazard(
        id="wind",
        label="Wind",
        concern_level=level,
        observed_value=observed,
        trigger=trigger,
        source_basis=(WIND_SOURCE, WIND_CONTEXT_SOURCE),
        operational_judgment=(
            "Compare reported wind with runway-relative conditions and applicable aircraft, operator, and personal limits; these project thresholds are not universal limits."
        ),
    )


def assess_freshness(
    observation: MetarObservation, evaluated_at: datetime
) -> HazardAssessment:
    """Assess project-defined observation-age and future-time tolerances."""

    observation_time = parse_observation_time(observation.observation_time)
    if observation_time is None:
        return _hazard(
            id="observation_freshness",
            label="Observation freshness",
            concern_level=ConcernLevel.UNAVAILABLE,
            observed_value={"observation_time": observation.observation_time},
            trigger="AWC obsTime is missing or unusable.",
            source_basis=FRESHNESS_SOURCES,
            operational_judgment="Obtain an observation with a usable observation time before treating it as current.",
            data_complete=False,
            data_confidence=DataConfidence.UNAVAILABLE,
        )
    age_minutes = (evaluated_at - observation_time).total_seconds() / 60
    observed = {
        "observation_time": observation_time.isoformat(),
        "age_minutes": round(age_minutes, 3),
    }
    if age_minutes < -FUTURE_TIME_TOLERANCE_MINUTES:
        return _hazard(
            id="observation_freshness",
            label="Observation freshness",
            concern_level=ConcernLevel.UNAVAILABLE,
            observed_value=observed,
            trigger="Observation time is more than 5 minutes in the future.",
            source_basis=FRESHNESS_SOURCES,
            operational_judgment="Check time synchronization or obtain a current observation with a plausible timestamp.",
            data_complete=False,
            data_confidence=DataConfidence.UNAVAILABLE,
        )
    if age_minutes > STALE_OBSERVATION_MINUTES:
        level = ConcernLevel.ATTENTION
        trigger = "Observation age is >75 minutes."
        judgment = "Obtain a newer METAR, SPECI, ATIS, or direct ASOS/AWOS report."
    else:
        level = ConcernLevel.NOT_TRIGGERED
        trigger = "Observation age is <=75 minutes and no more than 5 minutes in the future."
        judgment = "No project-defined freshness trigger was reached."
    return _hazard(
        id="observation_freshness",
        label="Observation freshness",
        concern_level=level,
        observed_value=observed,
        trigger=trigger,
        source_basis=FRESHNESS_SOURCES,
        operational_judgment=judgment,
    )


def assess_current_conditions(
    observation: MetarObservation, *, evaluated_at: datetime | None = None
) -> OperationalAssessment:
    """Assess official category and all project-defined current hazards."""

    evaluated = evaluated_at or datetime.now(timezone.utc)
    if evaluated.tzinfo is None:
        raise ValueError("evaluated_at must be timezone-aware")
    evaluated = evaluated.astimezone(timezone.utc)
    flight_category = assess_flight_category(observation)
    hazards = (
        assess_thunderstorm(observation),
        assess_convective_cloud(observation),
        assess_freezing_precipitation(observation),
        assess_wind(observation),
        assess_freshness(observation, evaluated),
    )
    known = [
        hazard.concern_level
        for hazard in hazards
        if hazard.concern_level != ConcernLevel.UNAVAILABLE
    ]
    if ConcernLevel.HIGH_ATTENTION in known:
        overall = ConcernLevel.HIGH_ATTENTION
    elif ConcernLevel.ATTENTION in known:
        overall = ConcernLevel.ATTENTION
    elif ConcernLevel.NOT_TRIGGERED in known:
        overall = ConcernLevel.NOT_TRIGGERED
    else:
        overall = ConcernLevel.UNAVAILABLE
    return OperationalAssessment(
        flight_category=flight_category,
        hazards=hazards,
        overall_concern=overall,
        overall_display_label=CONCERN_DISPLAY_LABELS[overall],
        data_complete=(
            flight_category.data_complete
            and all(hazard.data_complete for hazard in hazards)
        ),
        evaluated_at=evaluated,
    )
