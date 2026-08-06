"""Command-line entry points for METAR retrieval and report generation."""

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Sequence

from aviation_weather_support.api import MetarApiError
from aviation_weather_support.logging_config import (
    LoggingSetupError,
    configure_logging,
)
from aviation_weather_support.models import MetarDataValidationError
from aviation_weather_support.operational_rules import INFORMATIONAL_DISCLAIMER
from aviation_weather_support.reporting import (
    GeneratedReport,
    ReportWorkflowError,
    create_live_report,
    replay_report,
)
from aviation_weather_support.workflow import (
    AirportValidationError,
    normalize_airport,
    retrieve_metar,
)


logger = logging.getLogger(__name__)


def icao_identifier(value: str) -> str:
    """Convert an argparse value to a validated ICAO identifier."""

    try:
        return normalize_airport(value)
    except AirportValidationError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


def main(argv: Sequence[str] | None = None) -> None:
    """Run either the existing METAR command or the report subcommand."""

    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments and arguments[0] == "report":
        _report_main(arguments[1:])
        return
    _standard_main(arguments)


def _standard_main(argv: Sequence[str]) -> None:
    """Run the original METAR retrieval and JSON-saving command."""

    parser = argparse.ArgumentParser(
        description=(
            "Retrieve and assess the latest METAR observation, then save raw "
            "and processed JSON output."
        ),
        epilog=(
            f"Use 'aviation-weather-support report --help' for PDF reports. "
            f"{INFORMATIONAL_DISCLAIMER}"
        ),
    )
    parser.add_argument(
        "airport",
        type=icao_identifier,
        help="four-character ICAO identifier (for example KATL, not the IATA code ATL)",
    )
    _add_logging_arguments(parser)
    args = parser.parse_args(argv)
    _configure_cli_logging(args)

    try:
        result = retrieve_metar(args.airport)
    except (MetarApiError, MetarDataValidationError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    raw_path = Path("data/raw") / f"{args.airport}_metar_raw.json"
    processed_path = Path("data/processed") / f"{args.airport}_metar_processed.json"
    logger.debug("Raw output path: %s", raw_path)
    logger.debug("Processed output path: %s", processed_path)

    try:
        raw_path.parent.mkdir(parents=True, exist_ok=True)
        processed_path.parent.mkdir(parents=True, exist_ok=True)
        raw_path.write_text(
            json.dumps(result.raw_observations, indent=2), encoding="utf-8"
        )
        logger.info("Raw METAR response written to %s", raw_path)
        processed_path.write_text(
            json.dumps(result.processed, indent=2), encoding="utf-8"
        )
        logger.info("Processed METAR data written to %s", processed_path)
    except OSError as exc:
        logger.error(
            "Could not write METAR output files %s and %s: %s",
            raw_path,
            processed_path,
            exc,
        )
        print(f"Error: unable to save METAR files: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    print(f"Saved METAR data for {args.airport}.")
    print(f"Raw file: {raw_path}")
    print(f"Processed file: {processed_path}")


def _report_main(argv: Sequence[str]) -> None:
    """Run live or replay report generation."""

    parser = argparse.ArgumentParser(
        prog="aviation-weather-support report",
        description=(
            "Create a reproducible Quarto PDF from a live METAR or saved raw "
            "report evidence."
        ),
        epilog=INFORMATIONAL_DISCLAIMER,
    )
    parser.add_argument(
        "station",
        nargs="?",
        type=icao_identifier,
        help="four-character ICAO identifier for live report mode",
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=None,
        metavar="SAVED-RAW-JSON",
        help="replay a raw evidence file without contacting the live API",
    )
    _add_logging_arguments(parser)
    args = parser.parse_args(argv)
    if (args.station is None) == (args.input is None):
        parser.error("provide either a station or --input, but not both")
    _configure_cli_logging(args)

    project_root = Path.cwd().resolve()
    try:
        if args.input is not None:
            generated = replay_report(project_root, args.input)
        else:
            generated = create_live_report(project_root, args.station)
    except MetarApiError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        print("No raw evidence, processed result, or PDF was generated.", file=sys.stderr)
        raise SystemExit(1) from exc
    except ReportWorkflowError as exc:
        _print_report_failure(exc, project_root)
        raise SystemExit(1) from exc

    _print_report_success(generated, project_root)


def _add_logging_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="show operational INFO messages in the console",
    )
    parser.add_argument(
        "--log-file",
        type=Path,
        default=None,
        metavar="PATH",
        help="write detailed DEBUG logs to PATH",
    )


def _configure_cli_logging(args: argparse.Namespace) -> None:
    try:
        configure_logging(verbose=args.verbose, log_file=args.log_file)
    except LoggingSetupError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


def _print_report_success(generated: GeneratedReport, project_root: Path) -> None:
    print(f"Generated METAR report for {generated.result.airport}.")
    print(f"Raw evidence file: {_display_path(project_root, generated.raw_path)}")
    print(f"Processed file: {_display_path(project_root, generated.processed_path)}")
    print(f"PDF file: {_display_path(project_root, generated.pdf_path)}")


def _print_report_failure(error: ReportWorkflowError, project_root: Path) -> None:
    print(f"Error: {error}", file=sys.stderr)
    if error.raw_path is not None:
        print(
            "Raw response preserved: "
            f"{_display_path(project_root, error.raw_path)}",
            file=sys.stderr,
        )
    else:
        print("Raw evidence was not generated.", file=sys.stderr)
    if error.processed_path is not None:
        print(
            "Processed result preserved: "
            f"{_display_path(project_root, error.processed_path)}",
            file=sys.stderr,
        )
    else:
        print("Processed result was not generated.", file=sys.stderr)
    print("PDF was not generated.", file=sys.stderr)


def _display_path(project_root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(project_root.resolve()).as_posix()
    except ValueError:
        return path.resolve().as_posix()
