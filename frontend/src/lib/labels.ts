import type { AggregationId } from "../api/client";

/** How each aggregation level is named in the interface. */
export const AGGREGATION_LABELS: Record<AggregationId, string> = {
  none: "10-minute records",
  hourly: "Hourly means",
  daily: "Daily means",
  monthly: "Monthly means",
};
