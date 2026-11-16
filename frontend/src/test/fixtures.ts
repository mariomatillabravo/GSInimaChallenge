/**
 * API responses for tests, copied from the API running in demo mode. Typed with the generated
 * types, so a contract change that breaks them fails the type check.
 */
import type { MetaResponse, Station } from "../api/client";

export const demoMeta: MetaResponse = {
  source: "demo",
  output_timezone: "Europe/Madrid",
  default_input_timezone: "Europe/Madrid",
  aggregations: [
    { id: "none", max_range_days: 31 },
    { id: "hourly", max_range_days: 366 },
    { id: "daily", max_range_days: 3660 },
    { id: "monthly", max_range_days: null },
  ],
  measurement_types: [
    { id: "temperature", key: "temperature_c", label: "Temperature (°C)", unit: "°C" },
    { id: "pressure", key: "pressure_hpa", label: "Pressure (hPa)", unit: "hPa" },
    { id: "speed", key: "speed_ms", label: "Speed (m/s)", unit: "m/s" },
  ],
};

export const realMeta: MetaResponse = { ...demoMeta, source: "aemet" };

export const demoStations: Station[] = [
  {
    id: "juan-carlos-i",
    name: "Juan Carlos I",
    aemet_id: "89064",
    aemet_name: "JCI Estacion meteorologica",
    latitude: -62.66325,
    longitude: -60.38959,
    altitude_m: 12.0,
    timezone: "UTC-03:00",
    available_range: { start: "2025-03-01T01:00:00+01:00", end: "2025-04-01T01:50:00+02:00" },
  },
  {
    id: "gabriel-de-castilla",
    name: "Gabriel de Castilla",
    aemet_id: "89070",
    aemet_name: "GdC Estacion meteorologica",
    latitude: -62.97697,
    longitude: -60.67528,
    altitude_m: 12.0,
    timezone: "UTC-03:00",
    available_range: { start: "2025-03-01T01:00:00+01:00", end: "2025-04-01T01:50:00+02:00" },
  },
];

export const realStations: Station[] = demoStations.map((station) => ({
  ...station,
  available_range: null,
}));
