import { describe, expect, it } from "vitest";

import { clampPage, pageCount, pageRows, sortRows } from "./table";

interface Item {
  name: string;
  value: number | null;
}

const items: Item[] = [
  { name: "a", value: 2 },
  { name: "b", value: null },
  { name: "c", value: 10 },
  { name: "d", value: 2 },
  { name: "e", value: -1 },
];

const names = (rows: Item[]) => rows.map((row) => row.name);

describe("sortRows", () => {
  it("sorts numbers by value, not as text", () => {
    expect(names(sortRows(items, (row) => row.value, "ascending"))).toEqual([
      "e",
      "a",
      "d",
      "c",
      "b",
    ]);
  });

  it("reverses the order when descending, keeping rows without a value last", () => {
    expect(names(sortRows(items, (row) => row.value, "descending"))).toEqual([
      "c",
      "a",
      "d",
      "e",
      "b",
    ]);
  });

  it("keeps the original order of rows with the same value", () => {
    const sorted = sortRows(items, (row) => row.value, "descending");
    expect(names(sorted).filter((name) => name === "a" || name === "d")).toEqual(["a", "d"]);
  });

  it("sorts text without depending on the browser's language", () => {
    const periods = ["2025-03-31", "2025-03-29", "2025-03-30"];
    expect(sortRows(periods, (period) => period, "ascending")).toEqual([
      "2025-03-29",
      "2025-03-30",
      "2025-03-31",
    ]);
  });

  it("returns a copy and leaves the rows untouched", () => {
    const before = names(items);
    sortRows(items, (row) => row.value, "ascending");
    expect(names(items)).toEqual(before);
  });
});

describe("pagination", () => {
  const rows = Array.from({ length: 120 }, (_, index) => index + 1);

  it("counts the pages, with at least one", () => {
    expect(pageCount(120, 50)).toBe(3);
    expect(pageCount(100, 50)).toBe(2);
    expect(pageCount(0, 50)).toBe(1);
  });

  it("returns the rows of a page, the last one shorter", () => {
    expect(pageRows(rows, 1, 50)).toEqual(rows.slice(0, 50));
    expect(pageRows(rows, 3, 50)).toEqual(rows.slice(100, 120));
  });

  it("keeps the page number inside the pages that exist", () => {
    expect(clampPage(0, 120, 50)).toBe(1);
    expect(clampPage(7, 120, 50)).toBe(3);
    expect(pageRows(rows, 7, 50)).toEqual(rows.slice(100, 120));
  });
});
