"""Render validated METAR conditions and operational flags with Streamlit."""

import json
from html import escape

import streamlit as st

from aviation_weather_support.api import MetarApiError
from aviation_weather_support.logging_config import configure_logging
from aviation_weather_support.models import MetarDataValidationError, MetarObservation
from aviation_weather_support.operational_rules import (
    ConcernLevel,
    HazardAssessment,
    OperationalAssessment,
)
from aviation_weather_support.workflow import (
    AirportValidationError,
    MetarResult,
    retrieve_metar,
)


AUBURN_BLUE = "#0B2341"
AUBURN_ORANGE = "#E86100"

AUBURN_STYLES = f"""
<style>
    :root {{
        color-scheme: dark;
    }}
    .stApp {{
        background: #171A1F;
        color: #F4F6F8;
    }}
    header[data-testid="stHeader"] {{
        background: rgba(23, 26, 31, 0.94);
    }}
    .block-container {{
        max-width: 1120px;
        padding-top: 2.25rem;
        padding-bottom: 3rem;
    }}
    h1, h2, h3,
    div[data-testid="stMarkdownContainer"] p,
    div[data-testid="stText"],
    label {{
        color: #F4F6F8;
    }}
    h1 {{
        border-bottom: 3px solid {AUBURN_ORANGE};
        padding-bottom: 0.55rem;
    }}
    h2, h3 {{
        border-left: 4px solid {AUBURN_BLUE};
        padding-left: 0.7rem;
    }}
    .dashboard-subtitle {{
        color: #C6CDD5 !important;
        font-size: 1.05rem;
        margin: -0.35rem 0 1.5rem;
    }}
    hr {{
        border-color: #39424D !important;
    }}
    div[data-testid="stMetric"] {{
        background: #242931;
        border: 1px solid #3B4653;
        border-top: 2px solid {AUBURN_BLUE};
        border-left: 4px solid {AUBURN_ORANGE};
        border-radius: 0.6rem;
        box-shadow: 0 3px 10px rgba(0, 0, 0, 0.18);
        padding: 0.85rem 1rem;
    }}
    div[data-testid="stMetricLabel"],
    div[data-testid="stMetricLabel"] p {{
        color: #C9D0D8 !important;
        font-weight: 650;
    }}
    div[data-testid="stMetricValue"],
    div[data-testid="stMetricValue"] div {{
        color: #F8FAFC !important;
        font-size: clamp(1.15rem, 2.2vw, 1.75rem) !important;
        line-height: 1.25;
        overflow-wrap: anywhere;
        white-space: normal;
    }}
    .flight-category {{
        background: {AUBURN_BLUE};
        border: 1px solid {AUBURN_ORANGE};
        border-radius: 0.6rem;
        box-shadow: 0 3px 10px rgba(0, 0, 0, 0.18);
        color: #F4F6F8;
        display: inline-flex;
        gap: 0.65rem;
        align-items: baseline;
        padding: 0.55rem 0.85rem;
        margin: 0.25rem 0 1.25rem;
    }}
    .flight-category strong {{
        color: {AUBURN_ORANGE};
        font-size: 1.2rem;
    }}
    div[data-testid="stCaptionContainer"],
    div[data-testid="stCaptionContainer"] p,
    small {{
        color: #C2CAD3 !important;
    }}
    div[data-testid="stTextInputRootElement"] {{
        background: #242931 !important;
        border: 1px solid #526171 !important;
        box-shadow: inset 0 0 0 1px rgba(11, 35, 65, 0.35);
    }}
    div[data-testid="stTextInputRootElement"] input {{
        background: #242931 !important;
        color: #F4F6F8 !important;
        caret-color: {AUBURN_ORANGE};
    }}
    div[data-testid="stTextInputRootElement"] input::placeholder {{
        color: #ADB7C2 !important;
        opacity: 1;
    }}
    div[data-testid="stTextInputRootElement"]:focus-within {{
        border-color: {AUBURN_ORANGE} !important;
        box-shadow: 0 0 0 0.2rem rgba(232, 97, 0, 0.35) !important;
    }}
    div[data-testid="stTextInput"] label,
    div[data-testid="stTextInput"] label p,
    div[data-testid="InputInstructions"] {{
        color: #D5DAE0 !important;
    }}
    button[data-testid="stBaseButton-secondaryFormSubmit"],
    div[data-testid="stDownloadButton"] button {{
        background: {AUBURN_ORANGE} !important;
        border: 2px solid {AUBURN_ORANGE} !important;
        color: {AUBURN_BLUE} !important;
        font-weight: 700;
    }}
    button[data-testid="stBaseButton-secondaryFormSubmit"] *,
    div[data-testid="stDownloadButton"] button * {{
        color: inherit !important;
    }}
    button[data-testid="stBaseButton-secondaryFormSubmit"]:hover,
    div[data-testid="stDownloadButton"] button:hover {{
        background: {AUBURN_BLUE} !important;
        border-color: {AUBURN_ORANGE} !important;
        color: #FFFFFF !important;
    }}
    div[data-testid="stExpander"] {{
        background: #242931;
        border: 1px solid #3B4653;
        border-radius: 0.55rem;
    }}
    div[data-testid="stExpander"] summary,
    div[data-testid="stExpander"] summary p,
    div[data-testid="stExpander"] summary span {{
        color: #F4F6F8 !important;
    }}
    div[data-testid="stExpander"] summary svg {{
        fill: #C9D0D8 !important;
        color: #C9D0D8 !important;
    }}
    div[data-testid="stExpander"] summary:focus-visible,
    button:focus-visible {{
        outline: 2px solid {AUBURN_ORANGE} !important;
        outline-offset: 2px;
        box-shadow: 0 0 0 0.2rem rgba(232, 97, 0, 0.35) !important;
    }}
    div[data-testid="stCode"],
    div[data-testid="stJson"] {{
        background: #11161C !important;
        border: 1px solid #3B4653;
        border-radius: 0.55rem;
    }}
    div[data-testid="stCode"] pre,
    div[data-testid="stCode"] code,
    div[data-testid="stCode"] span,
    div[data-testid="stJson"] div,
    div[data-testid="stJson"] span {{
        background: transparent !important;
        color: #F1F4F7 !important;
    }}
    div[data-testid="stDataFrame"] {{
        --gdg-bg-cell: #242931;
        --gdg-bg-header: #1D2229;
        --gdg-bg-header-has-focus: #283340;
        --gdg-bg-header-hovered: #2D3946;
        --gdg-text-dark: #F4F6F8;
        --gdg-text-medium: #D1D7DE;
        --gdg-text-light: #B8C1CB;
        background: #242931;
        border: 1px solid #3B4653;
        border-radius: 0.55rem;
        color: #F4F6F8;
        overflow: hidden;
    }}
    div[data-testid="stAlertContainer"] {{
        background: #242931 !important;
        border: 1px solid #465362;
        border-left: 4px solid {AUBURN_ORANGE};
        color: #F4F6F8 !important;
    }}
    div[data-testid="stAlertContainer"] p,
    div[data-testid="stAlertContainer"] div,
    div[data-testid="stAlertContainer"] span {{
        color: #F4F6F8 !important;
    }}
    div[data-testid="stAlertContainer"] svg {{
        color: {AUBURN_ORANGE} !important;
        fill: {AUBURN_ORANGE} !important;
    }}
    div[data-testid="stSpinner"] p {{
        color: #D5DAE0 !important;
    }}
    a {{
        color: #FF8A3D;
    }}
</style>
"""


def celsius_to_fahrenheit(value: int | float | None) -> float | None:
    """Convert Celsius to Fahrenheit while preserving missing data."""

    if value is None:
        return None
    return (value * 9 / 5) + 32


def knots_to_mph(value: int | float | None) -> float | None:
    """Convert knots to miles per hour while preserving missing data."""

    if value is None:
        return None
    return value * 1.150779448


def statute_miles_to_km(value: str | int | float | None) -> float | None:
    """Convert a numeric statute-mile value to kilometers when possible."""

    if value is None:
        return None
    try:
        miles = float(str(value).removesuffix("+"))
    except ValueError:
        return None
    return miles * 1.609344


def hpa_to_inhg(value: int | float | None) -> float | None:
    """Convert hectopascals to inches of mercury."""

    if value is None:
        return None
    return value * 0.0295299830714


def format_temperature(value: int | float | None) -> str:
    """Format temperature in Celsius and Fahrenheit."""

    converted = celsius_to_fahrenheit(value)
    if value is None or converted is None:
        return "Not reported"
    return f"{value:.1f} °C / {converted:.1f} °F"


def format_speed(value: int | float | None) -> str:
    """Format speed in knots and miles per hour."""

    converted = knots_to_mph(value)
    if value is None or converted is None:
        return "Not reported"
    return f"{value:g} kt / {converted:.1f} mph"


def format_visibility(value: str | int | float | None) -> str:
    """Format visibility in statute miles and kilometers."""

    converted = statute_miles_to_km(value)
    if value is None or converted is None:
        return "Not reported"
    marker = "+" if isinstance(value, str) and value.endswith("+") else ""
    return f"{value} mi / {converted:.1f}{marker} km"


def format_altimeter(value: int | float | None) -> str:
    """Format an altimeter setting in hPa and inHg."""

    converted = hpa_to_inhg(value)
    if value is None or converted is None:
        return "Not reported"
    return f"{value:.1f} hPa / {converted:.2f} inHg"


def format_wind(direction: int | None, speed: int | float | None) -> str:
    """Format available wind direction and sustained speed."""

    if direction is None and speed is None:
        return "Not reported"
    if direction is None:
        return format_speed(speed)
    if speed is None:
        return f"{direction}°"
    return f"{direction}° at {format_speed(speed)}"


def cloud_rows(observation: MetarObservation) -> list[dict[str, object]]:
    """Return cloud layers as plain records for dashboard display."""

    if observation.clouds is None:
        return []
    return [cloud.model_dump(exclude_none=True) for cloud in observation.clouds]


def json_text(data: object) -> str:
    """Serialize downloadable JSON with readable indentation."""

    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def format_hazard_observation(hazard: HazardAssessment) -> str:
    """Format one hazard's structured observation for display."""

    observed = hazard.observed_value
    if hazard.id in {"thunderstorm", "freezing_precipitation"}:
        weather = observed.get("present_weather")
        return str(weather) if weather else "No significant present weather reported"
    if hazard.id == "convective_cloud":
        cloud_types = observed.get("cloud_types")
        if cloud_types is None:
            return "Cloud data unavailable"
        return ", ".join(cloud_types) if cloud_types else "No CB or TCU reported"
    if hazard.id == "wind":
        parts = []
        sustained = observed.get("sustained_kt")
        gust = observed.get("gust_kt")
        if sustained is not None:
            parts.append(f"{sustained:g} kt sustained")
        if gust is not None:
            parts.append(f"{gust:g} kt gust")
        return " / ".join(parts) or "Wind data unavailable"
    if hazard.id == "observation_freshness":
        age = observed.get("age_minutes")
        return "Time unavailable" if age is None else f"{age:g} minutes old"
    return json.dumps(observed, ensure_ascii=False)


def render_operational_assessment(
    assessment: OperationalAssessment,
) -> None:
    """Display centralized project-defined hazard results."""

    st.subheader("Project-defined operational hazard screening")
    alert = {
        ConcernLevel.NOT_TRIGGERED: st.success,
        ConcernLevel.ATTENTION: st.warning,
        ConcernLevel.HIGH_ATTENTION: st.error,
        ConcernLevel.UNAVAILABLE: st.info,
    }[assessment.overall_concern]
    alert(f"Overall concern: {assessment.overall_display_label}")

    st.table(
        [
            {
                "Hazard": hazard.label,
                "Concern": hazard.display_label,
                "Observed": format_hazard_observation(hazard),
                "Trigger": hazard.trigger,
            }
            for hazard in assessment.hazards
        ]
    )

    with st.expander("Hazard sources and operational context"):
        for hazard in assessment.hazards:
            st.markdown(f"**{hazard.label}: {hazard.display_label}**")
            st.write(hazard.operational_judgment)
            if hazard.confidence_note:
                st.caption(hazard.confidence_note)
            for source in hazard.source_basis:
                st.markdown(f"- [{source.title}]({source.url}): {source.relevance}")

    if not assessment.data_complete:
        unavailable = ", ".join(
            hazard.label
            for hazard in assessment.hazards
            if not hazard.data_complete
        )
        category_note = (
            "official flight category; "
            if not assessment.flight_category.data_complete
            else ""
        )
        st.warning(
            f"Incomplete assessment data: {category_note}{unavailable or 'none'}."
        )

    st.info(assessment.disclaimer)


def main() -> None:
    """Configure and run the interactive Streamlit dashboard."""

    configure_logging(verbose=False, log_file=None)
    st.set_page_config(
        page_title="Aviation Weather METAR Dashboard",
        page_icon="✈️",
        layout="wide",
    )
    st.markdown(AUBURN_STYLES, unsafe_allow_html=True)
    st.title("✈ Aviation Weather METAR Dashboard")
    st.markdown(
        '<p class="dashboard-subtitle">Current airport weather from the '
        "Aviation Weather Center, presented in aviation and familiar units.</p>",
        unsafe_allow_html=True,
    )

    with st.form("metar-request"):
        airport = st.text_input(
            "ICAO identifier",
            value="KATL",
            max_chars=4,
            help=(
                "Enter a four-character ICAO identifier such as KATL, not "
                "the three-letter IATA code ATL."
            ),
        )
        submitted = st.form_submit_button("Load weather")

    if submitted:
        st.session_state.pop("metar_result", None)
        try:
            with st.spinner("Loading the latest METAR..."):
                st.session_state["metar_result"] = retrieve_metar(airport)
        except (
            AirportValidationError,
            MetarApiError,
            MetarDataValidationError,
        ) as exc:
            st.error(str(exc))
            return

    result = st.session_state.get("metar_result")
    if result is None:
        return

    st.divider()
    render_result(result)


def render_result(result: MetarResult) -> None:
    """Render one retrieved METAR result and its downloads."""

    observation = result.observation
    station_name = observation.airport_name or "Unknown station"

    st.subheader(f"{station_name} ({observation.icao_id})")
    st.caption(f"Report time: {observation.report_time}")
    category_result = result.operational_assessment.flight_category
    category = escape(category_result.category.value)
    st.markdown(
        f'<div class="flight-category"><span>Official weather category</span>'
        f"<strong>{category}</strong></div>",
        unsafe_allow_html=True,
    )
    st.caption(category_result.operational_judgment)

    render_operational_assessment(result.operational_assessment)

    st.subheader("Current conditions")
    temperature, dewpoint = st.columns(2)
    temperature.metric(
        "Temperature", format_temperature(observation.temperature_c)
    )
    dewpoint.metric("Dew point", format_temperature(observation.dewpoint_c))

    visibility, wind = st.columns(2)
    visibility.metric(
        "Visibility", format_visibility(observation.visibility_miles)
    )
    wind.metric(
        "Wind",
        format_wind(observation.wind_direction_deg, observation.wind_speed_kt),
    )

    gusts, altimeter = st.columns(2)
    gusts.metric("Wind gusts", format_speed(observation.wind_gust_kt))
    altimeter.metric(
        "Altimeter", format_altimeter(observation.altimeter_hpa)
    )

    st.divider()
    st.subheader("Cloud layers")
    clouds = cloud_rows(observation)
    if clouds:
        st.dataframe(
            clouds,
            hide_index=True,
            width="stretch",
            column_config={
                "cover": "Coverage",
                "base": st.column_config.NumberColumn("Base (ft)"),
            },
        )
    else:
        st.info("No cloud layers were reported.")

    st.subheader("Raw METAR observation")
    st.code(observation.raw_metar, language=None)

    st.subheader("JSON data and downloads")
    with st.expander("Complete raw API JSON"):
        st.json(result.raw_observations)
    with st.expander("Processed METAR JSON"):
        st.json(result.processed)

    raw_download, processed_download = st.columns(2)
    raw_download.download_button(
        "Download raw JSON",
        data=json_text(result.raw_observations),
        file_name=f"{result.airport}_metar_raw.json",
        mime="application/json",
    )
    processed_download.download_button(
        "Download processed JSON",
        data=json_text(result.processed),
        file_name=f"{result.airport}_metar_processed.json",
        mime="application/json",
    )


if __name__ == "__main__":
    main()
