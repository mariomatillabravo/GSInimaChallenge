/** Charts of measurements over time (pure functions). */
import type { AggregationId, MeasurementsResponse, MetaResponse } from "../api/client";
import { apiInstant } from "./datetime";
import { type LocalDateTime, shiftDate, wallClockAt, wallClockMinutes } from "./range";

type Row = MeasurementsResponse["data"][number];

const MINUTE = 60_000;
const HOUR = 60 * MINUTE;
const DAY = 24 * HOUR;
const TEN_MINUTES = 10 * MINUTE;

/** One position on the time axis: a row of the result, or a break in the line. */
export interface ChartPoint {
  /** The instant, in milliseconds since 1970 (UTC): the axis is real time, not row order. */
  x: number;
  /** null marks a break: the line stops there. */
  row: Row | null;
}

/**
 * The points shared by every chart (sharing them lets the charts synchronize their cursors by
 * index). Aggregated results include their empty buckets with null values, so their lines break
 * by themselves. Missing ten-minute records are simply absent, so a break is added after any
 * record followed by a longer silence: otherwise the line would bridge an outage.
 */
export function chartPoints(rows: readonly Row[], aggregation: AggregationId): ChartPoint[] {
  const points: ChartPoint[] = [];
  let previous: number | null = null;
  for (const row of rows) {
    const x = apiInstant(row.datetime);
    if (aggregation === "none" && previous !== null && x - previous > TEN_MINUTES) {
      points.push({ x: previous + TEN_MINUTES, row: null });
    }
    points.push({ x, row });
    previous = x;
  }
  return points;
}

/** The value of a measurement at a point; null for a break or a missing value. */
export function measurementValue(point: ChartPoint, key: string): number | null {
  if (point.row === null) {
    return null;
  }
  const record: Readonly<Record<string, unknown>> = point.row;
  const value = record[key];
  return typeof value === "number" ? value : null;
}

/**
 * Positions of values with no value on either side. A line needs two points, so these would
 * not be drawn at all; the chart shows them as dots.
 */
export function isolatedIndexes(values: readonly (number | null)[]): Set<number> {
  const isolated = new Set<number>();
  values.forEach((value, index) => {
    const before = values[index - 1] ?? null;
    const after = values[index + 1] ?? null;
    if (value !== null && before === null && after === null) {
      isolated.add(index);
    }
  });
  return isolated;
}

/**
 * The instant at which the clocks of a time zone show a wall-clock time, which must exist and
 * be unique there (midnight always is in Madrid: the clocks change at 02:00 and 03:00). The first
 * guess reads the time as UTC; each correction subtracts the offset the zone shows at the guess,
 * and the second one settles the case where the guess fell on the other side of a change.
 */
export function zonedInstant(local: LocalDateTime, timeZone: string): number {
  const target = wallClockMinutes(local);
  if (target === null) {
    throw new Error(`Not a local date and time: ${local}`);
  }
  let guess = target * MINUTE;
  for (let attempt = 0; attempt < 2; attempt++) {
    const shown = wallClockMinutes(wallClockAt(new Date(guess), timeZone)) ?? target;
    guess += (target - shown) * MINUTE;
  }
  return guess;
}

export type TickUnit = "hour" | "day" | "month" | "year";

interface Granularity {
  unit: TickUnit;
  step: number;
  /** Approximate length of one step, to choose the granularity. */
  length: number;
}

const COARSEST: Granularity = { unit: "year", step: 10, length: 10 * 365.25 * DAY };

/** From finest to coarsest. */
const GRANULARITIES: readonly Granularity[] = [
  ...[1, 3, 6, 12].map((step) => ({ unit: "hour" as const, step, length: step * HOUR })),
  ...[1, 2, 7].map((step) => ({ unit: "day" as const, step, length: step * DAY })),
  ...[1, 3, 6].map((step) => ({ unit: "month" as const, step, length: step * 30.44 * DAY })),
  ...[1, 2, 5].map((step) => ({ unit: "year" as const, step, length: step * 365.25 * DAY })),
  COARSEST,
];

/** The most ticks an axis gets; the chart also hides labels that would overlap. */
export const MAX_TICKS = 8;

export interface TimeTicks {
  ticks: number[];
  unit: TickUnit;
}

/**
 * Ticks of a time axis on round values of the time zone's calendar (whole hours, midnights,
 * first days of months or years), with the finest granularity that gives at most MAX_TICKS.
 * They are computed in the time zone, not in the browser's: a tick at "00:00" is midnight in
 * Madrid wherever the page is opened.
 */
export function timeTicks(start: number, end: number, timeZone: string): TimeTicks {
  const span = end - start;
  const granularity =
    GRANULARITIES.find((candidate) => span / candidate.length <= MAX_TICKS - 1) ?? COARSEST;
  const inRange = (instant: number) => instant >= start && instant <= end;
  const candidates = tickCandidates(start, end, timeZone, granularity);
  const ticks = candidates.filter(inRange);
  return { ticks: ticks.length > 0 ? ticks : [start], unit: granularity.unit };
}

function tickCandidates(
  start: number,
  end: number,
  timeZone: string,
  { unit, step }: Granularity,
): number[] {
  const first = wallClockAt(new Date(start), timeZone);
  const last = wallClockAt(new Date(end), timeZone);
  const candidates: number[] = [];

  if (unit === "hour") {
    // Every whole UTC hour is a whole hour in Madrid; keep those whose local hour fits the step.
    // On the night summer time ends, 02:00 appears twice, as two ticks.
    for (let instant = Math.ceil(start / HOUR) * HOUR; instant <= end; instant += HOUR) {
      const local = wallClockAt(new Date(instant), timeZone);
      if (local.endsWith(":00") && Number(local.slice(11, 13)) % step === 0) {
        candidates.push(instant);
      }
    }
  } else if (unit === "day") {
    const lastDate = last.slice(0, 10);
    for (let date = first.slice(0, 10), index = 0; date <= lastDate; index++) {
      if (index % step === 0) {
        candidates.push(zonedInstant(`${date}T00:00`, timeZone));
      }
      date = shiftDate(date, 1);
    }
  } else if (unit === "month") {
    for (let year = Number(first.slice(0, 4)); year <= Number(last.slice(0, 4)); year++) {
      for (let month = 1; month <= 12; month += step) {
        const date = `${String(year)}-${String(month).padStart(2, "0")}-01`;
        candidates.push(zonedInstant(`${date}T00:00`, timeZone));
      }
    }
  } else {
    const firstYear = Math.ceil(Number(first.slice(0, 4)) / step) * step;
    for (let year = firstYear; year <= Number(last.slice(0, 4)); year += step) {
      candidates.push(zonedInstant(`${String(year)}-01-01T00:00`, timeZone));
    }
  }
  return candidates;
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/**
 * The label of a tick, in the time zone: "30 Mar 06:00", "30 Mar", "Mar 2025" or "2025". Built
 * from the wall-clock time instead of Intl's date formats, whose wording varies between browsers.
 */
export function formatTick(instant: number, unit: TickUnit, timeZone: string): string {
  const local = wallClockAt(new Date(instant), timeZone);
  const year = local.slice(0, 4);
  const month = MONTHS[Number(local.slice(5, 7)) - 1] ?? "";
  const day = String(Number(local.slice(8, 10)));
  switch (unit) {
    case "hour":
      return `${day} ${month} ${local.slice(11, 16)}`;
    case "day":
      return `${day} ${month}`;
    case "month":
      return `${month} ${year}`;
    case "year":
      return year;
  }
}

/** Above this many points per chart, the lines are denser than a chart is wide. */
export const DENSE_POINTS = 1000;

/** Length of the bucket of each aggregation level (a month on average). */
const BUCKET_LENGTH: Record<AggregationId, number> = {
  none: TEN_MINUTES,
  hourly: HOUR,
  daily: DAY,
  monthly: 30.44 * DAY,
};

export interface AggregationSuggestion {
  aggregation: AggregationId;
  /** Estimated number of points with that aggregation. */
  points: number;
}

/**
 * When a result has more than DENSE_POINTS points, the finest coarser aggregation level that
 * would stay under it and accepts the range; null when the result is not dense or none fits.
 *
 * @param levels The API's aggregation levels, from finest to coarsest, with their range limits.
 */
export function suggestAggregation(
  levels: MetaResponse["aggregations"],
  current: AggregationId,
  start: number,
  end: number,
  points: number,
): AggregationSuggestion | null {
  if (points <= DENSE_POINTS) {
    return null;
  }
  const span = end - start;
  const coarser = levels.slice(levels.findIndex((level) => level.id === current) + 1);
  for (const level of coarser) {
    const estimate = Math.floor(span / BUCKET_LENGTH[level.id]) + 1;
    // The API's own rule: real elapsed time, which is what span measures.
    const accepted = level.max_range_days === null || span <= level.max_range_days * DAY;
    if (estimate <= DENSE_POINTS && accepted) {
      return { aggregation: level.id, points: estimate };
    }
  }
  return null;
}
