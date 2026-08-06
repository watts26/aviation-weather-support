"""Prepare reproducible offline, live, and replay METAR reports."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from importlib.resources import as_file, files
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from aviation_weather_support.api import fetch_metar
from aviation_weather_support.models import (
    MetarDataValidationError,
    MetarObservation,
    validate_metar_observation,
)
from aviation_weather_support.operational_rules import (
    OperationalAssessment,
    assess_current_conditions,
    parse_observation_time,
)
from aviation_weather_support.workflow import (
    MetarResult,
    normalize_airport,
    process_metar_observations,
)


DEFAULT_REPORT_STATION = "KATL"
DEFAULT_REPORT_EVALUATED_AT = "2026-07-29T20:00:00Z"
RAW_REPORT_DIRECTORY = Path("data/reports/raw")
PROCESSED_REPORT_DIRECTORY = Path("data/reports/processed")
PDF_REPORT_DIRECTORY = Path("output/pdf")
REPORT_SCHEMA_VERSION = 1
PACKAGED_REPORT_SOURCE = "resources/quarto/practicum-6.qmd"
PACKAGED_FIXTURE_DIRECTORY = "resources/fixtures"


class OfflineReportDataError(ValueError):
    """Raised when deterministic offline report input cannot be used."""


class ReportWorkflowError(RuntimeError):
    """Raised when report generation stops after zero or more artifacts exist."""

    def __init__(
        self,
        message: str,
        *,
        raw_path: Path | None = None,
        processed_path: Path | None = None,
    ) -> None:
        super().__init__(message)
        self.raw_path = raw_path
        self.processed_path = processed_path


class SavedRawEvidence(BaseModel):
    """Portable evidence envelope containing an unchanged AWC JSON response."""

    model_config = ConfigDict(frozen=True)

    schema_version: Literal[1] = REPORT_SCHEMA_VERSION
    requested_station: str = Field(pattern=r"^[A-Z0-9]{4}$")
    retrieved_at: datetime
    evaluated_at: datetime
    api_response: list[object]

    @field_validator("retrieved_at", "evaluated_at")
    @classmethod
    def require_aware_timestamp(cls, value: datetime) -> datetime:
        """Require evidence timestamps to be timezone-aware and store UTC."""

        if value.tzinfo is None:
            raise ValueError("must include a UTC offset")
        return value.astimezone(timezone.utc)


@dataclass(frozen=True)
class OfflineReportData:
    """Validated fixture and deterministic assessment used by a report."""

    station: str
    fixture_reference: str
    observation: MetarObservation
    assessment: OperationalAssessment


@dataclass(frozen=True)
class ReportRenderData:
    """Validated observation, assessment, and provenance displayed by Quarto."""

    station: str
    observation: MetarObservation
    assessment: OperationalAssessment
    evaluated_at: datetime
    retrieved_at: datetime | None
    raw_source_path: Path | None
    processed_source_path: Path | None
    raw_source_reference: str | None = None

    @property
    def observation_time(self) -> datetime | None:
        """Return the structured METAR observation time in UTC when usable."""

        return parse_observation_time(self.observation.observation_time)


@dataclass(frozen=True)
class ReportHeader:
    """Human-readable validated metadata displayed at the top of a report."""

    report_date: str
    station: str
    observation_time: str
    evaluated_at: str
    overall_concern: str
    flight_category: str


@dataclass(frozen=True)
class GeneratedReport:
    """Paths and data produced by one successful live or replay report."""

    raw_path: Path
    processed_path: Path
    pdf_path: Path
    result: MetarResult
    retrieved_at: datetime


def build_report_header(report_data: ReportRenderData) -> ReportHeader:
    """Build the visible report header from validated render data."""

    observation_time = report_data.observation_time
    return ReportHeader(
        report_date=_format_report_date(report_data.evaluated_at),
        station=report_data.observation.icao_id,
        observation_time=(
            _format_report_datetime(observation_time)
            if observation_time is not None
            else "Unavailable"
        ),
        evaluated_at=_format_report_datetime(report_data.evaluated_at),
        overall_concern=report_data.assessment.overall_display_label,
        flight_category=report_data.assessment.flight_category.category.value,
    )


def normalize_report_station(value: object) -> str:
    """Normalize and validate a four-character ICAO report parameter."""

    if not isinstance(value, str):
        raise OfflineReportDataError(
            "Report parameter 'station' must be a four-character ICAO identifier."
        )
    station = value.strip().upper()
    if not re.fullmatch(r"[A-Z0-9]{4}", station):
        raise OfflineReportDataError(
            "Report parameter 'station' must be a four-character ICAO identifier "
            "containing only A-Z and 0-9."
        )
    return station


def fixture_resource_for_station(station: object):
    """Return the packaged offline fixture resource for one station."""

    normalized = normalize_report_station(station)
    return files("aviation_weather_support").joinpath(
        PACKAGED_FIXTURE_DIRECTORY,
        f"metar-{normalized.lower()}-success.json",
    )


def report_template_resource():
    """Return the packaged Quarto report template resource."""

    return files("aviation_weather_support").joinpath(PACKAGED_REPORT_SOURCE)


def parse_report_evaluated_at(value: object) -> datetime:
    """Parse a timezone-aware report evaluation timestamp and normalize to UTC."""

    if not isinstance(value, str):
        raise OfflineReportDataError(
            "Report parameter 'evaluated_at' must be an ISO 8601 timestamp with a "
            "UTC offset."
        )
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise OfflineReportDataError(
            "Report parameter 'evaluated_at' must be a valid ISO 8601 timestamp "
            "with a UTC offset."
        ) from exc
    if parsed.tzinfo is None:
        raise OfflineReportDataError(
            "Report parameter 'evaluated_at' must include a UTC offset."
        )
    return parsed.astimezone(timezone.utc)


def load_offline_report_data(
    project_root: Path, *, station: object, evaluated_at: object
) -> OfflineReportData:
    """Load, validate, and deterministically assess one committed fixture."""

    normalized = normalize_report_station(station)
    fixture_resource = fixture_resource_for_station(normalized)
    fixture_reference = (
        "package:aviation_weather_support/"
        f"{PACKAGED_FIXTURE_DIRECTORY}/metar-{normalized.lower()}-success.json"
    )
    if not fixture_resource.is_file():
        raise OfflineReportDataError(
            f"No committed METAR fixture was found for {normalized} at "
            f"{fixture_reference}. Report rendering is offline; this installed "
            "package does not include a fixture for that station."
        )

    try:
        raw_observations = json.loads(fixture_resource.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise OfflineReportDataError(
            f"Committed METAR fixture could not be read: {fixture_reference}."
        ) from exc
    if not isinstance(raw_observations, list) or not raw_observations:
        raise OfflineReportDataError(
            f"Committed METAR fixture contains no observations: {fixture_reference}."
        )
    observation = validate_metar_observation(raw_observations)
    if observation.icao_id != normalized:
        raise OfflineReportDataError(
            f"Committed fixture station mismatch: requested {normalized}, but "
            f"{fixture_resource.name} contains {observation.icao_id}."
        )

    assessment = assess_current_conditions(
        observation,
        evaluated_at=parse_report_evaluated_at(evaluated_at),
    )
    return OfflineReportData(
        station=normalized,
        fixture_reference=fixture_reference,
        observation=observation,
        assessment=assessment,
    )


def portable_source_path(project_root: Path, path: Path) -> str:
    """Return a repository-relative source reference when the path is in-project."""

    resolved_root = project_root.resolve()
    resolved_path = path.resolve()
    try:
        return resolved_path.relative_to(resolved_root).as_posix()
    except ValueError:
        return resolved_path.as_posix()


def create_live_report(
    project_root: Path,
    station: str,
    *,
    clock: Callable[[], datetime] | None = None,
    fetcher: Callable[[str], list[object]] | None = None,
    renderer: Callable[..., None] | None = None,
) -> GeneratedReport:
    """Fetch, preserve, process, and render one current METAR report."""

    normalized = normalize_airport(station)
    fetch = fetcher or fetch_metar
    raw_observations = fetch(normalized)
    now = (clock or (lambda: datetime.now(timezone.utc)))()
    if now.tzinfo is None:
        raise ReportWorkflowError("The report retrieval timestamp must be timezone-aware.")
    retrieved_at = now.astimezone(timezone.utc)
    raw_path = _raw_path(project_root, normalized, retrieved_at)
    evidence = SavedRawEvidence(
        requested_station=normalized,
        retrieved_at=retrieved_at,
        evaluated_at=retrieved_at,
        api_response=raw_observations,
    )
    try:
        _write_json(raw_path, evidence.model_dump(mode="json"))
    except OSError as exc:
        raise ReportWorkflowError(
            f"Unable to preserve the raw METAR response: {exc}"
        ) from exc

    return _process_and_render(
        project_root,
        evidence=evidence,
        raw_path=raw_path,
        renderer=renderer,
    )


def replay_report(
    project_root: Path,
    input_path: Path,
    *,
    renderer: Callable[..., None] | None = None,
) -> GeneratedReport:
    """Recreate a processed assessment and PDF without contacting the API."""

    raw_path = input_path.resolve()
    try:
        evidence = load_raw_evidence(raw_path)
    except ReportWorkflowError as exc:
        raise ReportWorkflowError(str(exc), raw_path=raw_path) from exc
    return _process_and_render(
        project_root,
        evidence=evidence,
        raw_path=raw_path,
        renderer=renderer,
    )


def load_raw_evidence(path: Path) -> SavedRawEvidence:
    """Load and validate a saved live-report evidence envelope."""

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        evidence = SavedRawEvidence.model_validate(payload)
    except OSError as exc:
        raise ReportWorkflowError(f"Unable to read raw evidence file {path}: {exc}") from exc
    except (json.JSONDecodeError, ValidationError) as exc:
        raise ReportWorkflowError(
            f"Raw evidence file is malformed or incomplete: {path}."
        ) from exc
    if not evidence.api_response:
        raise ReportWorkflowError(
            f"Raw evidence file contains no METAR observations: {path}."
        )
    return evidence


def load_report_render_data(
    project_root: Path,
    *,
    station: object,
    evaluated_at: object,
    raw_input_path: object = "",
    processed_input_path: object = "",
) -> ReportRenderData:
    """Load either the committed default or a saved live/replay report pair."""

    raw_value = str(raw_input_path).strip() if raw_input_path is not None else ""
    processed_value = (
        str(processed_input_path).strip()
        if processed_input_path is not None
        else ""
    )
    if not raw_value and not processed_value:
        offline = load_offline_report_data(
            project_root,
            station=station,
            evaluated_at=evaluated_at,
        )
        return ReportRenderData(
            station=offline.station,
            observation=offline.observation,
            assessment=offline.assessment,
            evaluated_at=offline.assessment.evaluated_at,
            retrieved_at=None,
            raw_source_path=None,
            processed_source_path=None,
            raw_source_reference=offline.fixture_reference,
        )
    if not raw_value or not processed_value:
        raise OfflineReportDataError(
            "Report parameters 'raw_input_path' and 'processed_input_path' must "
            "be provided together."
        )

    raw_path = Path(raw_value).resolve()
    processed_path = Path(processed_value).resolve()
    try:
        evidence = load_raw_evidence(raw_path)
    except ReportWorkflowError as exc:
        raise OfflineReportDataError(str(exc)) from exc
    normalized = normalize_report_station(station)
    parsed_evaluated_at = parse_report_evaluated_at(evaluated_at)
    if evidence.requested_station != normalized:
        raise OfflineReportDataError(
            f"Saved evidence station mismatch: requested {normalized}, but the "
            f"evidence contains {evidence.requested_station}."
        )
    if evidence.evaluated_at != parsed_evaluated_at:
        raise OfflineReportDataError(
            "The Quarto evaluated_at parameter does not match the saved raw evidence."
        )

    try:
        processed = json.loads(processed_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise OfflineReportDataError(
            f"Processed report data could not be read: {processed_path}."
        ) from exc
    if not isinstance(processed, dict):
        raise OfflineReportDataError("Processed report data must be a JSON object.")

    try:
        result = process_metar_observations(
            normalized,
            evidence.api_response,
            evaluated_at=parsed_evaluated_at,
        )
    except (MetarDataValidationError, ValueError) as exc:
        raise OfflineReportDataError(str(exc)) from exc
    expected = dict(result.processed)
    metadata = processed.get("report_metadata")
    expected["report_metadata"] = metadata
    if processed != expected or not isinstance(metadata, dict):
        raise OfflineReportDataError(
            "The saved processed report does not match the validated raw evidence."
        )
    _validate_report_metadata(
        metadata,
        project_root=project_root,
        raw_path=raw_path,
        processed_path=processed_path,
        result=result,
        evidence=evidence,
    )
    assessment = OperationalAssessment.model_validate(
        processed["operational_assessment"]
    )
    return ReportRenderData(
        station=normalized,
        observation=result.observation,
        assessment=assessment,
        evaluated_at=parsed_evaluated_at,
        retrieved_at=evidence.retrieved_at,
        raw_source_path=raw_path,
        processed_source_path=processed_path,
    )


def render_report_pdf(
    project_root: Path,
    *,
    station: str,
    evaluated_at: datetime,
    raw_path: Path,
    processed_path: Path,
    pdf_path: Path,
) -> None:
    """Render to a temporary PDF and replace the same-observation destination."""

    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    environment = os.environ.copy()
    environment["SOURCE_DATE_EPOCH"] = str(int(evaluated_at.timestamp()))
    environment["QUARTO_PYTHON"] = sys.executable
    try:
        _render_packaged_quarto(
            project_root,
            station=station,
            evaluated_at=evaluated_at,
            raw_input_path=raw_path,
            processed_input_path=processed_path,
            pdf_path=pdf_path,
            environment=environment,
        )
    except OSError as exc:
        raise ReportWorkflowError(f"Unable to render the Quarto PDF: {exc}") from exc
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or str(exc)).strip()
        raise ReportWorkflowError(f"Quarto PDF rendering failed: {detail}") from exc


def render_fixture_report(
    output_root: Path,
    station: str = DEFAULT_REPORT_STATION,
    *,
    evaluated_at: str = DEFAULT_REPORT_EVALUATED_AT,
) -> Path:
    """Render the packaged deterministic fixture without contacting the API."""

    normalized = normalize_report_station(station)
    evaluated = parse_report_evaluated_at(evaluated_at)
    load_offline_report_data(
        output_root, station=normalized, evaluated_at=evaluated_at
    )
    pdf_path = output_root / PDF_REPORT_DIRECTORY / "practicum-6.pdf"
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    environment = os.environ.copy()
    environment["SOURCE_DATE_EPOCH"] = str(int(evaluated.timestamp()))
    environment["QUARTO_PYTHON"] = sys.executable
    try:
        _render_packaged_quarto(
            output_root,
            station=normalized,
            evaluated_at=evaluated,
            raw_input_path=None,
            processed_input_path=None,
            pdf_path=pdf_path,
            environment=environment,
        )
    except OSError as exc:
        raise ReportWorkflowError(f"Unable to render the Quarto PDF: {exc}") from exc
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or str(exc)).strip()
        raise ReportWorkflowError(f"Quarto PDF rendering failed: {detail}") from exc
    return pdf_path


def _render_packaged_quarto(
    output_root: Path,
    *,
    station: str,
    evaluated_at: datetime,
    raw_input_path: Path | None,
    processed_input_path: Path | None,
    pdf_path: Path,
    environment: dict[str, str],
) -> None:
    """Render the packaged QMD while its resource context remains active."""

    with as_file(report_template_resource()) as packaged_source:
        with tempfile.TemporaryDirectory(
            prefix="quarto-report-", dir=pdf_path.parent
        ) as temporary_directory:
            temporary_path = Path(temporary_directory)
            report_source = temporary_path / "practicum-6.qmd"
            shutil.copy2(packaged_source, report_source)
            command = [
                "quarto",
                "render",
                str(report_source),
                "--to",
                "pdf",
                "--output-dir",
                ".",
                "-P",
                f"station:{station}",
                "-P",
                f"evaluated_at:{_isoformat_utc(evaluated_at)}",
                "-P",
                f"artifact_root:{output_root.resolve().as_posix()}",
                "-P",
                "raw_input_path:"
                + (raw_input_path.resolve().as_posix() if raw_input_path else ""),
                "-P",
                "processed_input_path:"
                + (
                    processed_input_path.resolve().as_posix()
                    if processed_input_path
                    else ""
                ),
            ]
            subprocess.run(
                command,
                cwd=temporary_path,
                env=environment,
                check=True,
                capture_output=True,
                text=True,
            )
            rendered = temporary_path / "practicum-6.pdf"
            if not rendered.is_file():
                raise ReportWorkflowError(
                    "Quarto completed without producing the expected PDF."
                )
            rendered.replace(pdf_path)


def _process_and_render(
    project_root: Path,
    *,
    evidence: SavedRawEvidence,
    raw_path: Path,
    renderer: Callable[..., None] | None,
) -> GeneratedReport:
    """Process preserved evidence, write its assessment, and render its PDF."""

    try:
        result = process_metar_observations(
            evidence.requested_station,
            evidence.api_response,
            evaluated_at=evidence.evaluated_at,
        )
        observation_time = parse_observation_time(result.observation.observation_time)
        if observation_time is None:
            raise MetarDataValidationError(
                "METAR observation time is unavailable or malformed; a "
                "reproducible report cannot be generated."
            )
    except (MetarDataValidationError, ValueError, StopIteration) as exc:
        raise ReportWorkflowError(str(exc), raw_path=raw_path) from exc

    processed_path = _processed_path(
        project_root, evidence.requested_station, evidence.retrieved_at
    )
    pdf_path = _pdf_path(
        project_root, evidence.requested_station, observation_time
    )
    processed = dict(result.processed)
    processed["report_metadata"] = {
        "schema_version": REPORT_SCHEMA_VERSION,
        "station": evidence.requested_station,
        "observation_time": _isoformat_utc(observation_time),
        "retrieved_at": _isoformat_utc(evidence.retrieved_at),
        "evaluated_at": _isoformat_utc(evidence.evaluated_at),
        "raw_source_path": portable_source_path(project_root, raw_path),
        "processed_source_path": portable_source_path(project_root, processed_path),
        "pdf_path": portable_source_path(project_root, pdf_path),
    }
    try:
        _write_json(processed_path, processed)
    except OSError as exc:
        raise ReportWorkflowError(
            f"Unable to save the processed report data: {exc}",
            raw_path=raw_path,
        ) from exc

    render = renderer or render_report_pdf
    try:
        render(
            project_root,
            station=evidence.requested_station,
            evaluated_at=evidence.evaluated_at,
            raw_path=raw_path,
            processed_path=processed_path,
            pdf_path=pdf_path,
        )
    except ReportWorkflowError as exc:
        raise ReportWorkflowError(
            str(exc), raw_path=raw_path, processed_path=processed_path
        ) from exc
    except Exception as exc:
        raise ReportWorkflowError(
            f"Quarto PDF rendering failed: {exc}",
            raw_path=raw_path,
            processed_path=processed_path,
        ) from exc

    return GeneratedReport(
        raw_path=raw_path,
        processed_path=processed_path,
        pdf_path=pdf_path,
        result=result,
        retrieved_at=evidence.retrieved_at,
    )


def _validate_report_metadata(
    metadata: dict[str, object],
    *,
    project_root: Path,
    raw_path: Path,
    processed_path: Path,
    result: MetarResult,
    evidence: SavedRawEvidence,
) -> None:
    """Require saved provenance to describe the exact inputs being rendered."""

    observation_time = parse_observation_time(result.observation.observation_time)
    expected = {
        "schema_version": REPORT_SCHEMA_VERSION,
        "station": result.airport,
        "observation_time": (
            _isoformat_utc(observation_time) if observation_time else None
        ),
        "retrieved_at": _isoformat_utc(evidence.retrieved_at),
        "evaluated_at": _isoformat_utc(evidence.evaluated_at),
        "raw_source_path": portable_source_path(project_root, raw_path),
        "processed_source_path": portable_source_path(project_root, processed_path),
        "pdf_path": portable_source_path(
            project_root,
            _pdf_path(project_root, result.airport, observation_time),
        ) if observation_time else None,
    }
    if metadata != expected:
        raise OfflineReportDataError(
            "The saved processed report provenance does not match its source files."
        )


def _raw_path(project_root: Path, station: str, retrieved_at: datetime) -> Path:
    return (
        project_root
        / RAW_REPORT_DIRECTORY
        / f"{station}_{_filename_timestamp(retrieved_at, fractional=True)}_metar_raw.json"
    )


def _processed_path(
    project_root: Path, station: str, retrieved_at: datetime
) -> Path:
    return (
        project_root
        / PROCESSED_REPORT_DIRECTORY
        / f"{station}_{_filename_timestamp(retrieved_at, fractional=True)}_metar_processed.json"
    )


def _pdf_path(project_root: Path, station: str, observation_time: datetime) -> Path:
    return (
        project_root
        / PDF_REPORT_DIRECTORY
        / f"{station}_{_filename_timestamp(observation_time)}_metar_report.pdf"
    )


def _filename_timestamp(value: datetime, *, fractional: bool = False) -> str:
    utc_value = value.astimezone(timezone.utc)
    if fractional:
        return utc_value.strftime("%Y%m%dT%H%M%S%fZ")
    return utc_value.strftime("%Y%m%dT%H%M%SZ")


def _isoformat_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _format_report_date(value: datetime) -> str:
    utc_value = value.astimezone(timezone.utc)
    return f"{utc_value.strftime('%B')} {utc_value.day}, {utc_value.year}"


def _format_report_datetime(value: datetime) -> str:
    utc_value = value.astimezone(timezone.utc)
    clock_time = utc_value.strftime("%I:%M %p").lstrip("0")
    return f"{_format_report_date(utc_value)} at {clock_time} UTC"


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
