import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";

import { App } from "./App";
import { jsonResponse, stubFetch } from "./test/fetch";
import { dailyMeasurements, demoMeta, demoStations } from "./test/fixtures";
import { renderWithQueryClient } from "./test/render";

// The charts' code fails to load, as after a deployment that replaced it while the page was open.
vi.mock("./components/MeasurementCharts", () => {
  throw new Error("Failed to fetch dynamically imported module");
});

it("keeps the summary and the table when the charts cannot be loaded", async () => {
  stubFetch({
    "/api/v1/meta": () => jsonResponse(demoMeta),
    "/api/v1/stations": () => jsonResponse(demoStations),
    "/api/v1/stations/juan-carlos-i/measurements": () => jsonResponse(dailyMeasurements),
  });
  const consoleError = vi.spyOn(console, "error").mockImplementation(() => undefined);
  const user = userEvent.setup();
  renderWithQueryClient(<App />);

  await user.click(await screen.findByRole("button", { name: "Show data" }));

  expect(await screen.findByRole("alert")).toHaveTextContent(
    "The charts could not be loaded. Reload the page to try again; the table below has every value.",
  );
  expect(screen.getByRole("region", { name: "Result" })).toBeInTheDocument();
  expect(screen.getByRole("table")).toBeInTheDocument();
  consoleError.mockRestore();
});
