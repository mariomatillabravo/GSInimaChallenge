# ADR-0006: Output field names

- **Status**: Accepted
- **Date**: 2026-11-15

## Context

The challenge statement names the fields of the output dataset `Station`, `Datetime`, `Temperature (ºC)`,
`Pressure (hpa)` and `Speed (m/s)`. As JSON keys these names are awkward: they contain spaces and parentheses, so
they cannot be used as attribute names in Python or with dot notation in TypeScript. The `º` they use is the
ordinal indicator (U+00BA), not the degree sign (U+00B0): the two look almost identical, so a client typing the
key would silently fail to find it. AEMET's own metadata uses the same spellings (`ºC`, `hpa`), which is where the
statement took them from.

AEMET's station names (`nombre`) are abbreviations: `JCI Estacion meteorologica`, `GdC Estacion meteorologica`.

## Options considered

1. **Use the statement's names as JSON keys**: literal compliance, at the cost of every consumer.
2. **Clean snake_case JSON keys plus the official labels where data is presented as a dataset**: CSV headers and
   user interface, with a `fields` block in every JSON response mapping each key to its label and unit.
3. **Let the client choose** with a parameter: two response shapes to test, document and type.

## Decision

**Option 2.**

- JSON rows use `station`, `datetime`, `period`, `temperature_c`, `pressure_hpa`, `speed_ms`, `samples`,
  `expected_samples` and `coverage`.
- Every response includes `fields`, e.g. `"temperature_c": {"label": "Temperature (°C)", "unit": "°C"}`, so any
  client can render the official labels without hard-coding them.
- The CSV export and the front-end table use the official labels.
- The labels use the **correct unit symbols**, `Temperature (°C)` and `Pressure (hPa)`, instead of the statement's
  `ºC` and `hpa`. They are defined once, in `app/domain/measurements.py`, and a test pins the degree sign.
- `station` holds a **readable name** from the station registry ("Juan Carlos I", "Gabriel de Castilla"); AEMET's
  identifier and raw name are kept in the response metadata for traceability.
- A requested measurement without data is an explicit `null`; a measurement that was not requested is absent.
- Values are rounded to two decimals (AEMET publishes one).

## Consequences

- The JSON contract is easy to consume from Python, TypeScript and spreadsheets alike.
- Someone looking only at the JSON keys does not see the literal statement names; this ADR, the `fields` block and
  the CSV export make the mapping explicit.
- Changing a label is a one-line change in a single place.
