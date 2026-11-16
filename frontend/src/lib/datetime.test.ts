import { describe, expect, it } from "vitest";

import { formatApiDateTime } from "./datetime";

describe("formatApiDateTime", () => {
  it("keeps the Madrid wall-clock time on both sides of a daylight saving time change", () => {
    expect(formatApiDateTime("2025-03-01T01:00:00+01:00")).toBe("2025-03-01 01:00");
    expect(formatApiDateTime("2025-04-01T01:50:00+02:00")).toBe("2025-04-01 01:50");
  });
});
