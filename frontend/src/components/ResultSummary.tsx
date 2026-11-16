import type { MeasurementsResponse } from "../api/client";
import { formatApiDateTime } from "../lib/datetime";
import { AGGREGATION_LABELS } from "../lib/labels";
import styles from "./ResultSummary.module.css";

/** What the API answered: how many rows, for which range, and how fresh the data is. */
export function ResultSummary({ result }: { result: MeasurementsResponse }) {
  const { metadata } = result;
  const source = metadata.source === "demo" ? "the recorded data" : "AEMET";
  const origin = {
    hit: "Served from the cache",
    partial: `Partly fetched from ${source}`,
    miss: `Fetched from ${source}`,
  }[metadata.cache.status];
  const lastUpdated = metadata.cache.last_updated;

  return (
    <section className={styles.summary} aria-label="Result">
      <p className={styles.line}>
        <strong>
          {metadata.count} {metadata.count === 1 ? "row" : "rows"}
        </strong>{" "}
        · {metadata.station.name} · {AGGREGATION_LABELS[metadata.aggregation]} ·{" "}
        {formatApiDateTime(metadata.start)} to {formatApiDateTime(metadata.end)} (
        {metadata.input_interpretation}) · {origin}
      </p>
      {metadata.cache.stale ? (
        <p className={styles.warning} role="status">
          AEMET is not answering, so part of this data comes from an older copy
          {lastUpdated ? `, last updated ${formatApiDateTime(lastUpdated)}` : ""}.
        </p>
      ) : null}
      {metadata.notice ? <p className={styles.notice}>{metadata.notice}</p> : null}
    </section>
  );
}
