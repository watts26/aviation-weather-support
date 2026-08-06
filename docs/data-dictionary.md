# Processed METAR Data Dictionary

Processed JSON is a project-owned representation of one validated Aviation Weather Center METAR. Raw API JSON is preserved separately. The CLI saves processed data to `data/processed/<ICAO>_metar_processed.json`; the dashboard downloads the same structure.

Report mode stores a separate evidence envelope under `data/reports/raw/` and
the exact processed assessment consumed by Quarto under
`data/reports/processed/`. Replay reconstructs the assessment from the evidence
envelope using its saved `evaluated_at` timestamp and does not call the API.

## Report raw-evidence envelope

| Field | Type | Meaning |
| --- | --- | --- |
| `schema_version` | integer | Evidence schema version; currently `1` |
| `requested_station` | string | Normalized four-character ICAO identifier sent to AWC |
| `retrieved_at` | ISO 8601 UTC string | Time the API response was received by report mode |
| `evaluated_at` | ISO 8601 UTC string | Fixed timestamp used by the operational assessment; equal to `retrieved_at` for live reports |
| `api_response` | array | Complete, unmodified parsed JSON array returned by AWC |

The evidence filename is
`<ICAO>_<retrieval-YYYYMMDDTHHMMSSffffffZ>_metar_raw.json`.

## Report provenance metadata

Report-mode processed JSON contains the normal processed observation and
`operational_assessment`, plus a `report_metadata` object:

| Field | Type | Meaning |
| --- | --- | --- |
| `schema_version` | integer | Report provenance schema version; currently `1` |
| `station` | string | Validated station identifier |
| `observation_time` | ISO 8601 UTC string | Validated METAR observation time |
| `retrieved_at` | ISO 8601 UTC string | Original live retrieval time |
| `evaluated_at` | ISO 8601 UTC string | Fixed assessment timestamp reused during replay |
| `raw_source_path` | string | Raw evidence path; repository-relative when inside the project |
| `processed_source_path` | string | This processed file; repository-relative when inside the project |
| `pdf_path` | string | Observation-timestamp PDF path; repository-relative when inside the project |

The processed filename is
`<ICAO>_<retrieval-YYYYMMDDTHHMMSSffffffZ>_metar_processed.json`. The PDF is
named `<ICAO>_<observation-YYYYMMDDTHHMMSSZ>_metar_report.pdf`; generating the
same station and observation again intentionally replaces that PDF.

## Observation fields

| Field | Type | Units or values | Source | Missing-value behavior | Meaning |
| --- | --- | --- | --- | --- | --- |
| `icao_id` | string | Four uppercase letters or digits | AWC `icaoId` | Required | ICAO station identifier |
| `airport_name` | string or null | Text | AWC `name` | `null` when absent | Station name |
| `observation_time` | integer, number, string, or null | Epoch seconds or ISO 8601 | AWC `obsTime` | `null`/unparseable makes freshness unavailable | Actual observation time used for freshness |
| `receipt_time` | string or null | AWC timestamp | AWC `receiptTime` | `null` when absent | Time AWC received the report |
| `report_time` | string | ISO 8601 | AWC `reportTime` | Required and validated | AWC report time; not used for freshness |
| `raw_metar` | string | METAR text | AWC `rawOb` | Required | Preserved report evidence |
| `temperature_c` | number or null | Degrees Celsius | AWC `temp` | `null` when absent | Air temperature |
| `dewpoint_c` | number or null | Degrees Celsius | AWC `dewp` | `null` when absent | Dew point |
| `wind_direction_deg` | integer, `"VRB"`, or null | 0-360 degrees true, variable, or unavailable | AWC `wdir` | `"VRB"` when variable; `null` when absent | Decoded wind direction |
| `wind_speed_kt` | number or null | Knots, nonnegative | AWC `wspd` | `null` makes wind concern unavailable | Sustained wind speed |
| `wind_gust_kt` | number or null | Knots, nonnegative | AWC `wgst` | `null` validly means no gust value reported | Gust speed |
| `visibility_miles` | number, string, or null | Statute miles | AWC `visib` | Missing/unusable makes visibility dimension unavailable | Decoded prevailing visibility |
| `weather_string` | string or null | METAR weather tokens | AWC `wxString` | Null/absent/empty validly means no significant phenomenon reported | Structured present weather used for TS/VCTS/FZRA/FZDZ |
| `altimeter_hpa` | number or null | Hectopascals | AWC `altim` | `null` when absent | Altimeter setting |
| `flight_category` | string or null | Commonly VFR/MVFR/IFR/LIFR | AWC `fltCat` | `null` when absent | AWC category retained for comparison; project classification is separate |
| `clouds` | array or null | Cloud-layer objects | AWC `clouds` | See below | Structured cloud layers |
| `operational_assessment` | object | See below | `operational_rules.py` | Added by workflow | Official category plus project hazard concerns |

## Cloud-layer fields and missing-data rules

| Field | Type | Values or units | Source | Meaning |
| --- | --- | --- | --- | --- |
| `clouds[].cover` | string | CLR, SKC, NSC, NCD, FEW, SCT, BKN, OVC, VV | AWC `cover` | Coverage; BKN, OVC, and VV form a ceiling |
| `clouds[].base` | integer or null | Feet AGL, nonnegative | AWC `base` | Layer base |
| `clouds[].cloud_type` | string or null | CB or TCU when reported | AWC `type` | Convective cloud type |

- `clouds: null` means structured cloud data is unavailable.
- `clouds: []` is a valid observation with no reported layers and no ceiling.
- CLR/SKC and lists containing only FEW/SCT are valid no-ceiling observations.
- A BKN/OVC/VV layer without a usable base makes the ceiling dimension unavailable.
- Malformed cover or cloud-type data is not treated as clear sky or no convection.

## Operational assessment

| Field | Type | Values | Meaning |
| --- | --- | --- | --- |
| `operational_assessment.flight_category` | object | `FlightCategoryAssessment` | Official ceiling-and-visibility weather classification |
| `operational_assessment.hazards` | array | Five hazard objects | Project thunderstorm, convective-cloud, freezing-precipitation, wind, and freshness results |
| `operational_assessment.overall_concern` | string | `not_triggered`, `attention`, `high_attention`, `unavailable` | Highest active known project concern |
| `operational_assessment.overall_display_label` | string | User-facing label | Presentation label generated centrally |
| `operational_assessment.data_complete` | boolean | true/false | True only when the official category and every hazard have usable data |
| `operational_assessment.evaluated_at` | string | ISO 8601 UTC | Time at which freshness and assessment were evaluated |
| `operational_assessment.disclaimer` | string | Informational statement | Separates weather categories and project concerns from official guidance and universal limits |

Unavailable hazards do not override a known active concern. Overall concern is unavailable only when every project hazard is unavailable. Official VFR/MVFR/IFR/LIFR category does not directly change project overall concern.

## Official flight-category assessment

| Field | Type | Meaning |
| --- | --- | --- |
| `flight_category.category` | string | VFR, MVFR, IFR, LIFR, or unavailable |
| `flight_category.observed_value` | object | Derived `ceiling_ft_agl`, parsed `visibility_sm`, and retained `awc_reported_category` |
| `flight_category.trigger` | string | Exact official category condition applied |
| `flight_category.source_basis` | array | FAA source title, URL, and relevance |
| `flight_category.rule_classification` | string | Always `official` |
| `flight_category.operational_judgment` | string | Scope-limited interpretation without a flight-suitability judgment |
| `flight_category.data_complete` | boolean | Whether both ceiling and visibility dimensions were usable |

Official category boundaries:

- VFR: ceiling greater than 3,000 ft AGL and visibility greater than 5 SM.
- MVFR: ceiling 1,000-3,000 ft AGL inclusive and/or visibility 3-5 SM inclusive, unless a worse dimension applies.
- IFR: ceiling 500 to less than 1,000 ft AGL and/or visibility 1 to less than 3 SM, unless LIFR applies.
- LIFR: ceiling less than 500 ft AGL and/or visibility less than 1 SM.

The worse dimension wins. A known LIFR dimension remains LIFR when the other dimension is missing, while `data_complete` remains false. Otherwise a missing dimension makes the combined category unavailable.

## Hazard assessment fields

| Field | Type | Meaning |
| --- | --- | --- |
| `hazards[].id` | string | Stable hazard identifier |
| `hazards[].label` | string | Human-readable hazard name |
| `hazards[].concern_level` | string | Internal project concern value |
| `hazards[].display_label` | string | Clear user-facing result label |
| `hazards[].observed_value` | object | Structured values used by the classifier |
| `hazards[].trigger` | string | Exact trigger or non-trigger condition applied centrally |
| `hazards[].source_basis` | array | Official source title, URL, and relevance |
| `hazards[].rule_classification` | string | Always `project_defined` |
| `hazards[].operational_judgment` | string | Operational review supported by the observation without safe/unsafe language |
| `hazards[].data_complete` | boolean | Whether the hazard had usable classification data |
| `hazards[].data_confidence` | string | `standard`, `limited`, or `unavailable` |
| `hazards[].confidence_note` | string or null | Explanation of a limitation such as AO1 |

User-facing labels are `No listed hazard trigger`, `Operational attention`, `Elevated operational attention`, and `Assessment unavailable`.

## Project-defined hazard rules

- Thunderstorm: TS at the station produces high attention; VCTS produces attention. Null/absent decoded weather or valid weather without these tokens is not triggered.
- Convective cloud: structured CB or TCU produces attention. Missing or malformed cloud data is unavailable.
- Freezing precipitation: FZRA or FZDZ at any intensity produces high attention. AO1 does not change the concern or completeness; it records limited confidence because the station lacks a precipitation discriminator.
- Wind: sustained wind or gust at least 25 kt produces attention; sustained wind at least 30 kt or gust at least 50 kt produces high attention. Missing sustained wind makes wind unavailable; missing gust alone does not.
- Freshness: age greater than 75 minutes produces attention. A time more than five minutes in the future or missing/unusable `obsTime` is unavailable.

All concern mappings are project-defined. The wind values are contextual anchors from official FAA weather-product criteria, not a complete FAA hazard scale or universal aircraft limits. The 75-minute age and five-minute future tolerance are project-defined.

Raw METAR remains evidence. Numeric classification uses structured AWC fields; raw remarks are inspected only for the AO1/AO2 capability token because the current AWC response has no corresponding structured field.
