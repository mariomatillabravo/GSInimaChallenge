/** Facts about a result that decide how it is shown (pure functions). */
import type { AggregationId, MeasurementsResponse } from "../api/client";

/**
 * Whether any row holds data. Aggregated rows say how many observations they use (`samples`);
 * ten-minute records only exist when there is data, so any row counts.
 */
export function hasData(result: MeasurementsResponse): boolean {
  return result.data.some((row) => row.samples == null || row.samples > 0);
}

const BUCKET_NOUNS: Record<Exclude<AggregationId, "none">, [string, string]> = {
  hourly: ["hour", "hours"],
  daily: ["day", "days"],
  monthly: ["month", "months"],
};

/** "169 empty hours", "1 empty day": what the hidden rows of a result without data are. */
export function emptyRowsText(aggregation: AggregationId, count: number): string {
  if (aggregation === "none") {
    return `${String(count)} empty ${count === 1 ? "row" : "rows"}`;
  }
  const [one, many] = BUCKET_NOUNS[aggregation];
  return `${String(count)} empty ${count === 1 ? one : many}`;
}
