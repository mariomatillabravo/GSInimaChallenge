# ADR-0002: Time zone strategy

- **Status**: Accepted
- **Date**: 2026-11-15

## Context

Three time zones meet in this service:

- Clients send local datetimes (format `YYYY-MM-DDTHH:MM:SS`) and may say which zone they are in, either as a
  location (`Europe/Berlin`) or as an offset (`+02:00`).
- The challenge requires output datetimes in CET/CEST (Europe/Madrid) including the UTC offset.
- Daily and monthly aggregation must consider the time zone of the stations, in the South Shetland Islands.

AEMET returns observation times in UTC (`fhora`, e.g. `2026-01-15T00:10:00Z`). Europe/Madrid changes its offset
twice a year, so naive datetimes (without zone) would make some instants impossible to tell apart.

## Options considered

**Default zone for input datetimes without an offset:**

1. **Europe/Madrid**: the users are analysts and traders in Spain, and the output is already in Madrid time, so
   asking "from 00:00" returns data from 00:00.
2. **UTC**: neutral, but surprising: asking for 00:00 would return data starting at 01:00 or 02:00 Madrid time.
3. **Station time**: nobody in Madrid thinks in Antarctic time.

**Local time of the stations** (used to cut station days and months):

1. **Fixed UTC−03:00**: the current civil time of the whole region (Chilean Magallanes, Argentine Tierra del
   Fuego, the Palmer station).
2. **`America/Punta_Arenas`** (or the equivalent `Antarctica/Palmer`): Chilean civil time, which until 2016 used
   UTC−04:00 in winter and UTC−03:00 in summer.

## Decision

- **Inside the service, every datetime is timezone-aware and in UTC.** Local times only exist at the edges:
  parsing the request and writing the response. The linter (`ruff` rule set `DTZ`) rejects naive datetimes.
- **Input**: datetimes without an offset are interpreted in the zone given by `tz` or, when absent, in
  **Europe/Madrid**. `tz` accepts an IANA name or a `±HH:MM` offset. A datetime may also carry its own offset or
  `Z`; giving `tz` as well is rejected as a conflict. Every response states how the input was interpreted.
- **Both ends of the range are inclusive**, as in AEMET's own API (one day returns 144 + 1 records).
- In a query string, `+` is decoded as a space. An offset arriving as ` 02:00` can only mean `+02:00`, so it is
  accepted; documentation and examples use `%2B`.
- **Output**: Europe/Madrid, always with the offset, e.g. `2026-03-29T05:00:00+02:00`.
- **Station local time: fixed UTC−03:00**, exposed as `UTC-03:00`. Real data exists since at least 2010, so the
  pre-2016 Chilean rules could matter; however, the bases are seasonal (November to March), and in those months
  even historical Chilean time was UTC−03:00. The clock actually used at the bases could not be verified. A fixed
  offset keeps every station day exactly 24 hours long and avoids applying a daylight-saving history the bases may
  never have followed. It is a per-station value in the registry, so it can change without touching code.

## Consequences

- Conversions happen in exactly two places, which keeps the logic testable with pure functions.
- Clients in other countries can query in their own zone, and the metadata removes any doubt about the
  interpretation.
- The zone is written as `UTC-03:00` rather than as the IANA name `Etc/GMT+3`, whose sign is inverted by POSIX
  convention and would confuse readers.
- If a base is ever confirmed to use a different clock, only its registry entry changes.
