import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { App } from "./App";
import { jsonResponse, stubFetch } from "./test/fetch";
import { demoMeta, demoStations } from "./test/fixtures";
import { renderWithQueryClient } from "./test/render";

describe("App", () => {
  it("renders the title, the demo banner and the attribution footer", async () => {
    stubFetch({
      "/api/v1/meta": () => jsonResponse(demoMeta),
      "/api/v1/stations": () => jsonResponse(demoStations),
    });

    renderWithQueryClient(<App />);

    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("AEMET Antarctica Weather");
    expect(await screen.findByRole("complementary", { name: "Demo mode" })).toBeInTheDocument();
    expect(screen.getByRole("contentinfo")).toBeInTheDocument();
  });
});
