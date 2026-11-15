# ADR-0003: Non-existent and ambiguous local times are rejected

- **Status**: Accepted
- **Date**: 2026-11-15

## Context

Input datetimes without an offset are interpreted in Europe/Madrid (or in the zone given by `tz`). Twice a year,
some local times do not map to exactly one instant:

- **Spring forward** (last Sunday of March): at 02:00 the clocks jump to 03:00. `2026-03-29T02:30:00` **does not
  exist**.
- **Fall back** (last Sunday of October): at 03:00 the clocks go back to 02:00. `2026-10-25T02:30:00` is
  **ambiguous**: it is both `00:30Z` (summer time, `+02:00`) and `01:30Z` (winter time, `+01:00`).

Python does not raise for these values: it silently picks one interpretation through the `fold` attribute, so a
request for "02:00 to 03:00" on the fall-back day could return one hour of data or two without anyone noticing.

## Options considered

1. **Reject both cases** with HTTP 422 and a message explaining how to fix the request.
2. **Resolve automatically**: move non-existent times forward (02:30 becomes 03:30) and take the first occurrence
   of ambiguous times, reporting it in the response.
3. **Mixed**: reject non-existent times (clearly a client mistake) but resolve ambiguous ones.

## Decision

**Option 1: reject both.** The API never guesses. The error names the parameter, explains the cause and, for
ambiguous times, lists the two offsets that select each occurrence:

> `'2026-10-25T02:30:00' is ambiguous in Europe/Madrid: it occurs twice when daylight saving time ends. Use the
> offset +02:00 for the first occurrence or +01:00 for the second (in a URL, write '+' as %2B).`

There is always a way to express any instant: an explicit offset maps every local time to exactly one instant.

Detection compares the two interpretations of the local time (`fold=0` and `fold=1`). If their offsets differ,
the time is non-existent when converting the first interpretation to UTC and back changes the wall-clock time,
and ambiguous otherwise. The rule applies to any IANA zone given in `tz`; fixed offsets never have gaps or
overlaps.

## Consequences

- Results are always unambiguous, which matters for traders comparing intraday data.
- A client must repeat a request that hits one of these times. This affects at most two hours per year.
- The behaviour is covered by the DST test suite (`tests/unit/test_dst_input.py`) and by property-based tests
  that check that every other local time converts to UTC and back unchanged.
