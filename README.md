# Aviation Weather Support

A Python application that retrieves the latest airport METAR, validates the Aviation Weather Center response, preserves the raw response, creates a simplified processed record, assigns the official ceiling-and-visibility weather category, and evaluates project-defined current-condition hazard concerns. One shared workflow powers the CLI and Streamlit dashboard.

The current Practicum 6 scope covers ceiling and visibility category, thunderstorms and convective clouds, freezing precipitation, sustained winds and gusts, and observation freshness. Forecast comparisons, crosswind and runway calculations, and official flight recommendations are outside scope.

## Documentation

- [Repository guide](AGENTS.md)
- [Processed-data dictionary](docs/data-dictionary.md)
- [Practicum 6 Quarto source](reports/practicum-6.qmd)
- [Practicum 6 PDF](output/pdf/practicum-6.pdf)
- [MIT License](LICENSE)

## Data source

Weather data comes from the [Aviation Weather Center Data API](https://aviationweather.gov/data/api/). No API key is required.

```text
https://aviationweather.gov/api/data/metar?ids=KATL&format=json
```

The application accepts four-character ICAO identifiers such as `KATL`, not three-letter IATA codes such as `ATL`.

## Installation

Python 3.10 or newer, [`uv`](https://docs.astral.sh/uv/), and internet access for live retrieval are required.

```console
git clone https://github.com/watts26/aviation-weather-support.git
cd aviation-weather-support
uv sync
```

No environment variables, credentials, or API keys are currently required. `.env.example` records this explicitly.

## Command-line usage

```console
uv run aviation-weather-support --help
uv run aviation-weather-support KATL
uv run aviation-weather-support KATL --verbose
uv run aviation-weather-support KATL --log-file logs/aviation-weather-support.log
```

`--verbose` writes operational `INFO` messages to the console. `--log-file PATH` writes detailed `DEBUG` messages without including complete API payloads, request headers, or secrets.

A successful run saves:

```text
data/raw/<ICAO>_metar_raw.json
data/processed/<ICAO>_metar_processed.json
```

The raw file retains the complete AWC response. The processed file contains validated observation fields plus the centralized operational assessment.

### Reproducible PDF reports

Create a report from a current live observation:

```console
uv run aviation-weather-support report KATL
```

On success, report mode prints the paths to a raw evidence envelope, the
processed assessment used by the report, and the rendered PDF. The evidence
envelope preserves the complete AWC response array along with the UTC retrieval
and evaluation timestamps. It is written before model validation or operational
processing.

Replay any raw evidence file created by report mode without calling the API:

```console
uv run aviation-weather-support report --input data/reports/raw/KATL_20260805T194132891000Z_metar_raw.json
```

Report artifacts use these names:

```text
data/reports/raw/<ICAO>_<retrieval-YYYYMMDDTHHMMSSffffffZ>_metar_raw.json
data/reports/processed/<ICAO>_<retrieval-YYYYMMDDTHHMMSSffffffZ>_metar_processed.json
output/pdf/<ICAO>_<observation-YYYYMMDDTHHMMSSZ>_metar_report.pdf
```

The processed JSON stores repository-relative provenance paths for files inside
the project. Replaying the same station and observation intentionally replaces
the same PDF instead of creating a numbered duplicate.

Retrieval failures, HTTP 204 responses, empty responses, and malformed API JSON
produce no report artifacts. If a response is retrieved and preserved but later
fails validation or report usability checks, the CLI identifies the preserved
raw path and explicitly states that no processed result or PDF was generated.
If Quarto rendering fails, the raw and processed evidence remain available, but
no partial PDF is reported as complete.

## Streamlit dashboard

```console
uv run streamlit run src/aviation_weather_support/dashboard.py
```

Enter an ICAO identifier and select **Load weather**. The dashboard displays the official weather category separately from project-defined hazard concerns, current observations, source basis, confidence notes, and downloadable raw and processed JSON.

## Quarto report

Render the committed offline KATL fixture with its fixed evaluation timestamp:

```console
uv run quarto render reports/practicum-6.qmd --to pdf --output-dir ../output/pdf
```

To render another airport, first add a matching committed fixture named `tests/fixtures/metar-<lowercase-icao>-success.json`, then override the station and evaluation time. For example, this command requires `tests/fixtures/metar-kauo-success.json` to already exist:

```console
uv run quarto render reports/practicum-6.qmd -P station:KAUO -P evaluated_at:2026-07-29T20:00:00Z --to pdf --output-dir ../output/pdf
```

Report rendering never calls the live API and never falls back to KATL. A missing fixture, invalid parameter, or station mismatch stops the render with a clear error. The report consumes assessment results from `operational_rules.py`; it does not reproduce threshold or aggregation logic.

The `report` CLI passes absolute paths internally to Quarto, but the report and
saved processed JSON display repository-relative source references whenever the
files are inside this project. Live and replay reports use the saved UTC
evaluation timestamp, so observation freshness is assessed consistently.

## Official flight category

The official category is derived from structured AWC visibility and cloud fields. It is a weather classification, not an aircraft operating limit or flight approval.

| Official category | Ceiling | Visibility |
| --- | --- | --- |
| VFR | Greater than 3,000 ft AGL | Greater than 5 SM |
| MVFR | 1,000-3,000 ft AGL inclusive | 3-5 SM inclusive |
| IFR | 500 to less than 1,000 ft AGL | 1 to less than 3 SM |
| LIFR | Less than 500 ft AGL | Less than 1 SM |

The worse available ceiling or visibility dimension determines the category. `BKN`, `OVC`, and `VV` form ceilings. An empty cloud list, CLR/SKC, or only FEW/SCT layers is a valid no-ceiling observation. Missing cloud data or an unusable ceiling-layer base remains incomplete. A known LIFR dimension remains LIFR when the other dimension is unavailable, with `data_complete: false`.

## Project-defined hazard concerns

The project assesses thunderstorm, convective cloud, freezing precipitation, wind, and observation freshness hazards. Internal concern values are:

- `not_triggered`: no listed project trigger was found.
- `attention`: a project attention trigger was found.
- `high_attention`: a project elevated-attention trigger was found.
- `unavailable`: the relevant input was malformed, unusable, or genuinely unavailable.

Overall concern equals the highest active known project concern. Unavailable hazards do not conceal known concerns, and the official flight category does not automatically change project concern.

The 25 kt wind threshold, 30 kt sustained-wind threshold, and 50 kt gust threshold are project-defined screening anchors informed by official FAA weather-product criteria. They are not a complete FAA wind-hazard scale or universal aircraft operating limits. The 75-minute freshness threshold and five-minute future-time tolerance are also project-defined.

An absent or null decoded `wxString` validly means that no significant present-weather phenomenon was reported; it does not make thunderstorm or freezing-precipitation screening unavailable. Explicit TS, VCTS, FZRA, and FZDZ tokens are evaluated from the structured decoded field. Raw METAR text is preserved as evidence rather than reparsed when a structured field exists.

AO1 indicates limited confidence because the station lacks a precipitation discriminator. AO1 does not by itself make freezing-precipitation screening unavailable or incomplete, and explicit FZRA/FZDZ still triggers regardless of AO1/AO2.

> **Informational use only:** Official flight categories are weather classifications. Project-defined concern levels are not universal aircraft operating limits or official flight guidance.

## Representative processed structure

```json
{
  "icao_id": "KATL",
  "observation_time": 1785354720,
  "report_time": "2026-07-29T20:00:00.000Z",
  "weather_string": null,
  "operational_assessment": {
    "flight_category": {
      "category": "VFR",
      "rule_classification": "official",
      "data_complete": true
    },
    "overall_concern": "not_triggered",
    "overall_display_label": "No listed hazard trigger",
    "hazards": [
      {
        "id": "wind",
        "concern_level": "not_triggered",
        "display_label": "No listed hazard trigger",
        "rule_classification": "project_defined"
      }
    ]
  }
}
```

The example omits fields and metadata for brevity. See the [data dictionary](docs/data-dictionary.md) for the complete schema.

## Common failures

| Message or symptom | Likely cause | Resolution |
| --- | --- | --- |
| `airport must be a four-character ICAO identifier...` | Identifier is invalid | Use an ICAO identifier such as `KATL` |
| `unable to retrieve METAR...` | Network, timeout, HTTP, or AWC failure | Confirm internet access and retry |
| `no METAR observation found...` | AWC returned no usable observation | Verify the identifier and retry later |
| `the METAR API returned invalid JSON` | Remote response was malformed | Retry after AWC publishes another response |
| `METAR data could not be used at <field>...` | A typed field failed validation | Review the named field |
| `unable to save METAR files...` | Output directory is not writable | Run from a writable directory |

## Testing

```console
uv run pytest
git diff --check
```

Tests use committed fixtures and mocks. An automatic safeguard fails any unmocked live HTTP request, keeping the suite deterministic and offline.
