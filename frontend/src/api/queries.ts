import { keepPreviousData, skipToken, useQuery } from "@tanstack/react-query";

import { fetchMeasurements, fetchMeta, fetchStations, type MeasurementsQuery } from "./client";

/** Options and limits of the API. They only change when the API restarts. */
export function useMeta() {
  return useQuery({
    queryKey: ["meta"],
    queryFn: ({ signal }) => fetchMeta(signal),
    staleTime: Infinity,
  });
}

/** The stations, with the span of their recorded data in demo mode. Fixed while the API runs. */
export function useStations() {
  return useQuery({
    queryKey: ["stations"],
    queryFn: ({ signal }) => fetchStations(signal),
    staleTime: Infinity,
  });
}

/** A query the user submitted with the form. */
export interface SubmittedQuery {
  stationId: string;
  params: MeasurementsQuery;
}

/**
 * The measurements of the last submitted query; nothing is requested before the first one
 * (skipToken). While a new query loads, the previous result stays on screen.
 */
export function useMeasurements(query: SubmittedQuery | null) {
  return useQuery({
    queryKey: ["measurements", query],
    queryFn:
      query === null
        ? skipToken
        : ({ signal }) => fetchMeasurements(query.stationId, query.params, signal),
    placeholderData: keepPreviousData,
  });
}
