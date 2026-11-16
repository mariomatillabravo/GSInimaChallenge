/** Sorting and pagination of the rows of a table (pure functions). */

/** What a column sorts by. null (no data) always goes last. */
export type SortValue = string | number | null;

export type SortDirection = "ascending" | "descending";

export interface SortState {
  column: string;
  direction: SortDirection;
}

function compare(a: string | number, b: string | number): number {
  // Plain comparison, not localeCompare: the text columns hold dates such as "2025-03-30",
  // whose order must not depend on the browser's language.
  if (a < b) {
    return -1;
  }
  return a > b ? 1 : 0;
}

/**
 * A sorted copy of the rows. Rows with the same value keep their order (Array.prototype.sort is
 * stable), and rows without a value go last in both directions: the data that exists comes
 * first whichever way the column is sorted.
 */
export function sortRows<Row>(
  rows: readonly Row[],
  value: (row: Row) => SortValue,
  direction: SortDirection,
): Row[] {
  const sign = direction === "ascending" ? 1 : -1;
  return [...rows].sort((rowA, rowB) => {
    const a = value(rowA);
    const b = value(rowB);
    if (a === null || b === null) {
      return Number(a === null) - Number(b === null);
    }
    return sign * compare(a, b);
  });
}

/** Number of pages; an empty table still has one, empty page. */
export function pageCount(total: number, pageSize: number): number {
  return Math.max(1, Math.ceil(total / pageSize));
}

/** Keep a page number (counted from 1) inside the pages that exist. */
export function clampPage(page: number, total: number, pageSize: number): number {
  return Math.min(Math.max(1, page), pageCount(total, pageSize));
}

/** The rows of one page, counted from 1. */
export function pageRows<Row>(rows: readonly Row[], page: number, pageSize: number): Row[] {
  const first = (clampPage(page, rows.length, pageSize) - 1) * pageSize;
  return rows.slice(first, first + pageSize);
}
