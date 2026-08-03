# Processed METAR Data Dictionary

The processed JSON is a project-owned, simplified representation of one validated Aviation Weather Center METAR observation. The CLI saves it to `data/processed/<ICAO>_metar_processed.json`; the dashboard displays and downloads the same structure.

Raw API JSON is preserved separately without a project-defined schema. Consult the [Aviation Weather Center API documentation](https://aviationweather.gov/data/api/) for raw-response fields. This dictionary covers only the processed JSON produced by this repository.

## Observation fields

| Field | Type | Units or allowable values | Source or provenance | Missing-value rule | Meaning or transformation |
| --- | --- | --- | --- | --- | --- |
| `icao_id` | string | Four uppercase letters or digits | AWC `icaoId`, validated | Required | ICAO station identifier. |
| `airport_name` | string or null | Free text | AWC `name` | `null` when absent | Airport or reporting-station name. |
| `report_time` | string | ISO 8601 timestamp | AWC `reportTime`, validated | Required | Time assigned to the observation by AWC. |
| `raw_metar` | string | METAR text | AWC `rawOb`, validated | Required | Original textual METAR observation. |
| `temperature_c` | number or null | Degrees Celsius | AWC `temp` | `null` when absent | Reported air temperature; no conversion in processed JSON. |
| `dewpoint_c` | number or null | Degrees Celsius | AWC `dewp` | `null` when absent | Reported dew point; no conversion in processed JSON. |
| `wind_direction_deg` | integer or null | 0–360 degrees true | AWC `wdir`, range-validated | `null` when absent or variable direction is not supplied numerically | Reported wind direction. |
| `wind_speed_kt` | number or null | Knots, nonnegative | AWC `wspd`, validated | `null` when absent | Reported sustained wind speed. |
| `wind_gust_kt` | number or null | Knots, nonnegative | AWC `wgst`, validated | `null` when no gust value is supplied | Reported wind-gust speed. |
| `visibility_miles` | number, string, or null | Statute miles; strings may include `+` or a fraction | AWC `visib` | `null` when absent | Original API visibility representation. The assessment parses numeric values, `10+`, fractions, and mixed fractions. |
| `altimeter_hpa` | number or null | Hectopascals, positive | AWC `altim`, validated | `null` when absent | Reported altimeter setting; no conversion in processed JSON. |
| `flight_category` | string or null | Common AWC values include `VFR`, `MVFR`, `IFR`, and `LIFR` | AWC `fltCat` | `null` when absent | AWC-reported category; it is not calculated by this project. |
| `clouds` | array or null | Cloud-layer objects | AWC `clouds`, validated | See cloud rules below | Reported cloud layers retained in API order. |
| `operational_assessment` | object | Current-condition assessment | Derived by `assess_current_conditions()` | Always present after the shared workflow completes | Project-defined visibility, ceiling, and wind screening result. |

## Cloud-layer fields

| Field | Type | Units or allowable values | Source or provenance | Missing-value rule | Meaning or transformation |
| --- | --- | --- | --- | --- | --- |
| `clouds[].cover` | string | Common values: `CLR`, `SKC`, `FEW`, `SCT`, `BKN`, `OVC`, `VV` | AWC cloud-layer `cover` | Required for each retained layer | Cloud coverage code. Only `BKN`, `OVC`, and `VV` form a ceiling for this project. |
| `clouds[].base` | integer or null | Feet AGL, nonnegative | AWC cloud-layer `base`, validated | `null` when no usable base is supplied | Cloud-layer base. |

Cloud missing-value distinctions are intentional:

- `clouds: null` means the cloud-layer field was absent, so the ceiling flag is `unavailable`.
- `clouds: []` means no cloud layers were reported, so the ceiling flag is `normal` with no ceiling reported.
- A list containing only non-ceiling layers such as `FEW` or `SCT` also produces a normal no-ceiling result.
- Any `BKN`, `OVC`, or `VV` layer with `base: null` makes the ceiling flag unavailable because the lowest ceiling cannot be established safely.

## Operational assessment fields

| Field | Type | Units or allowable values | Source or provenance | Missing-value rule | Meaning or transformation |
| --- | --- | --- | --- | --- | --- |
| `operational_assessment.overall_status` | string | `normal`, `caution`, `severe`, `unavailable` | Derived | Never null | Most severe known flag. It is `unavailable` only when every flag is unavailable. |
| `operational_assessment.data_complete` | boolean | `true` or `false` | Derived | Never null | `true` only when visibility, ceiling, and wind are all assessable. |
| `operational_assessment.flags` | array | Three flag objects | Derived | Always contains visibility, ceiling, and wind | Individual operational flags in stable display order. |
| `operational_assessment.disclaimer` | string | Informational-use statement | Project constant | Never null | States that project thresholds are not official flight guidance. |

## Operational flag fields

| Field | Type | Units or allowable values | Source or provenance | Missing-value rule | Meaning or transformation |
| --- | --- | --- | --- | --- | --- |
| `flags[].id` | string | `visibility`, `ceiling`, `wind` | Project-defined | Never null | Stable machine-readable flag identifier. |
| `flags[].label` | string | `Visibility`, `Ceiling`, `Wind` | Project-defined | Never null | Human-readable display label. |
| `flags[].status` | string | `normal`, `caution`, `severe`, `unavailable` | Derived from centralized thresholds | Never null | Result for this condition. |
| `flags[].observed` | object | Metric-specific fields below | Validated METAR fields plus project transformations | May be empty for unavailable visibility or ceiling | Measurements used to determine the status. |
| `flags[].message` | string | Explanatory text | Project-defined | Never null | Concise reason for the status. |

## Observed metric fields

| Field | Type | Units or allowable values | Source or provenance | Missing-value rule | Meaning or transformation |
| --- | --- | --- | --- | --- | --- |
| `observed.visibility_sm` | number | Statute miles | Parsed from `visibility_miles` | Key omitted when visibility is unavailable | Numeric visibility used for threshold comparison. A trailing `+` is removed; fractions and mixed fractions are converted to decimal miles. |
| `observed.ceiling_ft_agl` | integer or null | Feet AGL | Minimum usable base among `BKN`, `OVC`, and `VV` layers | `null` means cloud data was available but no ceiling layer was reported; key omitted when ceiling is unavailable | Ceiling used for threshold comparison. |
| `observed.sustained_kt` | number or null | Knots | `wind_speed_kt` | `null` when absent | Sustained value used by the combined wind flag. |
| `observed.gust_kt` | number or null | Knots | `wind_gust_kt` | `null` when absent | Gust value used by the combined wind flag. Wind is unavailable only when both wind values are null. |

## Assessment transformations

- Visibility is severe below 3 SM, caution from 3 to less than 5 SM, and normal at 5 SM or more.
- Ceiling is severe below 1,000 ft AGL, caution from 1,000 through 2,999 ft AGL, and normal at 3,000 ft AGL or more or when no ceiling layer is reported.
- Sustained wind is severe at 25 kt or more and caution at 15–24 kt.
- Wind gust is severe at 30 kt or more and caution at 20–29 kt.
- The combined wind flag uses the more severe sustained-wind or gust result.
- Missing flags do not override known severity. `data_complete` preserves the fact that one or more conditions could not be assessed.

These transformations are project-defined informational screening rules. They are not official flight guidance.
