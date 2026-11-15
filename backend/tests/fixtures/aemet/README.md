# AEMET response fixtures

Real responses from the AEMET OpenData Antarctica endpoint
(`/api/antartida/datos/fechaini/{start}/fechafin/{end}/estacion/{station}`), recorded on 2026-11-15 with
[`scripts/explore_aemet.py`](../../../scripts/explore_aemet.py). They are used by contract tests to check that the
parser understands the real upstream format. Do not edit them: if AEMET changes its format, record new files instead.

## Envelopes (first step of the two-step response)

| File | Case covered |
|---|---|
| `envelope_success.json` | Success: `estado: 200` with the `datos` and `metadatos` URLs |
| `envelope_no_data.json` | No data for the range. Served with **HTTP 200** and `estado: 404` in the body |
| `envelope_range_too_large.json` | Range longer than one month. Served with **HTTP 200** and `estado: 400` in the body |

`envelope_success.json` keeps the recorded content; only its line endings were normalized to LF (the exploration
script stored envelopes as text on Windows). The two error envelopes were transcribed verbatim from the responses
printed by the script, which does not save envelopes without a `datos` URL.

## Data (second step)

Byte-exact copies of the bodies served by AEMET (`text/plain;charset=ISO-8859-15`, ASCII-only content).

| File | Station | Range (UTC, inclusive) | Records | Case covered |
|---|---|---|---|---|
| `data_89064_2026-01-15_2026-01-16.json` | 89064 Juan Carlos I | 2026-01-15 00:00 → 2026-01-16 00:00 | 145 | Typical day; one record with `temp` and `pres` as the string `"NaN"` (2026-01-15T16:00:00Z) |
| `data_89070_2026-01-15_2026-01-16.json` | 89070 Gabriel de Castilla | 2026-01-15 00:00 → 2026-01-16 00:00 | 145 | Same day, different set of fields per record (no `altNieve`, `radKjM2`, `rec`, `tsb`) |
| `data_89064_2023-03-25_2023-03-27.json` | 89064 Juan Carlos I | 2023-03-25 00:00 → 2023-03-27 00:00 | 289 | Records **not sorted** by time (the last one comes first); includes the Madrid DST change of 2023-03-26 |

The record counts show that AEMET treats the end of the range as inclusive (one day = 144 + 1 records).

## Attribution

© AEMET. Autorizado el uso de la información y su reproducción citando a AEMET como autora de la misma.
See AEMET's [legal notice](https://www.aemet.es/es/nota_legal).
