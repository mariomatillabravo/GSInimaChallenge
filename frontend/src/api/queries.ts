import { useQuery } from "@tanstack/react-query";

import { fetchMeta, fetchStations } from "./client";

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
