import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import type { MeasurementsResponse } from "./api/client";
import { App } from "./App";
import { jsonResponse, stubFetch } from "./test/fetch";
import {
  dailyMeasurements,
  dailyWindMeasurements,
  demoMeta,
  demoStations,
  emptyMeasurements,
} from "./test/fixtures";
import { renderWithQueryClient } from "./test/render";

const MEASUREMENTS = "/api/v1/stations/juan-carlos-i/measurements";

/** Serves the demo API; the measurements path answers with `measurements`. */
function serveDemo(
  measurements: () => Response | Promise<Response> = () => jsonResponse(dailyMeasurements),
) {
  return stubFetch({
    "/api/v1/meta": () => jsonResponse(demoMeta),
    "/api/v1/stations": () => jsonResponse(demoStations),
    [MEASUREMENTS]: measurements,
  });
}

function measurementRequests(fake: ReturnType<typeof stubFetch>): string[] {
  return fake.mock.calls.map(([url]) => url).filter((url) => url.startsWith(MEASUREMENTS));
}

async function renderApp() {
  const user = userEvent.setup();
  renderWithQueryClient(<App />);
  const form = await screen.findByRole("form", { name: "Query" });
  return { user, form };
}

function submit(user: ReturnType<typeof userEvent.setup>) {
  return user.click(screen.getByRole("button", { name: "Show data" }));
}

describe("App", () => {
  it("renders the title, the demo banner and the attribution footer", async () => {
    serveDemo();

    await renderApp();

    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("AEMET Antarctica Weather");
    expect(screen.getByRole("complementary", { name: "Demo mode" })).toBeInTheDocument();
    expect(screen.getByRole("contentinfo")).toBeInTheDocument();
  });

  it("starts the form on the last two recorded days, hourly, with every measurement", async () => {
    serveDemo();

    await renderApp();

    expect(screen.getByLabelText("Station")).toHaveValue("juan-carlos-i");
    expect(screen.getByLabelText("Start")).toHaveValue("2025-03-30T00:00");
    expect(screen.getByLabelText("End (included)")).toHaveValue("2025-04-01T00:00");
    expect(screen.getByLabelText("Aggregation")).toHaveValue("hourly");
    for (const label of ["Temperature (°C)", "Pressure (hPa)", "Speed (m/s)"]) {
      expect(screen.getByRole("checkbox", { name: label })).toBeChecked();
    }
  });

  it("tells the maximum range of the chosen aggregation, from the API's options", async () => {
    serveDemo();
    const { user } = await renderApp();
    const aggregation = screen.getByLabelText("Aggregation");

    expect(aggregation).toHaveAccessibleDescription("Ranges up to 366 days.");
    await user.selectOptions(aggregation, "none");
    expect(aggregation).toHaveAccessibleDescription("Ranges up to 31 days.");
    await user.selectOptions(aggregation, "monthly");
    expect(aggregation).toHaveAccessibleDescription("Any range length.");
  });

  it("requests nothing until the form is submitted, then shows a summary", async () => {
    const fake = serveDemo();
    const { user } = await renderApp();
    expect(measurementRequests(fake)).toEqual([]);

    await user.selectOptions(screen.getByLabelText("Aggregation"), "daily");
    await submit(user);

    const summary = await screen.findByRole("region", { name: "Result" });
    expect(measurementRequests(fake)).toEqual([
      `${MEASUREMENTS}?start=2025-03-30T00%3A00%3A00&end=2025-04-01T00%3A00%3A00` +
        "&aggregation=daily&types=temperature&types=pressure&types=speed",
    ]);
    expect(summary).toHaveTextContent("3 rows · Juan Carlos I · Daily means");
    expect(summary).toHaveTextContent(
      "2025-03-30 00:00 to 2025-04-01 00:00 (Europe/Madrid (default)) · Fetched from the recorded data",
    );
  });

  it("shows the rows in a table, with a link to the same query as CSV", async () => {
    serveDemo();
    const { user } = await renderApp();

    await user.selectOptions(screen.getByLabelText("Aggregation"), "daily");
    await submit(user);

    const table = await screen.findByRole("table", { name: "Daily means, Juan Carlos I" });
    expect(within(table).getAllByRole("row")).toHaveLength(1 + dailyMeasurements.data.length);
    const link = screen.getByRole("link", { name: "Download CSV" });
    expect(link).toHaveAttribute(
      "href",
      `${MEASUREMENTS}?start=2025-03-30T00%3A00%3A00&end=2025-04-01T00%3A00%3A00` +
        "&aggregation=daily&types=temperature&types=pressure&types=speed&format=csv",
    );
  });

  it("draws one chart per measurement, between the summary and the table", async () => {
    serveDemo();
    const { user } = await renderApp();

    await submit(user);

    const charts = await screen.findByRole("region", { name: "Charts" });
    expect(within(charts).getAllByRole("figure")).toHaveLength(3);
    const summary = screen.getByRole("region", { name: "Result" });
    const table = screen.getByRole("table");
    expect(summary.compareDocumentPosition(charts)).toBe(Node.DOCUMENT_POSITION_FOLLOWING);
    expect(charts.compareDocumentPosition(table)).toBe(Node.DOCUMENT_POSITION_FOLLOWING);
  });

  it("keeps the rows but hides the CSV link while the next query loads", async () => {
    let requests = 0;
    serveDemo(() => {
      requests += 1;
      return requests === 1
        ? jsonResponse(dailyMeasurements)
        : new Promise<Response>(() => {
            // The second request never answers.
          });
    });
    const { user } = await renderApp();
    await submit(user);
    await screen.findByRole("link", { name: "Download CSV" });

    await user.selectOptions(screen.getByLabelText("Aggregation"), "monthly");
    await submit(user);

    await waitFor(() => {
      expect(screen.queryByRole("link", { name: "Download CSV" })).not.toBeInTheDocument();
    });
    expect(screen.getByRole("table").closest("[aria-busy]")).toHaveAttribute("aria-busy", "true");
  });

  it("starts each new result in the API's order", async () => {
    serveDemo();
    const { user } = await renderApp();
    await submit(user);
    const temperature = await screen.findByRole("columnheader", { name: "Temperature (°C)" });
    await user.click(within(temperature).getByRole("button"));
    expect(temperature).toHaveAttribute("aria-sort", "ascending");

    await user.selectOptions(screen.getByLabelText("Aggregation"), "daily");
    await submit(user);

    await waitFor(() => {
      expect(screen.getByRole("columnheader", { name: "Datetime" })).toHaveAttribute(
        "aria-sort",
        "ascending",
      );
    });
    expect(screen.getByRole("columnheader", { name: "Temperature (°C)" })).not.toHaveAttribute(
      "aria-sort",
    );
  });

  it("asks for the wind-energy metrics, which need an aggregation level", async () => {
    const fake = serveDemo(() => jsonResponse(dailyWindMeasurements));
    const { user } = await renderApp();
    const option = screen.getByRole("checkbox", { name: "Wind-energy metrics" });

    await user.selectOptions(screen.getByLabelText("Aggregation"), "none");
    expect(option).toBeDisabled();
    expect(option).toHaveAccessibleDescription("Need hourly, daily or monthly means.");

    await user.selectOptions(screen.getByLabelText("Aggregation"), "daily");
    await user.click(option);
    await submit(user);

    await screen.findByRole("table");
    expect(measurementRequests(fake).at(-1)).toMatch(/&aggregation=daily&.*&metrics=extended$/);
    expect(screen.getByRole("columnheader", { name: "Wind power density (W/m²)" })).toBeVisible();
  });

  it("shows only the notice for a range without data, with the empty rows one click away", async () => {
    serveDemo(() => jsonResponse(emptyMeasurements));
    const { user } = await renderApp();

    await submit(user);

    expect(await screen.findByText(/^Demo mode: there is no recorded data/)).toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Charts" })).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Show the 2 empty days" }));

    expect(within(screen.getByRole("table")).getAllByRole("row")).toHaveLength(3);
  });

  it("warns when part of the data is a stale copy", async () => {
    const stale: MeasurementsResponse = {
      ...dailyMeasurements,
      metadata: {
        ...dailyMeasurements.metadata,
        source: "aemet",
        cache: { status: "hit", last_updated: "2026-11-15T13:00:00+01:00", stale: true },
      },
    };
    serveDemo(() => jsonResponse(stale));
    const { user } = await renderApp();

    await submit(user);

    expect(await screen.findByRole("status")).toHaveTextContent(
      "AEMET is not answering, so part of this data comes from an older copy, last updated 2026-11-15 13:00.",
    );
  });

  describe("validation before sending", () => {
    it("needs at least one measurement", async () => {
      const fake = serveDemo();
      const { user } = await renderApp();

      for (const label of ["Temperature (°C)", "Pressure (hPa)", "Speed (m/s)"]) {
        await user.click(screen.getByRole("checkbox", { name: label }));
      }
      await submit(user);

      expect(screen.getByText("Select at least one measurement.")).toBeInTheDocument();
      expect(measurementRequests(fake)).toEqual([]);
    });

    it("marks the end when it is not later than the start", async () => {
      const fake = serveDemo();
      const { user } = await renderApp();

      fireEvent.change(screen.getByLabelText("End (included)"), {
        target: { value: "2025-03-29T00:00" },
      });
      await submit(user);

      const end = screen.getByLabelText("End (included)");
      expect(end).toHaveAttribute("aria-invalid", "true");
      expect(end).toHaveAccessibleDescription("The end must be later than the start.");
      expect(measurementRequests(fake)).toEqual([]);
    });

    it("applies the maximum range of the chosen aggregation", async () => {
      const fake = serveDemo();
      const { user } = await renderApp();

      fireEvent.change(screen.getByLabelText("Start"), { target: { value: "2025-01-01T00:00" } });
      fireEvent.change(screen.getByLabelText("End (included)"), {
        target: { value: "2025-03-01T00:00" },
      });
      await user.selectOptions(screen.getByLabelText("Aggregation"), "none");
      await submit(user);

      expect(screen.getByLabelText("End (included)")).toHaveAccessibleDescription(
        /^The range is longer than 31 days/,
      );
      expect(measurementRequests(fake)).toEqual([]);
    });
  });

  describe("errors from the API", () => {
    it("shows a parameter error next to its field, with the request ID", async () => {
      serveDemo(() =>
        jsonResponse(
          {
            error: {
              code: "invalid_parameter",
              message: "'2025-03-30T02:30:00' does not exist in Europe/Madrid.",
              parameter: "start",
            },
          },
          { status: 422, headers: { "X-Request-ID": "a867d84a9a504f289d7cce6fbe8599ea" } },
        ),
      );
      const { user } = await renderApp();

      fireEvent.change(screen.getByLabelText("Start"), { target: { value: "2025-03-30T02:30" } });
      await submit(user);

      const start = screen.getByLabelText("Start");
      await waitFor(() => {
        expect(start).toHaveAttribute("aria-invalid", "true");
      });
      expect(start).toHaveAccessibleDescription(
        "'2025-03-30T02:30:00' does not exist in Europe/Madrid. Request ID: a867d84a9a504f289d7cce6fbe8599ea",
      );
      expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    });

    it("shows any other error in an alert, with the request ID", async () => {
      serveDemo(() =>
        jsonResponse(
          {
            error: {
              code: "upstream_unavailable",
              message: "AEMET failed recently and is not being called for a while.",
              parameter: null,
            },
          },
          { status: 503, headers: { "X-Request-ID": "r-503", "Retry-After": "42" } },
        ),
      );
      const { user } = await renderApp();

      await submit(user);

      const alert = await screen.findByRole("alert");
      expect(alert).toHaveTextContent("AEMET failed recently and is not being called for a while.");
      expect(within(alert).getByText("r-503")).toBeInTheDocument();
    });

    it("sends the same query again when it is submitted again", async () => {
      const fake = serveDemo();
      const { user } = await renderApp();

      await submit(user);
      await screen.findByRole("region", { name: "Result" });
      await submit(user);

      await waitFor(() => {
        expect(measurementRequests(fake)).toHaveLength(2);
      });
    });
  });
});
