# ADR-0005: Aggregation in station local time with visible data quality

- **Status**: Accepted
- **Date**: 2026-11-15

## Context

AEMET publishes one observation every ten minutes. Clients ask for no aggregation or for hourly, daily or monthly
aggregation, and the challenge warns that daily and monthly aggregation must consider the time zone of the
stations, while output datetimes must be in Europe/Madrid. Real data has gaps (the stations are seasonal and
sensors fail), and a requested range rarely starts and ends exactly on bucket boundaries.

## Options considered

**Bucket boundaries**

1. **Station local time** (fixed UTC−03:00, see [ADR-0002](0002-time-zone-strategy.md)): a day follows the
   station's own daily cycle of sun and temperature.
2. **Europe/Madrid days**: tidy labels, but days of 23 or 25 hours at the DST changes and boundaries that ignore
   the station.
3. **UTC days**: neutral, but meaningful neither for the station nor for the users.

**Data quality information**

1. Only `samples`, the number of observations used.
2. `samples` plus `expected_samples` and `coverage`, so incomplete buckets are obvious.
3. A sample count per measurement type: the most precise, but a wider response; in the real data the three
   measurements are usually missing together.

**Empty buckets**: omit them, or return them with `samples = 0` and no values.

**Implementation**: pandas `resample`, or grouping by hand in pure Python.

## Decision

- Hourly, daily and monthly buckets are cut in the **station's local time**. Hourly buckets are identical in every
  zone involved because all offsets are whole hours.
- Each row is labelled with the **start of its bucket**, written in Europe/Madrid with its offset. Daily and
  monthly rows also carry a readable **`period`** (`"2026-03-29"`, `"2026-03"`) in station time, because a station
  day starts at 04:00 or 05:00 Madrid time, which surprises readers.
- Each value is the **mean** of the bucket's non-missing observations. A measurement missing in the whole bucket
  is `null`. Other statistics (maximum, cubic mean for wind energy) are left for an optional extension.
- Every aggregated row includes **`samples`** (observations with at least one requested value), **`expected_samples`**
  (ten-minute slots in the complete bucket, computed from its real length) and **`coverage`** (percentage, rounded to
  0.1). They are computed at query time and never stored.
- **Every bucket between start and end is returned**, including empty ones with `samples = 0`, so gaps are visible
  in tables and charts instead of silently disappearing.
- **pandas** does the grouping: it is the standard tool for time series and handles timezone-aware resampling.
  The logic is a pure function, tested without any I/O.

## Consequences

- Station days always have 144 slots, so Madrid's DST never makes a bucket look incomplete; it only changes how
  labels are written (`2026-03-28T04:00:00+01:00`, then `2026-03-29T05:00:00+02:00`).
- A bucket cut by the requested range reports its real, partial coverage. This is deliberate: its mean is not
  comparable to the mean of a complete bucket.
- One year of hourly data (52,704 observations into 8,784 rows) is aggregated in about 0.3 s.
- Adding statistics later means adding columns to the same resampling step.
