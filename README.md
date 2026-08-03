# Aviation Weather Support

A Python aviation-weather application that retrieves the latest METAR for an airport, validates the Aviation Weather Center response, preserves the raw API data, creates a simplified processed record, and evaluates explicit current-condition operational flags. The same reusable workflow powers a command-line interface and an interactive Streamlit dashboard.

The current Practicum 6 scope covers informational visibility, ceiling, and wind flags for the latest observation. Forecast comparison, crosswind calculations, and runway-specific guidance are planned or out of scope; they are not part of the current assessment.

## Documentation

- [Repository setup and contribution guidance](AGENTS.md)
- [Processed-data dictionary](docs/data-dictionary.md)
- [MIT License](LICENSE)
- [Practicum 6 Quarto report](reports/practicum-6.qmd) — forthcoming; the report is intentionally not included yet

## Data source

Weather data comes from the [Aviation Weather Center Data API](https://aviationweather.gov/data/api/). No API key is required.

Example request for Atlanta Hartsfield-Jackson International Airport:

```text
https://aviationweather.gov/api/data/metar?ids=KATL&format=json
```

The application uses four-character ICAO identifiers such as `KATL`, not three-letter IATA codes such as `ATL`.

## Requirements and installation

Requirements:

- Python 3.10 or newer
- [`uv`](https://docs.astral.sh/uv/)
- Internet access when retrieving live METAR data

Clone the repository and install the locked runtime and development dependencies:

```console
git clone https://github.com/watts26/aviation-weather-support.git
cd aviation-weather-support
uv sync
```

## Configuration

No environment variables, credentials, or API keys are currently required. `.env.example` is retained for future configuration and explicitly records that the current application has no required variables.

Optional logging is configured through CLI arguments:

- `--verbose` writes operational `INFO` messages to the console.
- `--log-file PATH` writes detailed `DEBUG` messages to the selected file.

Logs describe operations and file paths but do not include complete API payloads, request headers, or secrets.

## Command-line usage

Display the complete command help:

```console
uv run aviation-weather-support --help
```

Retrieve, validate, assess, and save the latest observation for `KATL`:

```console
uv run aviation-weather-support KATL
```

Enable console logging:

```console
uv run aviation-weather-support KATL --verbose
```

Write a detailed log file:

```console
uv run aviation-weather-support KATL --log-file logs/aviation-weather-support.log
```

The logging options can be combined:

```console
uv run aviation-weather-support KATL --verbose --log-file logs/aviation-weather-support.log
```

A successful run prints the generated paths:

```text
Saved METAR data for KATL.
Raw file: data\raw\KATL_metar_raw.json
Processed file: data\processed\KATL_metar_processed.json
```

## Streamlit dashboard

Launch the dashboard from the repository root:

```console
uv run streamlit run src/aviation_weather_support/dashboard.py
```

In the dashboard:

1. Enter a four-character ICAO identifier such as `KATL`.
2. Select **Load weather**. No request is made until this button is selected.
3. Review the report time, AWC flight category, project-defined operational flags, and current conditions.
4. Expand the threshold explanation or JSON sections when needed.
5. Download the raw or processed JSON without writing dashboard files to disk.

The dashboard presents familiar-unit conversions for readability, while processed JSON retains the documented aviation/API units.

## Inputs and outputs

### Input

The CLI and dashboard accept one four-character ICAO station identifier containing only letters `A–Z` and digits `0–9`. Lowercase input is normalized to uppercase.

Examples:

| Input | Result |
| --- | --- |
| `KATL` | Accepted as Atlanta's ICAO identifier. |
| `katl` | Normalized to `KATL`. |
| `K1A2` | Accepted because alphanumeric ICAO-style identifiers are supported. |
| `ATL` | Rejected because it is a three-character IATA code. |

### Raw JSON

The CLI writes the complete API response to:

```text
data/raw/<ICAO>_metar_raw.json
```

This list preserves fields returned by the Aviation Weather Center, including fields the project does not currently use.

### Processed JSON

The CLI writes the validated, simplified observation and operational assessment to:

```text
data/processed/<ICAO>_metar_processed.json
```

Representative abbreviated output:

```json
{
  "icao_id": "KATL",
  "report_time": "2026-07-29T20:00:00.000Z",
  "wind_speed_kt": 9,
  "wind_gust_kt": null,
  "visibility_miles": 9,
  "clouds": [
    {"cover": "BKN", "base": 20000}
  ],
  "operational_assessment": {
    "overall_status": "normal",
    "data_complete": true,
    "flags": [
      {
        "id": "visibility",
        "label": "Visibility",
        "status": "normal",
        "observed": {"visibility_sm": 9.0},
        "message": "Visibility is at least 5 statute miles."
      }
    ],
    "disclaimer": "Informational screening only. These project-defined thresholds are not official flight guidance and do not replace official weather products, aircraft or operator limitations, or pilot and dispatcher judgment."
  }
}
```

The example omits other observation fields and two flag records for brevity. See the [complete processed-data dictionary](docs/data-dictionary.md) for every field, unit, allowable value, provenance, transformation, and missing-value rule.

## Current-condition operational flags

The processed JSON and dashboard contain visibility, ceiling, and combined wind flags. Each flag is `normal`, `caution`, `severe`, or `unavailable`. The overall status is the most severe known flag; it is unavailable only when every flag is unavailable.

These transparent, project-defined thresholds are used:

| Flag | Normal | Caution | Severe |
| --- | --- | --- | --- |
| Visibility | 5 SM or more | 3 to less than 5 SM | Less than 3 SM |
| Ceiling | 3,000 ft AGL or more, or no ceiling reported | 1,000–2,999 ft AGL | Less than 1,000 ft AGL |
| Sustained wind | Less than 15 kt | 15–24 kt | 25 kt or more |
| Wind gust | Less than 20 kt | 20–29 kt | 30 kt or more |

Ceiling is the lowest reported `BKN`, `OVC`, or vertical-visibility (`VV`) layer. `FEW` and `SCT` layers are not ceilings. The combined wind flag uses whichever of the sustained-wind or gust results is more severe.

Missing values do not silently become normal. Missing or unusable visibility produces an unavailable visibility flag. An absent cloud-layer field, or a ceiling-forming layer without a usable base, produces an unavailable ceiling flag. Wind is unavailable only when both sustained wind and gust data are absent. Partial missing data produces `data_complete: false` while the overall status continues to reflect the most severe known condition.

> **Informational use only:** These project-defined thresholds are not official flight guidance and do not replace official weather products, aircraft or operator limitations, or pilot and dispatcher judgment.

## Common failures

| Message or symptom | Likely cause | Resolution |
| --- | --- | --- |
| `airport must be a four-character ICAO identifier...` | The identifier is the wrong length or contains unsupported characters. | Use an ICAO identifier such as `KATL`, not `ATL`. |
| `unable to retrieve METAR...` | Network, timeout, HTTP, or Aviation Weather Center service failure. | Confirm internet access and retry later; use `--verbose` or `--log-file` for operational details. |
| `no METAR observation found...` | AWC returned no usable observation for that identifier. | Verify the station identifier and try again later. |
| `the METAR API returned invalid JSON` | The remote response was malformed. | Retry later; the application does not save an invalid response as processed data. |
| `METAR data could not be used at <field>...` | A required or typed API field failed validation. | Review the named field in the error; retry after AWC publishes another observation. |
| `Could not write log file...` | The selected log path is not writable. | Choose a writable path such as `logs/aviation-weather-support.log`. |
| `unable to save METAR files...` | The CLI cannot create or write `data/raw` or `data/processed`. | Run from a writable directory and check file permissions. |

## Testing

Run the complete fixture-backed test suite:

```console
uv run pytest
```

Validate changed-file whitespace before submission:

```console
git diff --check
```

Tests use committed JSON fixtures and mocks. An automatic safeguard fails any test that attempts an unmocked live HTTP request, so the suite remains deterministic and fully offline.

## License

This project is available under the [MIT License](LICENSE).
