import { type ReactNode, useId, useState } from "react";

import {
  clampPage,
  pageCount,
  pageRows,
  type SortState,
  type SortValue,
  sortRows,
} from "../lib/table";
import styles from "./DataTable.module.css";

export interface Column<Row> {
  key: string;
  header: string;
  /** The content of the cell. */
  render: (row: Row) => ReactNode;
  /** What the column sorts by; null goes last. */
  sortValue: (row: Row) => SortValue;
  /** Numbers are aligned to the end of the cell, so their digits line up. */
  numeric?: boolean;
}

interface Props<Row> {
  /** Names the table for screen readers. */
  caption: string;
  columns: readonly Column<Row>[];
  rows: readonly Row[];
  rowKey: (row: Row) => string;
  /** The order the rows arrive in, shown as the initial sort. */
  initialSort?: SortState;
  pageSize?: number;
}

/**
 * A table sorted and paginated in the browser. Every header is a button: the first click sorts
 * ascending, the next ones switch the direction. Sorting goes back to the first page.
 */
export function DataTable<Row>({
  caption,
  columns,
  rows,
  rowKey,
  initialSort,
  pageSize = 50,
}: Props<Row>) {
  const [sort, setSort] = useState<SortState | null>(initialSort ?? null);
  const [page, setPage] = useState(1);
  const captionId = useId();

  const sortColumn = columns.find((column) => column.key === sort?.column);
  const sorted =
    sort === null || sortColumn === undefined
      ? rows
      : sortRows(rows, sortColumn.sortValue, sort.direction);
  const pages = pageCount(rows.length, pageSize);
  const current = clampPage(page, rows.length, pageSize);
  const shown = pageRows(sorted, current, pageSize);

  function sortBy(column: string) {
    setSort((previous) =>
      previous?.column === column && previous.direction === "ascending"
        ? { column, direction: "descending" }
        : { column, direction: "ascending" },
    );
    setPage(1);
  }

  return (
    <div>
      {/* Scrolls sideways on narrow screens instead of the whole page; focusable for keyboards. */}
      <div className={styles.scroll} role="region" aria-labelledby={captionId} tabIndex={0}>
        <table className={styles.table}>
          {/* For screen readers only: the summary above the table already says what it holds. */}
          <caption id={captionId} className="visually-hidden">
            {caption}
          </caption>
          <thead>
            <tr>
              {columns.map((column) => {
                const direction = sort?.column === column.key ? sort.direction : undefined;
                return (
                  <th
                    key={column.key}
                    scope="col"
                    aria-sort={direction}
                    className={column.numeric ? styles.numeric : undefined}
                  >
                    <button
                      type="button"
                      className={styles.sortButton}
                      onClick={() => {
                        sortBy(column.key);
                      }}
                    >
                      {column.header}
                      <span className={styles.sortMark} aria-hidden="true">
                        {direction === undefined ? "" : direction === "ascending" ? "▲" : "▼"}
                      </span>
                    </button>
                  </th>
                );
              })}
            </tr>
          </thead>
          <tbody>
            {shown.length === 0 ? (
              <tr>
                <td colSpan={columns.length}>No rows.</td>
              </tr>
            ) : (
              shown.map((row) => (
                <tr key={rowKey(row)}>
                  {columns.map((column) => (
                    <td key={column.key} className={column.numeric ? styles.numeric : undefined}>
                      {column.render(row)}
                    </td>
                  ))}
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {pages > 1 ? (
        <nav className={styles.pages} aria-label="Table pages">
          <button
            type="button"
            disabled={current === 1}
            onClick={() => {
              setPage(1);
            }}
          >
            First
          </button>
          <button
            type="button"
            disabled={current === 1}
            onClick={() => {
              setPage(current - 1);
            }}
          >
            Previous
          </button>
          <span className={styles.position}>
            Page {current} of {pages} · rows {(current - 1) * pageSize + 1}–
            {Math.min(current * pageSize, rows.length)} of {rows.length}
          </span>
          <button
            type="button"
            disabled={current === pages}
            onClick={() => {
              setPage(current + 1);
            }}
          >
            Next
          </button>
          <button
            type="button"
            disabled={current === pages}
            onClick={() => {
              setPage(pages);
            }}
          >
            Last
          </button>
        </nav>
      ) : null}
    </div>
  );
}
