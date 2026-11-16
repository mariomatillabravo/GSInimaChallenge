import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { MeasurementsResponse } from "../api/client";
import { ChartTooltip } from "./ChartTooltip";

type Row = MeasurementsResponse["data"][number];

const hourly: Row = {
  station: "Juan Carlos I",
  datetime: "2025-10-26T02:00:00+01:00",
  temperature_c: -1.75,
  samples: 3,
  expected_samples: 6,
  coverage: 50,
};

describe("ChartTooltip", () => {
  it("shows the value with its unit, when it was measured and its coverage", () => {
    const { container } = render(
      <ChartTooltip point={{ x: 0, row: hourly }} measurementKey="temperature_c" unit="°C" />,
    );

    expect(container).toHaveTextContent(
      "-1.75 °C2025-10-26 02:00 +01:003/6 samples · 50 % coverage",
    );
  });

  it("says when the bucket has no value", () => {
    render(
      <ChartTooltip
        point={{ x: 0, row: { ...hourly, temperature_c: null } }}
        measurementKey="temperature_c"
        unit="°C"
      />,
    );

    expect(screen.getByText("No data")).toBeInTheDocument();
  });

  it("has no coverage line for ten-minute records", () => {
    const record: Row = { station: "Juan Carlos I", datetime: hourly.datetime, speed_ms: 4.1 };
    const { container } = render(
      <ChartTooltip point={{ x: 0, row: record }} measurementKey="speed_ms" unit="m/s" />,
    );

    expect(container).toHaveTextContent(/^4.1 m\/s2025-10-26 02:00 \+01:00$/);
  });

  it("shows nothing for a break in the line or without a point", () => {
    const { container } = render(
      <>
        <ChartTooltip point={{ x: 0, row: null }} measurementKey="temperature_c" unit="°C" />
        <ChartTooltip point={undefined} measurementKey="temperature_c" unit="°C" />
      </>,
    );

    expect(container).toBeEmptyDOMElement();
  });
});
