import argparse
import json
import re
import sys
from pathlib import Path

import requests


METAR_URL = "https://aviationweather.gov/api/data/metar"


def icao_identifier(value: str) -> str:
    airport = value.upper()
    if not re.fullmatch(r"[A-Z0-9]{4}", airport):
        raise argparse.ArgumentTypeError(
            "airport must be a four-character ICAO identifier containing only A-Z and 0-9 (for example KATL)"
        )
    return airport


def main() -> None:
    parser = argparse.ArgumentParser(description="Retrieve the latest METAR observation.")
    parser.add_argument(
        "airport",
        type=icao_identifier,
        help="four-character ICAO identifier (for example KATL, not the IATA code ATL)",
    )
    args = parser.parse_args()

    try:
        response = requests.get(
            METAR_URL,
            params={"ids": args.airport, "format": "json"},
            headers={"User-Agent": "aviation-weather-support/0.1.0 METAR CLI"},
            timeout=10,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        print(f"Error: unable to retrieve METAR for {args.airport}: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    try:
        observations = response.json()
    except (requests.exceptions.JSONDecodeError, json.JSONDecodeError, ValueError) as exc:
        print("Error: the METAR API returned invalid JSON.", file=sys.stderr)
        raise SystemExit(1) from exc

    if not isinstance(observations, list) or not any(
        isinstance(observation, dict) and observation for observation in observations
    ):
        print(f"Error: no METAR observation found for {args.airport}.", file=sys.stderr)
        raise SystemExit(1)

    observation = next(
        observation
        for observation in observations
        if isinstance(observation, dict) and observation
    )
    processed = {
        "icao_id": observation.get("icaoId"),
        "airport_name": observation.get("name"),
        "report_time": observation.get("reportTime"),
        "raw_metar": observation.get("rawOb"),
        "temperature_c": observation.get("temp"),
        "dewpoint_c": observation.get("dewp"),
        "wind_direction_deg": observation.get("wdir"),
        "wind_speed_kt": observation.get("wspd"),
        "wind_gust_kt": observation.get("wgst"),
        "visibility_miles": observation.get("visib"),
        "altimeter_hpa": observation.get("altim"),
        "flight_category": observation.get("fltCat"),
        "clouds": observation.get("clouds"),
    }

    raw_path = Path("data/raw") / f"{args.airport}_metar_raw.json"
    processed_path = Path("data/processed") / f"{args.airport}_metar_processed.json"

    try:
        raw_path.parent.mkdir(parents=True, exist_ok=True)
        processed_path.parent.mkdir(parents=True, exist_ok=True)
        raw_path.write_text(json.dumps(observations, indent=2), encoding="utf-8")
        processed_path.write_text(json.dumps(processed, indent=2), encoding="utf-8")
    except OSError as exc:
        print(f"Error: unable to save METAR files: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    print(f"Saved METAR data for {args.airport}.")
    print(f"Raw file: {raw_path}")
    print(f"Processed file: {processed_path}")
