import type { MeasurementsResponse } from "../api/client";
import { apiInstant, formatApiDateTimeWithOffset } from "../lib/datetime";
import { AGGREGATION_LABELS } from "../lib/labels";
import { type Column, DataTable } from "./DataTable";
import styles from "./MeasurementsTable.module.css";

type Row = MeasurementsResponse["data"][number];
type CellValue = string | number | null;

/**
 * Coverage below this percentage is marked: the bucket has fewer observations than a complete
 * one, so its means are less representative.
 */
const LOW_COVERAGE_PERCENT = 90;

/** A query covers one station, already named in the summary. */
const HIDDEN_COLUMNS = new Set(["station"]);

/** Columns holding text; every other one holds numbers. */
const TEXT_COLUMNS = new Set(["datetime", "period"]);

/** The value of any key of a row, read without knowing the key in advance. */
function valueOf(row: Row, key: string): CellValue {
  const record: Readonly<Record<string, unknown>> = row;
  const value = record[key];
  return typeof value === "string" || typeof value === "number" ? value : null;
}

function Value({ value }: { value: CellValue }) {
  return <>{value ?? "—"}</>;
}

function Coverage({ value }: { value: CellValue }) {
  if (typeof value !== "number" || value >= LOW_COVERAGE_PERCENT) {
    return <Value value={value} />;
  }
  return (
    <span className={styles.lowCoverage}>
      {value}
      <span aria-hidden="true"> ⚠</span>
      <span className="visually-hidden"> (below {LOW_COVERAGE_PERCENT} %)</span>
    </span>
  );
}

/**
 * One column per key of the response's `fields` block, in the API's order and with its official
 * label, so a field added to the API appears without changing this code.
 */
function columnsFor(fields: MeasurementsResponse["fields"]): Column<Row>[] {
  return Object.entries(fields)
    .filter(([key]) => !HIDDEN_COLUMNS.has(key))
    .map(([key, field]): Column<Row> => {
      if (key === "datetime") {
        return {
          key,
          header: field.label,
          render: (row) => formatApiDateTimeWithOffset(row.datetime),
          // By instant: on the night summer time ends, the text order of the two 02:00 is wrong.
          sortValue: (row) => apiInstant(row.datetime),
        };
      }
      return {
        key,
        header: field.label,
        numeric: !TEXT_COLUMNS.has(key),
        render: (row) =>
          key === "coverage" ? (
            <Coverage value={valueOf(row, key)} />
          ) : (
            <Value value={valueOf(row, key)} />
          ),
        sortValue: (row) => valueOf(row, key),
      };
    });
}

interface Props {
  result: MeasurementsResponse;
  /** The same query as CSV; null hides the link (while another query loads). */
  csvUrl: string | null;
}

/** The rows of a result, with their official labels, and the link to download them as CSV. */
export function MeasurementsTable({ result, csvUrl }: Props) {
  const { metadata } = result;
  return (
    <section className={styles.section} aria-label="Data">
      <div className={styles.toolbar}>
        <ul className={styles.legend}>
          <li>— means no data.</li>
          {"coverage" in result.fields ? (
            <li>
              ⚠ marks coverage below {LOW_COVERAGE_PERCENT} %: the means use fewer observations than
              a complete bucket has. The first and last buckets show it when the range starts or
              ends partway through them.
            </li>
          ) : null}
        </ul>
        {csvUrl === null ? null : (
          <a className={styles.download} href={csvUrl} download>
            Download CSV
          </a>
        )}
      </div>
      <DataTable
        caption={`${AGGREGATION_LABELS[metadata.aggregation]}, ${metadata.station.name}`}
        columns={columnsFor(result.fields)}
        rows={result.data}
        rowKey={(row) => row.datetime}
        initialSort={{ column: "datetime", direction: "ascending" }}
      />
    </section>
  );
}
