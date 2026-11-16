import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

// Testing Library unmounts rendered components by itself only when test globals are enabled.
// They are not (tests import describe, it and expect explicitly), so it is done here.
afterEach(() => {
  cleanup();
});
