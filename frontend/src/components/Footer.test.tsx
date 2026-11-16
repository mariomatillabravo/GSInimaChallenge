import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { AEMET_LEGAL_NOTICE_URL, AEMET_OPENDATA_URL, Footer } from "./Footer";

describe("Footer", () => {
  it("credits AEMET as the author of the data", () => {
    render(<Footer />);

    expect(screen.getByRole("contentinfo")).toHaveTextContent("© AEMET");
    expect(screen.getByRole("link", { name: "AEMET OpenData" })).toHaveAttribute(
      "href",
      AEMET_OPENDATA_URL,
    );
    expect(screen.getByRole("link", { name: "legal notice" })).toHaveAttribute(
      "href",
      AEMET_LEGAL_NOTICE_URL,
    );
  });
});
