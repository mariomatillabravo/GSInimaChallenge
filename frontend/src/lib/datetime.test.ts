import { describe, expect, it } from "vitest";

import { apiInstant, formatApiDateTime, formatApiDateTimeWithOffset } from "./datetime";

describe("formatApiDateTime", () => {
  it("keeps the Madrid wall-clock time on both sides of a daylight saving time change", () => {
    expect(formatApiDateTime("2025-03-01T01:00:00+01:00")).toBe("2025-03-01 01:00");
    expect(formatApiDateTime("2025-04-01T01:50:00+02:00")).toBe("2025-04-01 01:50");
  });
});

describe("formatApiDateTimeWithOffset", () => {
  it("tells apart the two 02:00 of the night summer time ends", () => {
    expect(formatApiDateTimeWithOffset("2025-10-26T02:00:00+02:00")).toBe(
      "2025-10-26 02:00 +02:00",
    );
    expect(formatApiDateTimeWithOffset("2025-10-26T02:00:00+01:00")).toBe(
      "2025-10-26 02:00 +01:00",
    );
  });
});

describe("apiInstant", () => {
  it("orders by real time where the text order is wrong", () => {
    const summer = "2025-10-26T02:50:00+02:00"; // 00:50 UTC
    const winter = "2025-10-26T02:00:00+01:00"; // 01:00 UTC, ten minutes later

    expect([summer, winter].sort()).toEqual([winter, summer]);
    expect(apiInstant(winter) - apiInstant(summer)).toBe(10 * 60_000);
  });

  it("reads the offset, not the browser's time zone", () => {
    expect(apiInstant("2025-03-30T03:00:00+02:00")).toBe(Date.UTC(2025, 2, 30, 1, 0));
  });
});
