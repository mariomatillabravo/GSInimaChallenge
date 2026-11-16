import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import type { MeasurementsResponse } from "../api/client";
import { dailyMeasurements } from "../test/fixtures";
import { MeasurementsTable } from "./MeasurementsTable";

type Row = MeasurementsResponse["data"][number];

function hourlyRow(
  datetime: string,
  temperature: number | null,
  speed: number,
  samples: number,
): Row {
  return {
    station: "Juan Carlos I",
    datetime,
    temperature_c: temperature,
    speed_ms: speed,
    samples,
    expected_samples: 6,
    coverage: Math.round((samples / 6) * 1000) / 10,
  };
}

/**
 * Synthetic hourly means around the end of summer time (26 October 2025), with temperature and
 * speed only: Madrid lives 02:00 to 03:00 twice, first at +02:00, then at +01:00.
 */
const fallBackNight: MeasurementsResponse = {
  metadata: {
    ...dailyMeasurements.metadata,
    aggregation: "hourly",
    start: "2025-10-26T01:00:00+02:00",
    end: "2025-10-26T03:00:00+01:00",
    count: 4,
  },
  fields: {
    station: { label: "Station", unit: null },
    datetime: { label: "Datetime", unit: null },
    temperature_c: { label: "Temperature (°C)", unit: "°C" },
    speed_ms: { label: "Speed (m/s)", unit: "m/s" },
    samples: { label: "Samples", unit: null },
    expected_samples: { label: "Expected samples", unit: null },
    coverage: { label: "Coverage (%)", unit: "%" },
  },
  data: [
    hourlyRow("2025-10-26T01:00:00+02:00", -1.5, 4.2, 6),
    hourlyRow("2025-10-26T02:00:00+02:00", -1.75, 3.9, 6),
    hourlyRow("2025-10-26T02:00:00+01:00", null, 4.1, 3),
    hourlyRow("2025-10-26T03:00:00+01:00", -2.0, 5.0, 6),
  ],
};

function renderTable(result: MeasurementsResponse, csvUrl: string | null = "/data.csv") {
  const user = userEvent.setup();
  render(<MeasurementsTable result={result} csvUrl={csvUrl} />);
  return user;
}

function bodyRows(): HTMLElement[] {
  const [, ...rows] = within(screen.getByRole("table")).getAllByRole("row");
  return rows;
}

function bodyRow(index: number): HTMLElement {
  const row = bodyRows()[index];
  if (row === undefined) {
    throw new Error(`The table has no row ${String(index)}.`);
  }
  return row;
}

const cellTexts = (row: HTMLElement) =>
  within(row)
    .getAllByRole("cell")
    .map((cell) => cell.textContent);

describe("MeasurementsTable", () => {
  it("has one column per field of the response, with its official label, except the station", () => {
    renderTable(fallBackNight);

    expect(screen.getAllByRole("columnheader").map((header) => header.textContent)).toEqual([
      "Datetime▲",
      "Temperature (°C)",
      "Speed (m/s)",
      "Samples",
      "Expected samples",
      "Coverage (%)",
    ]);
    expect(screen.getByRole("table", { name: "Hourly means, Juan Carlos I" })).toBeInTheDocument();
  });

  it("shows each datetime with its offset and a dash where there is no data", () => {
    renderTable(fallBackNight);

    expect(cellTexts(bodyRow(1)).slice(0, 2)).toEqual(["2025-10-26 02:00 +02:00", "-1.75"]);
    expect(cellTexts(bodyRow(2)).slice(0, 2)).toEqual(["2025-10-26 02:00 +01:00", "—"]);
  });

  it("sorts the datetimes by instant on the night summer time ends", async () => {
    const user = renderTable(fallBackNight);

    await user.click(
      within(screen.getByRole("columnheader", { name: "Datetime" })).getByRole("button"),
    );

    expect(bodyRows().map((row) => cellTexts(row)[0])).toEqual([
      "2025-10-26 03:00 +01:00",
      "2025-10-26 02:00 +01:00",
      "2025-10-26 02:00 +02:00",
      "2025-10-26 01:00 +02:00",
    ]);
  });

  it("marks coverage below 90 % in words, not only in colour", () => {
    renderTable(dailyMeasurements);

    const coverage = bodyRows().map((row) => within(row).getAllByRole("cell").at(-1));
    expect(coverage[0]).toHaveTextContent("16.7 ⚠ (below 90 %)");
    expect(coverage[1]).toHaveTextContent(/^100$/);
    expect(coverage[2]).toHaveTextContent("79.9 ⚠ (below 90 %)");
    expect(screen.getByText(/^⚠ marks coverage below 90 %/)).toBeInTheDocument();
  });

  it("does not mark coverage of exactly 90 %", () => {
    renderTable({
      ...dailyMeasurements,
      data: dailyMeasurements.data.map((row) => ({ ...row, coverage: 90 })),
    });

    for (const row of bodyRows()) {
      expect(within(row).getAllByRole("cell").at(-1)).toHaveTextContent(/^90$/);
    }
  });

  it("explains the coverage mark only when the rows have coverage", () => {
    const fields = Object.fromEntries(
      Object.entries(fallBackNight.fields).filter(([key]) => key !== "coverage"),
    );
    renderTable({ ...fallBackNight, fields });

    expect(screen.queryByText(/marks coverage/)).not.toBeInTheDocument();
    expect(screen.getByText("— means no data.")).toBeInTheDocument();
  });

  it("links the CSV of the same query, as a download", () => {
    renderTable(fallBackNight, "/api/v1/stations/juan-carlos-i/measurements?format=csv");

    const link = screen.getByRole("link", { name: "Download CSV" });
    expect(link).toHaveAttribute("href", "/api/v1/stations/juan-carlos-i/measurements?format=csv");
    expect(link).toHaveAttribute("download");
  });

  it("hides the CSV link when there is no query for it", () => {
    renderTable(fallBackNight, null);

    expect(screen.queryByRole("link", { name: "Download CSV" })).not.toBeInTheDocument();
  });
});
