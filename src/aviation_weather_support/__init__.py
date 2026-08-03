"""Command-line entry point for retrieving and saving assessed METAR data."""

import argparse
import json
import logging
import sys
from pathlib import Path

from aviation_weather_support.api import MetarApiError
from aviation_weather_support.logging_config import (
    LoggingSetupError,
    configure_logging,
)
from aviation_weather_support.models import MetarDataValidationError
from aviation_weather_support.operational import INFORMATIONAL_DISCLAIMER
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


def main() -> None:
    """Run the METAR retrieval, assessment, and JSON-saving CLI."""

    parser = argparse.ArgumentParser(
        description=(
            "Retrieve and assess the latest METAR observation, then save raw "
            "and processed JSON output."
        ),
        epilog=INFORMATIONAL_DISCLAIMER,
    )
    parser.add_argument(
        "airport",
        type=icao_identifier,
        help="four-character ICAO identifier (for example KATL, not the IATA code ATL)",
    )
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
    args = parser.parse_args()

    try:
        configure_logging(verbose=args.verbose, log_file=args.log_file)
    except LoggingSetupError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

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
