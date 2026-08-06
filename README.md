# Aviation Weather Support

## Project overview

Aviation Weather Support retrieves and validates the latest airport METAR, then translates it into an official flight category and clearer project-defined operational flags. Intended users: Aviation students and other users who want a clearer, structured view of current airport weather. Results are informational, not official flight guidance.

## Quick start

Python 3.10 or newer and internet access for live retrieval are required.

No API key or environment variable is required. PDF report generation also requires Quarto with a working PDF engine.

Install the core CLI from PyPI:

```console
pip install aviation-weather-support
aviation-weather-support KATL
```

Install optional features as needed:

```console
pip install "aviation-weather-support[dashboard]"
pip install "aviation-weather-support[report]"
pip install "aviation-weather-support[all]"
```

Launch installed features:

```console
aviation-weather-support dashboard
aviation-weather-support report KATL
aviation-weather-support report --fixture KATL
```

For contributor development, clone the project and sync the locked dependencies with [`uv`](https://docs.astral.sh/uv/):

```console
git clone https://github.com/watts26/aviation-weather-support.git
cd aviation-weather-support
uv sync
```

Run the development CLI:

```console
uv run aviation-weather-support KATL
```

Launch Streamlit directly during development:

```console
uv run streamlit run src/aviation_weather_support/dashboard.py
```

Generate a live PDF during development:

```console
uv run aviation-weather-support report KATL
```

Useful CLI options:

```console
uv run aviation-weather-support --help
uv run aviation-weather-support KATL --verbose
uv run aviation-weather-support KATL --log-file logs/aviation-weather-support.log
```

Use a four-character ICAO identifier such as `KATL`, not a three-letter IATA code such as `ATL`. The live data source is the [Aviation Weather Center Data API](https://aviationweather.gov/data/api/).

## Main features

- Retrieves the latest METAR for a requested airport.
- Validates the response and explains retrieval, data, and station-mismatch failures clearly.
- Assigns the official flight category from structured ceiling and visibility data.
- Applies project-defined hazard screening for thunderstorms, convective clouds, freezing precipitation, wind, and observation freshness.
- Preserves raw API data separately from the processed assessment.
- Presents the same assessment through the CLI and Streamlit dashboard.
- Creates reproducible PDF reports from live or saved raw input.
- Keeps tests deterministic, offline, and suitable for continuous integration.

## How to read the results

- **Official flight category:** The VFR, MVFR, IFR, or LIFR classification derived from reported ceiling and visibility. It is a weather category, not a flight approval or aircraft limit.
- **Hazard:** The condition being screened, such as wind, freezing precipitation, or observation freshness.
- **Concern level:** The project result: `not_triggered`, `attention`, `high_attention`, or `unavailable`.
- **Trigger:** The exact project condition applied to the observation.
- **Operational judgment:** A short explanation of what deserves review without making a go/no-go decision.

Overall concern is the highest active known project concern. Unavailable data does not hide a known concern, and the official flight category does not automatically change the project concern level.

**No listed hazard trigger does not mean the flight is safe or approved.** See the [processed-data dictionary](https://github.com/watts26/aviation-weather-support/blob/main/docs/data-dictionary.md) for the complete schema, allowable values, thresholds, and missing-data behavior.

## Report workflow

Create a report from the latest live observation:

```console
uv run aviation-weather-support report KATL
```

The command saves the raw API response with its UTC retrieval and evaluation times, creates the processed assessment, renders the PDF, and prints each output path.

Replay a saved raw input without calling the API:

```console
uv run aviation-weather-support report --input data/reports/raw/KATL_20260805T194132891000Z_metar_raw.json
```

Live and replay reports use the saved evaluation time so observation freshness remains reproducible. Replaying the same station and observation replaces the same PDF rather than creating a numbered duplicate. If validation fails after retrieval, the saved raw input remains available. If rendering fails, the saved raw input and processed assessment remain, but no partial PDF is reported as complete.

Render the packaged offline KATL fixture without calling the API:

```console
aviation-weather-support report --fixture KATL
```

The repository copy remains available for direct Quarto development:

```console
uv run quarto render reports/practicum-6.qmd --to pdf --output-dir ../output/pdf
```

Fixture rendering stays offline and stops when the installed package does not contain the requested station fixture.

## File locations

- `reports/`: Quarto source, including `reports/practicum-6.qmd`.
- `output/pdf/`: generated PDF reports.
- `data/reports/raw/`: saved raw inputs for live reports and replay.
- `data/reports/processed/`: saved processed assessments used to render reports.
- `tests/fixtures/`: committed offline API examples used by tests and direct Quarto rendering.
- `data/raw/`: raw JSON saved by the normal CLI.
- `data/processed/`: processed JSON saved by the normal CLI.

Report artifacts follow these patterns:

```text
data/reports/raw/<ICAO>_<retrieval-YYYYMMDDTHHMMSSffffffZ>_metar_raw.json
data/reports/processed/<ICAO>_<retrieval-YYYYMMDDTHHMMSSffffffZ>_metar_processed.json
output/pdf/<ICAO>_<observation-YYYYMMDDTHHMMSSZ>_metar_report.pdf
```

The processed assessment uses working-directory-relative source paths for generated files under the current output root. The dashboard keeps the raw and processed JSON available as separate downloads.

## Testing

Run the full offline test suite and validate the diff:

```console
uv run pytest
git diff --check
```

Tests use committed fixtures and mocks. A safeguard fails any unmocked live HTTP request, so the suite remains deterministic and offline. No GitHub Actions workflow is currently committed; the same command is suitable for GitHub Actions or another CI service.

## Limitations

- This tool is not a replacement for an official weather briefing.
- It does not make go/no-go decisions or issue flight approvals.
- Wind thresholds are project-defined screening levels, not aircraft operating limits.
- Results depend on the latest METAR available from the Aviation Weather Center.
- It does not calculate runway-relative crosswind components.
- Forecast comparisons and runway calculations are outside the current scope.

## License

This project is available under the [MIT License](https://github.com/watts26/aviation-weather-support/blob/main/LICENSE).
