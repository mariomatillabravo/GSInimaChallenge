import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { MeasurementsResponse } from "../api/client";
import { dailyMeasurements, dailyWindMeasurements, demoMeta } from "../test/fixtures";
import { MeasurementCharts } from "./MeasurementCharts";

type Row = MeasurementsResponse["data"][number];

const TEN_MINUTES = 10 * 60_000;

/** A Madrid winter-time datetime (+01:00) as the API writes it, from an instant. */
function winterDatetime(instant: number): string {
  return `${new Date(instant + 3_600_000).toISOString().slice(0, 19)}+01:00`;
}

/** Synthetic ten-minute temperature records from 1 March 2025 00:00 (Madrid). */
function tenMinuteResult(values: readonly (number | null)[], skip: number[] = []) {
  const origin = Date.UTC(2025, 1, 28, 23);
  const data: Row[] = values
    .map((value, index) => ({ value, index }))
    .filter(({ index }) => !skip.includes(index))
    .map(({ value, index }) => ({
      station: "Juan Carlos I",
      datetime: winterDatetime(origin + index * TEN_MINUTES),
      temperature_c: value,
    }));
  const result: MeasurementsResponse = {
    metadata: {
      ...dailyMeasurements.metadata,
      aggregation: "none",
      start: winterDatetime(origin),
      end: winterDatetime(origin + (values.length - 1) * TEN_MINUTES),
      count: data.length,
    },
    fields: {
      station: { label: "Station", unit: null },
      datetime: { label: "Datetime", unit: null },
      temperature_c: { label: "Temperature (°C)", unit: "°C" },
    },
    data,
  };
  return result;
}

function renderCharts(result: MeasurementsResponse) {
  return render(<MeasurementCharts result={result} meta={demoMeta} />);
}

/** The subpaths of the line in the only chart: each "M" starts a new stretch of line. */
function lineStretches(container: HTMLElement): number {
  const path = container.querySelector("path.recharts-line-curve");
  return (path?.getAttribute("d") ?? "").split("M").length - 1;
}

describe("MeasurementCharts", () => {
  it("draws one chart per measurement of the result, named by its official label", () => {
    renderCharts(dailyMeasurements);

    const charts = within(screen.getByRole("region", { name: "Charts" })).getAllByRole("figure");
    expect(charts.map((chart) => chart.querySelector("figcaption")?.textContent)).toEqual([
      "Temperature (°C)",
      "Pressure (hPa)",
      "Speed (m/s)",
    ]);
    expect(charts.every((chart) => chart.querySelector("path.recharts-line-curve"))).toBe(true);
  });

  it("adds a chart of wind power density, and only that metric, when it was requested", () => {
    renderCharts(dailyWindMeasurements);

    const charts = within(screen.getByRole("region", { name: "Charts" })).getAllByRole("figure");
    expect(charts.map((chart) => chart.querySelector("figcaption")?.textContent)).toEqual([
      "Temperature (°C)",
      "Pressure (hPa)",
      "Speed (m/s)",
      "Wind power density (W/m²)",
    ]);
  });

  it("labels the time axis in Madrid time", () => {
    const { container } = renderCharts(dailyMeasurements);

    const labels = [
      ...container.querySelectorAll(
        ".recharts-xAxis-tick-labels .recharts-cartesian-axis-tick-value",
      ),
    ].map((tick) => tick.textContent);
    // The daily buckets start at 04:00 or 05:00 in Madrid; the ticks sit on round Madrid hours.
    expect(labels.slice(0, 4)).toEqual([
      "29 Mar 12:00",
      "30 Mar 00:00",
      "30 Mar 12:00",
      "31 Mar 00:00",
    ]);
  });

  it("breaks the line where ten-minute records are missing", () => {
    const values = [1, 2, 3, 4, 5, 6];

    expect(lineStretches(renderCharts(tenMinuteResult(values)).container)).toBe(1);
    expect(lineStretches(renderCharts(tenMinuteResult(values, [2, 3])).container)).toBe(2);
  });

  it("draws a value with no neighbours as a dot, so it does not vanish", () => {
    const { container } = renderCharts(tenMinuteResult([null, 1, null, 2, 3, null]));

    expect(container.querySelectorAll(".recharts-line-dots circle")).toHaveLength(1);
  });

  it("suggests a coarser aggregation when there are too many points", () => {
    renderCharts(tenMinuteResult(Array.from({ length: 1100 }, (_, index) => index % 7)));

    expect(
      screen.getByText(
        "1,100 points per chart, more than a chart can show clearly. Hourly means (about 184 points) would show the trend better.",
      ),
    ).toBeInTheDocument();
  });

  it("suggests nothing for a readable number of points", () => {
    renderCharts(dailyMeasurements);

    expect(screen.queryByText(/more than a chart can show/)).not.toBeInTheDocument();
  });

  it("draws nothing for a result without rows", () => {
    const { container } = renderCharts({ ...dailyMeasurements, data: [] });

    expect(container).toBeEmptyDOMElement();
  });
});
