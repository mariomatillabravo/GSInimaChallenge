# ADR-0015: Charts of measurements over time

- **Status**: Accepted
- **Date**: 2026-11-16

## Context

The front-end shows each result as charts above the table. The data has properties that a default chart gets wrong:

- **Time is not row order.** On the day summer time starts, Madrid's clocks jump from 02:00 to 03:00, so two
  consecutive hourly rows labelled 01:00 and 03:00 are one hour apart; on the night it ends, two rows are labelled
  02:00. Every datetime from the API carries its UTC offset, so its instant is known exactly.
- **Gaps must stay visible.** Aggregated results include their empty buckets, with null values. Ten-minute records
  are returned as stored: a missing record is simply absent.
- **Density varies widely.** The maximum ranges allow up to 4,465 ten-minute records or 8,785 hourly means in one
  response, far more points than a chart is wide in pixels.
- **The measurements have different units and scales** (°C, hPa, m/s), and any subset of them can be requested.

## Options considered

**Library**

1. **Recharts**: declarative React components drawing SVG, which tests can inspect; synchronized cursors between
   charts (`syncId`). Adds about 107 kB gzipped to the bundle with its dependencies (Redux Toolkit, immer, d3 through
   victory-vendor).
2. **uPlot**: very small and fast with many points, but not a React library, so it needs a hand-written wrapper.
3. **Chart.js**: draws on a canvas, which tests cannot inspect.
4. **Hand-written SVG**: no dependency, but scales, axes and tooltips would all be written by hand.

**Layout**: one chart per measurement on a shared time axis (small multiples), or all measurements in one chart.
One chart would need a second Y axis or a common index, and a second axis invents correlations through the arbitrary
alignment of its scale.

**Time axis**: by instant, with ticks computed on Madrid's calendar; by instant with the library's numeric ticks
(which fall on odd times such as 03:20); or by category, one slot per row (which hides the length of gaps and the
hour lost or repeated when the clocks change).

**Gaps in ten-minute records**: insert a break where records are missing, or let the line bridge the gap (a
six-hour outage would look like a straight line).

**Too many points**: suggest a coarser aggregation, offer a button that applies it, or thin the points in the
browser (downsampling, which silently hides data).

## Decision

- **Recharts**, with animations off.
- **Small multiples**: one chart per measurement in the result, stacked above the table, each with its own Y axis.
  All charts share the same points and the same Y axis width, so their time axes line up, and their cursors and
  tooltips move together.
- **The X axis is the instant** of each row, parsed from the API's datetime with its offset, never from the
  browser's time zone. Ticks fall on round values of Madrid's calendar (whole hours, midnights, first days of months
  or years), at most eight, computed by pure functions in `src/lib/chart.ts`; labels are built from Madrid's
  wall-clock time.
- **Gaps**: `connectNulls` is off, so null buckets break the line. For ten-minute records, a break is inserted after
  any record followed by more than ten minutes without one. A value with no neighbour on either side is drawn as a
  dot, since a line needs two points.
- **Dense results**: above 1,000 points per chart, a notice suggests the finest coarser aggregation level that would
  stay under that number and accepts the range. It is text only; the chart still draws every point.
- **Tooltip**: the value with its unit first, then the row's datetime as the API wrote it (with its offset) and, for
  aggregated rows, samples and coverage.
- **Colours** come from CSS custom properties, one line colour validated for contrast and lightness against each
  theme's surface. CSS rules on Recharts' class names override the colours Recharts writes as SVG attributes.

## Consequences

- On the day summer time starts, the space between the 00:00 and 12:00 ticks is eleven hours, one less than between
  12:00 and the next midnight; on the night it ends, 02:00 appears twice. Both are the real elapsed time.
- An outage in ten-minute data shows as a break. A single surviving value between gaps shows as a dot.
- The bundle grows from about 84 kB to about 191 kB gzipped, and Vite warns about a chunk over 500 kB. Loading the
  charts on demand (a dynamic import) would keep the first load small.
- The colours depend on Recharts' class names (`recharts-line-curve`, `recharts-cartesian-axis-tick-value`...). A
  major Recharts upgrade must be checked visually.
- Recharts measures its container with `ResizeObserver`, which jsdom lacks; each chart sets an initial size, which is
  also what tests render with, so they can inspect the drawn lines, dots and tick labels.
- The table remains the accessible way to read every value; the charts are figures named by their measurement.
