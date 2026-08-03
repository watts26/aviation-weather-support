# Aviation Weather Support

A small Python command-line tool that retrieves the latest METAR observation for an airport and saves both the complete API response and a simplified record.

## API source

Weather data comes from the Aviation Weather Center's AviationWeather.gov Data API. See the [official API documentation](https://aviationweather.gov/data/api/).

Example request for Atlanta Hartsfield-Jackson International Airport (`KATL`):

```text
https://aviationweather.gov/api/data/metar?ids=KATL&format=json
```

A METAR response describes an airport's current observed weather, including the report time, raw METAR text, temperature, dew point, wind, visibility, altimeter setting, clouds, and flight category.

## Current functionality

The command validates and normalizes an ICAO identifier, retrieves its latest METAR, saves the full response, and creates a processed JSON record with commonly used fields and current-condition operational flags. The Streamlit dashboard uses the same retrieval, validation, assessment, and processing workflow and provides readable conditions, unit conversions, operational flags, JSON views, and downloads. Enter a four-character ICAO identifier such as `KATL`, not a three-letter IATA code such as `ATL`.

Planned direction: expand this foundation into practical aviation-weather decision support.

## Planned Final Product

The final version is planned as an interactive aviation-weather decision-support dashboard where users can enter an airport identifier, view current METAR and forecast information, and see clear flags for concerns such as low visibility, low ceilings, strong winds, and worsening weather.

The dashboard will preserve raw API responses, present processed data clearly, and compare current and forecast conditions.

## Installation

Install [uv](https://docs.astral.sh/uv/) if needed, then clone the repository and enter its directory:

```console
git clone https://github.com/watts26/aviation-weather-support.git
cd aviation-weather-support
```

Install the locked runtime and development dependencies:

```console
uv sync
```

## Run

```console
uv run aviation-weather-support KATL
```

Show operational INFO messages in the console with `--verbose`:

```console
uv run aviation-weather-support KATL --verbose
```

Write detailed DEBUG messages to a file with `--log-file PATH`:

```console
uv run aviation-weather-support KATL --log-file logs/aviation-weather-support.log
```

The options may be used together. Logs describe operational events and paths but do not include complete API payloads, request headers, or secrets.

## Test

Run the fixture-backed automated tests with:

```console
uv run pytest
```

The tests use committed JSON fixtures and mocks, and an automatic safeguard fails any test that attempts an unmocked live HTTP request.

## Dashboard

Launch the local METAR dashboard:

```console
uv run streamlit run src/aviation_weather_support/dashboard.py
```

Enter a four-character ICAO identifier and select **Load weather**. The dashboard does not retrieve weather until the button is selected. It displays the validated observation and provides raw and processed JSON downloads without writing API files to disk.

## Current-condition operational flags

The processed JSON and dashboard include reusable flags for visibility, ceiling, and wind. Each flag is `normal`, `caution`, `severe`, or `unavailable`. The overall status is the most severe known flag; if every flag is unavailable, the overall status is unavailable.

These transparent, project-defined thresholds are used:

| Flag | Normal | Caution | Severe |
| --- | --- | --- | --- |
| Visibility | 5 SM or more | 3 to less than 5 SM | Less than 3 SM |
| Ceiling | 3,000 ft AGL or more, or no ceiling reported | 1,000–2,999 ft AGL | Less than 1,000 ft AGL |
| Sustained wind | Less than 15 kt | 15–24 kt | 25 kt or more |
| Wind gust | Less than 20 kt | 20–29 kt | 30 kt or more |

Ceiling is the lowest reported `BKN`, `OVC`, or vertical-visibility (`VV`) layer. `FEW` and `SCT` layers are not treated as ceilings. The combined wind flag uses whichever of the sustained-wind or gust results is more severe.

Missing values do not silently become normal. Missing or unusable visibility produces an unavailable visibility flag. An absent cloud-layer field, or a ceiling-forming layer without a usable base, produces an unavailable ceiling flag. Wind is unavailable only when both sustained wind and gust data are absent. Partial missing data is recorded with `data_complete: false` while the overall status continues to reflect the most severe known condition.

> **Informational use only:** These project-defined thresholds are not official flight guidance and do not replace official weather products, aircraft or operator limitations, or pilot and dispatcher judgment.

## Output

The complete API response is written to `data/raw/KATL_metar_raw.json`. The selected and renamed fields from the first observation, including the operational assessment, are written to `data/processed/KATL_metar_processed.json`. These directories are created automatically.
