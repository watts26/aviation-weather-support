# Repository Guide

## Purpose and scope

This repository retrieves current METAR observations, validates the Aviation Weather Center response, produces a simplified processed record, evaluates project-defined current-condition operational flags, and presents the results through a CLI and Streamlit dashboard.

Keep work scoped to the requested practicum. Practicum 6 covers current-condition visibility, ceiling, and wind flags. Forecast comparisons, crosswind calculations, runway calculations, and official flight recommendations are outside this scope unless a later task explicitly adds them.

## Setup and configuration

- Python 3.10 or newer is required.
- Install the locked runtime and development dependencies with `uv sync`.
- No environment variables or API key are currently required. `.env.example` records this explicitly.
- Do not commit `.env`, generated `data/`, generated `logs/`, caches, or virtual environments.

## Commands

- CLI: `uv run aviation-weather-support KATL`
- CLI help: `uv run aviation-weather-support --help`
- Dashboard: `uv run streamlit run src/aviation_weather_support/dashboard.py`
- Full tests: `uv run pytest`
- Diff validation: `git diff --check`

## Repository navigation

- `src/aviation_weather_support/api.py`: Aviation Weather Center HTTP retrieval.
- `src/aviation_weather_support/models.py`: validation models and processed observation mapping.
- `src/aviation_weather_support/operational.py`: operational thresholds, flag models, and current-condition assessment logic.
- `src/aviation_weather_support/workflow.py`: shared normalize, retrieve, validate, assess, and process workflow.
- `src/aviation_weather_support/__init__.py`: CLI entry point and JSON file output.
- `src/aviation_weather_support/dashboard.py`: Streamlit presentation and display formatting.
- `src/aviation_weather_support/logging_config.py`: package logging setup.
- `tests/fixtures/`: committed offline API examples.
- `docs/data-dictionary.md`: processed-output schema and missing-value rules.

## Sources of truth

- `MetarObservation` in `models.py` is the source of truth for validated API fields used by the project.
- `to_processed_dict()` plus the workflow-added `operational_assessment` define the processed JSON structure.
- Operational thresholds and assessment semantics must remain centralized in `operational.py`. The dashboard, README, report, and tests may display or verify those thresholds but must not introduce independent threshold values or decision logic.
- `uv.lock` is the source of truth for resolved dependencies; update it through `uv` when dependencies change.
- The Aviation Weather Center API is the source of raw current-condition data. Preserve the raw response separately from project-derived fields.

## Code and documentation conventions

- Keep reusable weather and assessment logic independent of Streamlit.
- Keep public and private production modules, classes, methods, and functions concisely documented and type-hinted.
- Use clear domain-specific names and explicit units such as `_kt`, `_ft`, `_c`, and `_miles`.
- Preserve `None` and `unavailable` distinctions; never silently convert missing weather data to normal conditions.
- Label operational assessments as informational and project-defined, never as official flight guidance.
- Update the README and data dictionary whenever user-visible commands, processed fields, units, allowable values, or missing-value behavior changes.

## Testing expectations

- Tests must be deterministic and fully offline.
- Never call the live Aviation Weather Center API from tests. The automatic fixture in `tests/conftest.py` intentionally fails unmocked HTTP requests.
- Use committed fixtures or explicit mocks for API behavior.
- Cover normal, caution, severe, missing-data, and exact threshold-boundary cases when assessment logic changes.
- Run the full test suite after changes, not only the directly affected test module.
- Do not weaken tests or the live-request safeguard to make a change pass.
