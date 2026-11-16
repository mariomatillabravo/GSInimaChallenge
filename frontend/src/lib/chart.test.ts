import { describe, expect, it } from "vitest";

import type { MeasurementsResponse } from "../api/client";
import { demoMeta } from "../test/fixtures";
import {
  chartPoints,
  formatTick,
  isolatedIndexes,
  measurementValue,
  suggestAggregation,
  timeTicks,
  zonedInstant,
} from "./chart";

type Row = MeasurementsResponse["data"][number];

const MADRID = "Europe/Madrid";
const utc = (year: number, month: number, day: number, hour: number, minute = 0) =>
  Date.UTC(year, month - 1, day, hour, minute);

function row(datetime: string, temperature: number | null = 1): Row {
  return { station: "Juan Carlos I", datetime, temperature_c: temperature };
}

describe("chartPoints", () => {
  it("places each row at its instant", () => {
    const points = chartPoints(
      [row("2025-03-30T01:00:00+01:00"), row("2025-03-30T03:00:00+02:00")],
      "hourly",
    );

    // One hour apart in real time, although the clocks moved two.
    expect(points.map((point) => point.x)).toEqual([utc(2025, 3, 30, 0), utc(2025, 3, 30, 1)]);
  });

  it("breaks the line where ten-minute records are missing", () => {
    const points = chartPoints(
      [
        row("2025-03-01T00:00:00+01:00"),
        row("2025-03-01T00:10:00+01:00"),
        row("2025-03-01T00:40:00+01:00"),
      ],
      "none",
    );

    expect(points.map((point) => [point.x, point.row === null])).toEqual([
      [utc(2025, 2, 28, 23, 0), false],
      [utc(2025, 2, 28, 23, 10), false],
      [utc(2025, 2, 28, 23, 20), true],
      [utc(2025, 2, 28, 23, 40), false],
    ]);
  });

  it("adds no break between aggregated buckets, which arrive even when empty", () => {
    const points = chartPoints(
      [row("2025-03-01T00:00:00+01:00"), row("2025-03-01T01:00:00+01:00", null)],
      "hourly",
    );

    expect(points.every((point) => point.row !== null)).toBe(true);
  });
});

describe("measurementValue", () => {
  it("reads a measurement, and null for a missing value, a missing key or a break", () => {
    const [point] = chartPoints([row("2025-03-01T00:00:00+01:00", -1.5)], "hourly");
    const empty = chartPoints([row("2025-03-01T00:00:00+01:00", null)], "hourly")[0];

    expect(point && measurementValue(point, "temperature_c")).toBe(-1.5);
    expect(point && measurementValue(point, "speed_ms")).toBeNull();
    expect(empty && measurementValue(empty, "temperature_c")).toBeNull();
    expect(measurementValue({ x: 0, row: null }, "temperature_c")).toBeNull();
  });
});

describe("isolatedIndexes", () => {
  it("finds the values without a neighbour, which a line cannot draw", () => {
    expect(isolatedIndexes([null, 1, null, 2, 3, null, 4])).toEqual(new Set([1, 6]));
    expect(isolatedIndexes([5])).toEqual(new Set([0]));
    expect(isolatedIndexes([1, 2])).toEqual(new Set());
  });
});

describe("zonedInstant", () => {
  it("finds Madrid's midnight on both sides of each daylight saving time change", () => {
    expect(zonedInstant("2025-03-30T00:00", MADRID)).toBe(utc(2025, 3, 29, 23));
    expect(zonedInstant("2025-03-31T00:00", MADRID)).toBe(utc(2025, 3, 30, 22));
    expect(zonedInstant("2025-10-26T00:00", MADRID)).toBe(utc(2025, 10, 25, 22));
    expect(zonedInstant("2025-10-27T00:00", MADRID)).toBe(utc(2025, 10, 26, 23));
  });

  it("corrects a first guess that falls on the other side of a change", () => {
    // 01:30 read as UTC is 03:30 in Madrid (summer time); subtracting two hours lands at
    // 00:30 (winter time), so a second correction is needed to reach 01:30 +01:00.
    expect(zonedInstant("2025-03-30T01:30", MADRID)).toBe(utc(2025, 3, 30, 0, 30));
    expect(zonedInstant("2025-03-30T03:00", MADRID)).toBe(utc(2025, 3, 30, 1));
  });

  it("rejects a malformed value", () => {
    expect(() => zonedInstant("2025-03-30", MADRID)).toThrow("Not a local date and time");
  });
});

describe("timeTicks", () => {
  const labels = (start: number, end: number) => {
    const { ticks, unit } = timeTicks(start, end, MADRID);
    return ticks.map((tick) => formatTick(tick, unit, MADRID));
  };

  it("puts hour ticks on round Madrid hours on the day summer time starts", () => {
    const start = utc(2025, 3, 29, 23); // 30 March 00:00 +01:00
    const end = utc(2025, 3, 30, 22); // 31 March 00:00 +02:00

    expect(timeTicks(start, end, MADRID)).toEqual({
      unit: "hour",
      // Madrid 00:00, 06:00, 12:00, 18:00 and 00:00: the first gap lasts five real hours.
      ticks: [start, utc(2025, 3, 30, 4), utc(2025, 3, 30, 10), utc(2025, 3, 30, 16), end],
    });
    expect(labels(start, end)).toEqual([
      "30 Mar 00:00",
      "30 Mar 06:00",
      "30 Mar 12:00",
      "30 Mar 18:00",
      "31 Mar 00:00",
    ]);
  });

  it("shows 02:00 twice on the night summer time ends", () => {
    expect(labels(utc(2025, 10, 25, 23), utc(2025, 10, 26, 3))).toEqual([
      "26 Oct 01:00",
      "26 Oct 02:00",
      "26 Oct 02:00",
      "26 Oct 03:00",
      "26 Oct 04:00",
    ]);
  });

  it("puts day ticks on Madrid midnights, whatever the offset", () => {
    const { ticks, unit } = timeTicks(utc(2025, 3, 28, 23), utc(2025, 4, 1, 22), MADRID);

    expect(unit).toBe("day");
    expect(ticks).toEqual([
      utc(2025, 3, 28, 23),
      utc(2025, 3, 29, 23),
      utc(2025, 3, 30, 22),
      utc(2025, 3, 31, 22),
      utc(2025, 4, 1, 22),
    ]);
    expect(labels(utc(2025, 3, 28, 23), utc(2025, 4, 1, 22))).toEqual([
      "29 Mar",
      "30 Mar",
      "31 Mar",
      "1 Apr",
      "2 Apr",
    ]);
  });

  it("puts month ticks on the first day of each month, inside the range", () => {
    expect(labels(utc(2025, 1, 15, 0), utc(2025, 6, 15, 0))).toEqual([
      "Feb 2025",
      "Mar 2025",
      "Apr 2025",
      "May 2025",
      "Jun 2025",
    ]);
    expect(timeTicks(utc(2025, 1, 15, 0), utc(2025, 6, 15, 0), MADRID).ticks[2]).toBe(
      utc(2025, 3, 31, 22),
    );
  });

  it("uses round years for long ranges, with at most eight ticks", () => {
    expect(labels(utc(2009, 12, 31, 23), utc(2026, 11, 16, 0))).toEqual([
      "2010",
      "2015",
      "2020",
      "2025",
    ]);
  });

  it("gives a single instant one tick", () => {
    const instant = utc(2025, 3, 30, 10, 20);
    expect(timeTicks(instant, instant, MADRID).ticks).toEqual([instant]);
  });
});

describe("suggestAggregation", () => {
  const levels = demoMeta.aggregations;
  const january = [utc(2024, 12, 31, 23), utc(2025, 1, 31, 23)] as const; // 31 days

  it("suggests the finest coarser level that stays under the limit", () => {
    expect(suggestAggregation(levels, "none", ...january, 4465)).toEqual({
      aggregation: "hourly",
      points: 745,
    });
    expect(
      suggestAggregation(levels, "hourly", utc(2023, 12, 31, 23), utc(2024, 12, 31, 23), 8785),
    ).toEqual({ aggregation: "daily", points: 367 });
  });

  it("suggests nothing up to 1,000 points", () => {
    expect(suggestAggregation(levels, "none", ...january, 1000)).toBeNull();
    expect(suggestAggregation(levels, "none", ...january, 1001)).not.toBeNull();
  });

  it("skips a level whose maximum range is too short", () => {
    const shortHourly = levels.map((level) =>
      level.id === "hourly" ? { ...level, max_range_days: 10 } : level,
    );

    expect(suggestAggregation(shortHourly, "none", ...january, 4465)?.aggregation).toBe("daily");
  });

  it("suggests nothing when there is no coarser level", () => {
    expect(
      suggestAggregation(levels, "monthly", utc(1900, 1, 1, 0), utc(2025, 1, 1, 0), 1501),
    ).toBeNull();
  });
});
