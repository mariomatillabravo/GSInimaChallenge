import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { type Column, DataTable } from "./DataTable";

interface Item {
  id: number;
  value: number | null;
}

const columns: Column<Item>[] = [
  { key: "id", header: "Id", render: (row) => row.id, sortValue: (row) => row.id, numeric: true },
  {
    key: "value",
    header: "Value",
    render: (row) => row.value ?? "—",
    sortValue: (row) => row.value,
    numeric: true,
  },
];

/** Items 1..count; every tenth one has no value. */
function itemsUpTo(count: number): Item[] {
  return Array.from({ length: count }, (_, index) => ({
    id: index + 1,
    value: (index + 1) % 10 === 0 ? null : index + 1,
  }));
}

function renderTable(rows: Item[], initialSort = true) {
  const user = userEvent.setup();
  render(
    <DataTable
      caption="Items"
      columns={columns}
      rows={rows}
      rowKey={(row) => String(row.id)}
      initialSort={initialSort ? { column: "id", direction: "ascending" } : undefined}
    />,
  );
  return user;
}

/** The text of the first cell of every body row on screen. */
function firstColumn(): string[] {
  const table = screen.getByRole("table", { name: "Items" });
  const [, ...bodyRows] = within(table).getAllByRole("row");
  return bodyRows.map((row) => within(row).getAllByRole("cell")[0]?.textContent ?? "");
}

describe("DataTable", () => {
  it("shows the initial sort on its header", () => {
    renderTable(itemsUpTo(3));

    expect(screen.getByRole("columnheader", { name: "Id" })).toHaveAttribute(
      "aria-sort",
      "ascending",
    );
    expect(screen.getByRole("columnheader", { name: "Value" })).not.toHaveAttribute("aria-sort");
  });

  it("sorts ascending on the first click and switches direction on the next", async () => {
    const user = renderTable(itemsUpTo(12));
    const value = screen.getByRole("columnheader", { name: "Value" });

    await user.click(within(value).getByRole("button"));
    expect(value).toHaveAttribute("aria-sort", "ascending");
    expect(screen.getByRole("columnheader", { name: "Id" })).not.toHaveAttribute("aria-sort");
    expect(firstColumn().slice(0, 2)).toEqual(["1", "2"]);

    await user.click(within(value).getByRole("button"));
    expect(value).toHaveAttribute("aria-sort", "descending");
    expect(firstColumn().slice(0, 2)).toEqual(["12", "11"]);
  });

  it("puts rows without a value last in both directions", async () => {
    const user = renderTable(itemsUpTo(12));
    const value = within(screen.getByRole("columnheader", { name: "Value" })).getByRole("button");

    await user.click(value);
    expect(firstColumn().slice(-1)).toEqual(["10"]);
    await user.click(value);
    expect(firstColumn().slice(-1)).toEqual(["10"]);
  });

  it("keeps the order of the rows when there is no initial sort", () => {
    renderTable(
      [3, 1, 2].map((id) => ({ id, value: id })),
      false,
    );

    expect(firstColumn()).toEqual(["3", "1", "2"]);
  });

  it("shows 50 rows per page and moves between pages", async () => {
    const user = renderTable(itemsUpTo(120));
    const pages = screen.getByRole("navigation", { name: "Table pages" });

    expect(firstColumn()).toHaveLength(50);
    expect(pages).toHaveTextContent("Page 1 of 3 · rows 1–50 of 120");
    expect(within(pages).getByRole("button", { name: "Previous" })).toBeDisabled();

    await user.click(within(pages).getByRole("button", { name: "Next" }));
    expect(firstColumn()[0]).toBe("51");

    await user.click(within(pages).getByRole("button", { name: "Last" }));
    expect(pages).toHaveTextContent("Page 3 of 3 · rows 101–120 of 120");
    expect(firstColumn()).toHaveLength(20);
    expect(within(pages).getByRole("button", { name: "Next" })).toBeDisabled();

    await user.click(within(pages).getByRole("button", { name: "First" }));
    expect(firstColumn()[0]).toBe("1");
  });

  it("goes back to the first page when the sort changes", async () => {
    const user = renderTable(itemsUpTo(120));
    const pages = screen.getByRole("navigation", { name: "Table pages" });
    await user.click(within(pages).getByRole("button", { name: "Last" }));

    await user.click(within(screen.getByRole("columnheader", { name: "Id" })).getByRole("button"));

    expect(pages).toHaveTextContent("Page 1 of 3");
    expect(firstColumn()[0]).toBe("120");
  });

  it("hides the page controls when everything fits in one page", () => {
    renderTable(itemsUpTo(50));

    expect(screen.queryByRole("navigation", { name: "Table pages" })).not.toBeInTheDocument();
  });

  it("says so when there are no rows", () => {
    renderTable([]);

    expect(screen.getByRole("cell", { name: "No rows." })).toBeInTheDocument();
  });
});
