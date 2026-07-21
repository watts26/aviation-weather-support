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

The command validates and normalizes an ICAO identifier, retrieves its latest METAR, saves the full response, and creates a processed JSON record with commonly used fields. Enter a four-character ICAO identifier such as `KATL`, not a three-letter IATA code such as `ATL`.

Planned direction: expand this foundation into practical aviation-weather decision support.

## Installation

Install [uv](https://docs.astral.sh/uv/) if needed, clone or download this repository, and run the following command from the project directory:

```console
uv sync
```

## Run

```console
uv run aviation-weather-support KATL
```

## Output

The complete API response is written to `data/raw/KATL_metar_raw.json`. The selected and renamed fields from the first observation are written to `data/processed/KATL_metar_processed.json`. These directories are created automatically.
