import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ErrorBoundary } from "./ErrorBoundary";

function Broken(): never {
  throw new Error("Failed to fetch dynamically imported module");
}

describe("ErrorBoundary", () => {
  it("shows its children while they work", () => {
    render(
      <ErrorBoundary fallback={<p>Fallback</p>}>
        <p>Content</p>
      </ErrorBoundary>,
    );

    expect(screen.getByText("Content")).toBeInTheDocument();
  });

  it("replaces failing children with the fallback, leaving the rest of the page", () => {
    // React reports the caught error on the console; keep the test output clean.
    const consoleError = vi.spyOn(console, "error").mockImplementation(() => undefined);
    render(
      <>
        <ErrorBoundary fallback={<p>Fallback</p>}>
          <Broken />
        </ErrorBoundary>
        <p>Rest of the page</p>
      </>,
    );

    expect(screen.getByText("Fallback")).toBeInTheDocument();
    expect(screen.getByText("Rest of the page")).toBeInTheDocument();
    consoleError.mockRestore();
  });
});
