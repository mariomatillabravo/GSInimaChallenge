import { screen, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { MetaResponse, Station } from "../api/client";
import { jsonResponse, stubFetch } from "../test/fetch";
import { demoMeta, demoStations, realMeta, realStations } from "../test/fixtures";
import { renderWithQueryClient } from "../test/render";
import { DemoBanner } from "./DemoBanner";

function serve(meta: MetaResponse, stations: Station[]) {
  stubFetch({
    "/api/v1/meta": () => jsonResponse(meta),
    "/api/v1/stations": () => jsonResponse(stations),
  });
}

describe("DemoBanner", () => {
  it("lists the recorded period of each station in demo mode", async () => {
    serve(demoMeta, demoStations);

    renderWithQueryClient(<DemoBanner />);

    const banner = await screen.findByRole("complementary", { name: "Demo mode" });
    expect(banner).toHaveTextContent("Europe/Madrid time");
    expect(banner).toHaveTextContent("Juan Carlos I: 2025-03-01 01:00 to 2025-04-01 01:50");
    expect(banner).toHaveTextContent("Gabriel de Castilla: 2025-03-01 01:00 to 2025-04-01 01:50");
  });

  it("says when a station has no recorded data", async () => {
    const [first, second] = demoStations;
    if (first === undefined || second === undefined) {
      throw new Error("The fixture needs two stations.");
    }
    serve(demoMeta, [first, { ...second, available_range: null }]);

    renderWithQueryClient(<DemoBanner />);

    expect(await screen.findByText("Gabriel de Castilla: no recorded data")).toBeInTheDocument();
  });

  it("shows nothing with real AEMET data", async () => {
    serve(realMeta, realStations);

    const { client } = renderWithQueryClient(<DemoBanner />);

    await waitFor(() => {
      expect(client.getQueryState(["meta"])?.status).toBe("success");
      expect(client.getQueryState(["stations"])?.status).toBe("success");
    });
    expect(screen.queryByRole("complementary")).not.toBeInTheDocument();
  });
});
