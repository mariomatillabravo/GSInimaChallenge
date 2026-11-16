# ADR-0014: Query form defaults and range validation

- **Status**: Accepted
- **Date**: 2026-11-16

## Context

The query form uses the browser's `datetime-local` inputs. They hold a wall-clock date and time without a time
zone, such as `2025-03-30T00:00`, which the form sends as is and the API interprets in Europe/Madrid, its default
([ADR-0002](0002-time-zone-strategy.md)). Two facts make checking a range in the browser delicate:

- The API limits the range per aggregation level in **real elapsed time** between the two instants. Across a daylight
  saving time change, a range of N calendar days lasts N days plus or minus one hour, so the calendar difference the
  form sees and the duration the API measures can disagree by up to one hour.
- The browser's own time zone may not be Madrid. Turning an input value into a JavaScript `Date` interprets it in the
  browser's zone, so any calculation made that way is wrong for a user outside Spain.

The API already rejects non-existent and ambiguous local times ([ADR-0003](0003-dst-input-policy.md)) and ranges
that are too long, with a 422 that names the offending parameter.

## Options considered

**Range check in the form**

1. **Orientative check with one hour of margin**: compare calendar values only, and block a range only when it
   exceeds the maximum even with one hour of margin. The form never blocks a range the API would accept; the API
   decides the doubtful cases.
2. **Exact conversion to instants in the browser** (with `Intl` or a time zone library): matches the API exactly
   and could also detect non-existent and ambiguous times, but duplicates the most delicate rules of the project in
   a second language, where the two copies can drift apart.
3. **No check in the form**: simplest, but obvious mistakes (90 days of 10-minute records) cost a round trip.

**When to validate**: on submit, with each message next to its field, or live, disabling the button (users cannot
tell why they cannot submit).

**When to query**: when the form is submitted, or on every change after a short pause (more requests, some for
half-typed values).

## Decision

- **Orientative check with one hour of margin** (option 1), in pure functions in `src/lib/range.ts`. Calendar
  values are counted with `Date.UTC` used as a plain calendar, never through a `Date` in the browser's zone.
- **Validation on submit**, messages linked to their fields with `aria-describedby`. A 422 from the API that names a
  form field (`start`, `end`, `aggregation`, `types`) is shown next to that field, with its request ID; any other
  error is shown in an alert.
- **At least one measurement** must be selected; all of them are selected at the start.
- **The query runs on submit.** Submitting the same query again fetches it again (for example after a 503), and the
  previous result stays on screen while a new one loads.
- **Defaults**: hourly means of every measurement for the first station. In demo mode, the last two days of its
  recorded data, from midnight to midnight; with the current recording this covers the change to summer time on
  30 March 2025 (48 hourly rows for 47 hours, because the end is included). With real data, the last seven days, from
  midnight seven days ago to the current hour in Madrid.
- **No time zone selector**: the form works in Madrid time, the API's default, and says so. The API's `tz` parameter
  stays available to other clients.

## Consequences

- Within one hour of the limit, the form may let through a range the API then rejects with a 422; the message
  appears next to the end field.
- The form never blocks a valid query because of daylight saving time.
- Non-existent and ambiguous times (02:00 to 03:00 on the nights the clocks change) are explained by the API's own
  message. The real-data default range ends at the current hour, so on the night summer time ends, between 02:00 and
  03:00, its end is ambiguous and the API rejects it until the hour passes.
- Users in other time zones type Madrid times; a time zone selector would be a contained addition.
