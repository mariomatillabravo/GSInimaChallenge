/** State and rules of the query form (pure functions). */
import type { AggregationId, MeasurementTypeId, MetaResponse, Station } from "../api/client";
import type { SubmittedQuery } from "../api/queries";
import { checkRange, demoDefaultRange, recentDefaultRange, toApiDateTime } from "./range";

export interface FormValues {
  stationId: string;
  start: string;
  end: string;
  aggregation: AggregationId;
  types: MeasurementTypeId[];
  /** Ask for the wind-energy metrics; they only exist for aggregated levels. */
  windMetrics: boolean;
}

export type FormField = "station" | "start" | "end" | "aggregation" | "types";
export type FieldErrors = Partial<Record<FormField, string>>;

/**
 * The values the form starts with: the first station, hourly means of every measurement, and a
 * range with data. In demo mode, the last two recorded days; with real data, the last seven days.
 */
export function initialValues(meta: MetaResponse, stations: Station[], now: Date): FormValues {
  const station = stations[0];
  const recorded = station?.available_range;
  const range =
    meta.source === "demo" && recorded
      ? demoDefaultRange(recorded.end)
      : recentDefaultRange(now, meta.default_input_timezone);
  return {
    stationId: station?.id ?? "",
    ...range,
    aggregation: "hourly",
    types: meta.measurement_types.map((type) => type.id),
    windMetrics: false,
  };
}

/** Wind-energy metrics are statistics of a bucket: the API rejects them for raw records. */
export function windMetricsAvailable(aggregation: AggregationId): boolean {
  return aggregation !== "none";
}

/** Problems found before sending; the API still has the last word (see checkRange). */
export function validate(values: FormValues, meta: MetaResponse): FieldErrors {
  const errors: FieldErrors = {};
  if (values.stationId === "") {
    errors.station = "Choose a station.";
  }
  if (values.types.length === 0) {
    errors.types = "Select at least one measurement.";
  }
  const level = meta.aggregations.find((candidate) => candidate.id === values.aggregation);
  const problem = checkRange(values.start, values.end, level?.max_range_days ?? null);
  if (problem !== null) {
    errors[problem.field] = problem.message;
  }
  return errors;
}

export function toQuery(values: FormValues): SubmittedQuery {
  return {
    stationId: values.stationId,
    params: {
      start: toApiDateTime(values.start),
      end: toApiDateTime(values.end),
      aggregation: values.aggregation,
      types: values.types,
      // Left out (undefined) unless it applies, so the URL only carries it when it matters.
      metrics:
        values.windMetrics && windMetricsAvailable(values.aggregation) ? "extended" : undefined,
    },
  };
}

const FIELD_OF_PARAMETER: Readonly<Record<string, FormField>> = {
  start: "start",
  end: "end",
  aggregation: "aggregation",
  types: "types",
};

/** The form field an API error refers to, so the message can be shown next to it. */
export function formFieldOf(parameter: string | null): FormField | null {
  return parameter === null ? null : (FIELD_OF_PARAMETER[parameter] ?? null);
}
