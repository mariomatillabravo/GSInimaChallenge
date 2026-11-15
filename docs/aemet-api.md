# AEMET OpenData: Antarctica endpoint

What the service relies on, as verified against the real API on 2026-11-15 with
[`backend/scripts/explore_aemet.py`](../backend/scripts/explore_aemet.py) (33 requests in total). Items that could
not be verified are listed under [Still to verify](#still-to-verify).

## Request

```
GET https://opendata.aemet.es/opendata/api/antartida/datos/fechaini/{start}/fechafin/{end}/estacion/{station}
api_key: <AEMET API key>
```

| Aspect | Verified behaviour |
|---|---|
| Authentication | API key sent in the `api_key` request header |
| Date format in the URL | `YYYY-MM-DDTHH:MM:SSUTC`, e.g. `2026-01-15T00:00:00UTC` (UTC) |
| Maximum range | **One month** per request. Longer ranges are rejected (see `estado: 400` below) |
| End of range | **Inclusive**: one day returns 145 records (144 + 1), January 2026 returns 4,465 (31 × 144 + 1) |

## Two-step response

1. The endpoint returns an **envelope**, not the data:

   ```json
   {
     "descripcion" : "exito",
     "estado" : 200,
     "datos" : "https://opendata.aemet.es/opendata/sh/9905a00d_202611151227_json",
     "metadatos" : "https://opendata.aemet.es/opendata/sh/2cc612ba"
   }
   ```

2. A second request to the `datos` URL returns the measurements. The `datos` URL does not contain the API key.
   `metadatos` describes the fields.

### Errors are reported in the body, not in the HTTP status

Every envelope observed was served with **HTTP 200**, including errors. The outcome is in the `estado` field:

| `estado` | `descripcion` | Meaning for the service |
|---|---|---|
| 200 | `exito` | Fetch the `datos` URL |
| 404 | `No hay datos que satisfagan esos criterios` | Valid **empty** result, not an error |
| 400 | `El rango de fechas no puede ser superior a 1 mes` | Request too long: split into monthly chunks |

A client that only checks the HTTP status would treat the "no data" and "range too large" answers as successes.

## Data format

- Served as `text/plain;charset=ISO-8859-15` (also the envelopes, as `application/json;charset=ISO-8859-15`).
  The body must be decoded with the declared charset and then parsed as JSON.
- A JSON array with one object per **10-minute** observation.
- `fhora` is ISO-8601 in **UTC** with a `Z` suffix, e.g. `2026-01-15T00:10:00Z`.
- **Missing values are the string `"NaN"`**, not `null` (39 of 4,465 temperatures in January 2026 at 89064).
- **Records are not always sorted**: some older responses (2010, 2015, 2018, 2023) start with the last record.
- The set of fields varies between stations (89070 has no `altNieve`, `radKjM2`, `rec` or `tsb`), so absent keys
  must be tolerated.

### Fields used by the service

| AEMET field | Description (from the metadata) | Unit |
|---|---|---|
| `identificacion` | Station identifier | |
| `nombre` | Station name | |
| `fhora` | Date and time of the observation (UTC) | |
| `temp` | Temperature | °C |
| `pres` | Pressure | hPa |
| `vel` | Wind speed | m/s |
| `qdato` | Data quality flag: `1` bad, `0` good | |
| `velx` | Maximum wind speed within the 10 minutes | m/s |
| `tmn`, `tmx` | Minimum and maximum temperature within the 10 minutes | °C |

The metadata itself writes the units as `ºC` (ordinal indicator) and `hpa`; the correct symbols are `°C` and
`hPa`. It also still documents separate `fecha` and `hora` fields, while the data uses a single `fhora`, so the
real responses are treated as the source of truth.

## Stations

| Identifier | `nombre` returned | Latitude | Longitude | Altitude |
|---|---|---|---|---|
| `89064` | `JCI Estacion meteorologica` (Juan Carlos I) | -62.66325 | -60.38959 | 12 m |
| `89070` | `GdC Estacion meteorologica` (Gabriel de Castilla) | -62.97697 | -60.67528 | 12 m |

## Data availability

The Spanish Antarctic bases are seasonal (roughly November to March), and the data follows the campaigns:

- January and February 2026 are complete; in 2026 the data ends on **2026-03-13 19:50 UTC**.
- There is no data around the 2026 Madrid DST changes (28–30 March and 24–26 October 2026).
- The windows around the spring DST change of **2023, 2024 and 2025** are complete (289 records, nothing missing).
- History goes back at least to **2010**.
- The metadata states an annual publication periodicity (`"periodicidad": "anualmente"`).

## Rate limiting

No `429` responses were received over 33 requests sent with a 2-second pause between them. The actual limits are
not documented in the responses.

## Still to verify

- Shape of the responses for an invalid API key (`401`) and for rate limiting (`429`), and the actual limits.
- Whether the API key is also accepted as a query parameter, and whether the `datos` URL requires it.
- How long a `datos` URL remains valid.
- The local clock used at the bases (the service uses a fixed UTC−03:00 offset for station-local days).

## Attribution

© AEMET. Autorizado el uso de la información y su reproducción citando a AEMET como autora de la misma.
See AEMET's [legal notice](https://www.aemet.es/es/nota_legal).
