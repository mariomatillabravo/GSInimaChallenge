import { describe, expect, it } from "vitest";

import {
  checkRange,
  demoDefaultRange,
  recentDefaultRange,
  shiftDate,
  toApiDateTime,
  wallClockAt,
  wallClockMinutes,
} from "./range";

describe("toApiDateTime", () => {
  it("adds the seconds the API expects", () => {
    expect(toApiDateTime("2025-03-30T00:00")).toBe("2025-03-30T00:00:00");
    expect(toApiDateTime("2025-03-30T00:00:15")).toBe("2025-03-30T00:00:15");
  });
});

describe("wallClockMinutes", () => {
  it("counts every calendar day as 24 hours", () => {
    const start = wallClockMinutes("2025-03-30T00:00");
    const end = wallClockMinutes("2025-03-31T00:00");

    expect(start).not.toBeNull();
    expect(end).not.toBeNull();
    expect((end ?? 0) - (start ?? 0)).toBe(24 * 60);
  });

  it("rejects malformed values", () => {
    expect(wallClockMinutes("")).toBeNull();
    expect(wallClockMinutes("2025-03-30")).toBeNull();
  });
});

describe("checkRange", () => {
  it("asks for both ends and for an end later than the start", () => {
    expect(checkRange("", "2025-03-31T00:00", 31)?.field).toBe("start");
    expect(checkRange("2025-03-30T00:00", "", 31)?.field).toBe("end");
    expect(checkRange("2025-03-30T00:00", "2025-03-30T00:00", 31)?.message).toBe(
      "The end must be later than the start.",
    );
  });

  // The two ranges of the README's "Maximum range" example, checked by the form with its hour of
  // margin.
  it("lets through a range the API accepts although its dates suggest it is too long", () => {
    // 31 days and 30 minutes by the calendar, 30 days 23 h 30 min in reality: the API accepts it.
    expect(checkRange("2025-03-01T00:00", "2025-04-01T00:30", 31)).toBeNull();
  });

  it("leaves the doubtful cases to the API", () => {
    // 31 days by the calendar, 31 days and 1 hour in reality: the API rejects it with 422, but the
    // form cannot tell without time zone rules, so it does not block it.
    expect(checkRange("2025-10-01T00:00", "2025-11-01T00:00", 31)).toBeNull();
  });

  it("rejects a range too long even with an hour of margin", () => {
    expect(checkRange("2025-10-01T00:00", "2025-11-01T01:01", 31)?.message).toMatch(
      /^The range is longer than 31 days/,
    );
    expect(checkRange("2025-10-01T00:00", "2025-11-01T01:00", 31)).toBeNull();
  });

  it("accepts any length without a maximum", () => {
    expect(checkRange("1990-01-01T00:00", "2025-01-01T00:00", null)).toBeNull();
  });
});

describe("default ranges", () => {
  it("shifts calendar dates across month and year boundaries", () => {
    expect(shiftDate("2025-03-01", -2)).toBe("2025-02-27");
    expect(shiftDate("2025-01-01", -7)).toBe("2024-12-25");
  });

  it("uses the last two recorded days in demo mode, across the March 2025 change", () => {
    expect(demoDefaultRange("2025-04-01T01:50:00+02:00")).toEqual({
      start: "2025-03-30T00:00",
      end: "2025-04-01T00:00",
    });
  });

  it("reads the wall-clock time in Madrid, in winter and in summer", () => {
    expect(wallClockAt(new Date("2026-01-15T10:30:00Z"), "Europe/Madrid")).toBe("2026-01-15T11:30");
    expect(wallClockAt(new Date("2026-07-15T10:30:00Z"), "Europe/Madrid")).toBe("2026-07-15T12:30");
  });

  it("uses the last seven days up to the current hour with real data", () => {
    // 23:45 UTC on 15 November is already 00:45 on 16 November in Madrid.
    expect(recentDefaultRange(new Date("2026-11-15T23:45:00Z"), "Europe/Madrid")).toEqual({
      start: "2026-11-09T00:00",
      end: "2026-11-16T00:00",
    });
  });
});
