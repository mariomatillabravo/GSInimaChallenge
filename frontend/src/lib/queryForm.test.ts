import { describe, expect, it } from "vitest";

import { demoMeta, demoStations, realMeta, realStations } from "../test/fixtures";
import {
  type FormValues,
  formFieldOf,
  initialValues,
  toQuery,
  validate,
  windMetricsAvailable,
} from "./queryForm";

const NOW = new Date("2026-11-16T10:20:00Z"); // 11:20 in Madrid

describe("initialValues", () => {
  it("starts on the last two recorded days in demo mode", () => {
    expect(initialValues(demoMeta, demoStations, NOW)).toEqual({
      stationId: "juan-carlos-i",
      start: "2025-03-30T00:00",
      end: "2025-04-01T00:00",
      aggregation: "hourly",
      types: ["temperature", "pressure", "speed"],
      windMetrics: false,
    });
  });

  it("starts on the last seven days with real data", () => {
    expect(initialValues(realMeta, realStations, NOW)).toMatchObject({
      start: "2026-11-09T00:00",
      end: "2026-11-16T11:00",
    });
  });
});

describe("validate", () => {
  const valid: FormValues = initialValues(demoMeta, demoStations, NOW);

  it("accepts the initial values", () => {
    expect(validate(valid, demoMeta)).toEqual({});
  });

  it("needs at least one measurement", () => {
    expect(validate({ ...valid, types: [] }, demoMeta)).toEqual({
      types: "Select at least one measurement.",
    });
  });

  it("applies the maximum range of the chosen aggregation", () => {
    const twoMonths = { ...valid, start: "2025-01-01T00:00", end: "2025-03-01T00:00" };

    expect(validate({ ...twoMonths, aggregation: "none" }, demoMeta).end).toMatch(
      /^The range is longer than 31 days/,
    );
    expect(validate({ ...twoMonths, aggregation: "hourly" }, demoMeta)).toEqual({});
  });
});

describe("toQuery", () => {
  it("adds the seconds and keeps the types in the API's order", () => {
    expect(toQuery({ ...initialValues(demoMeta, demoStations, NOW), types: ["speed"] })).toEqual({
      stationId: "juan-carlos-i",
      params: {
        start: "2025-03-30T00:00:00",
        end: "2025-04-01T00:00:00",
        aggregation: "hourly",
        types: ["speed"],
      },
    });
  });

  it("asks for the wind-energy metrics only on aggregated levels", () => {
    const values = { ...initialValues(demoMeta, demoStations, NOW), windMetrics: true };

    expect(toQuery(values).params.metrics).toBe("extended");
    expect(toQuery({ ...values, aggregation: "daily" }).params.metrics).toBe("extended");
    expect(toQuery({ ...values, aggregation: "none" }).params.metrics).toBeUndefined();
    expect(toQuery({ ...values, windMetrics: false }).params.metrics).toBeUndefined();
  });
});

describe("windMetricsAvailable", () => {
  it("is false only for raw ten-minute records", () => {
    expect(windMetricsAvailable("none")).toBe(false);
    expect(windMetricsAvailable("hourly")).toBe(true);
    expect(windMetricsAvailable("monthly")).toBe(true);
  });
});

describe("formFieldOf", () => {
  it("maps the API's parameter names to form fields", () => {
    expect(formFieldOf("start")).toBe("start");
    expect(formFieldOf("types")).toBe("types");
    expect(formFieldOf("tz")).toBeNull();
    expect(formFieldOf(null)).toBeNull();
  });
});
