/**
 * API responses for tests, copied from the API running in demo mode. Typed with the generated
 * types, so a contract change that breaks them fails the type check.
 */
import type { MeasurementsResponse, MetaResponse, Station } from "../api/client";

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

const allFields: MeasurementsResponse["fields"] = {
  station: { label: "Station", unit: null },
  datetime: { label: "Datetime", unit: null },
  period: { label: "Period", unit: null },
  temperature_c: { label: "Temperature (°C)", unit: "°C" },
  pressure_hpa: { label: "Pressure (hPa)", unit: "hPa" },
  speed_ms: { label: "Speed (m/s)", unit: "m/s" },
  samples: { label: "Samples", unit: null },
  expected_samples: { label: "Expected samples", unit: null },
  coverage: { label: "Coverage (%)", unit: "%" },
};

/** Daily means of Juan Carlos I, 2025-03-30T00:00:00 to 2025-04-01T00:00:00 (Madrid). */
export const dailyMeasurements: MeasurementsResponse = {
  metadata: {
    station: {
      id: "juan-carlos-i",
      name: "Juan Carlos I",
      aemet_id: "89064",
      aemet_name: "JCI Estacion meteorologica",
    },
    aggregation: "daily",
    start: "2025-03-30T00:00:00+01:00",
    end: "2025-04-01T00:00:00+02:00",
    input_interpretation: "Europe/Madrid (default)",
    output_timezone: "Europe/Madrid",
    station_timezone: "UTC-03:00",
    source: "demo",
    cache: { status: "miss", last_updated: null, stale: false },
    count: 3,
  },
  fields: allFields,
  data: [
    {
      station: "Juan Carlos I",
      datetime: "2025-03-29T04:00:00+01:00",
      period: "2025-03-29",
      temperature_c: 0.51,
      pressure_hpa: 981.86,
      speed_ms: 2.81,
      samples: 24,
      expected_samples: 144,
      coverage: 16.7,
    },
    {
      station: "Juan Carlos I",
      datetime: "2025-03-30T05:00:00+02:00",
      period: "2025-03-30",
      temperature_c: 0.64,
      pressure_hpa: 980.74,
      speed_ms: 2.3,
      samples: 144,
      expected_samples: 144,
      coverage: 100.0,
    },
    {
      station: "Juan Carlos I",
      datetime: "2025-03-31T05:00:00+02:00",
      period: "2025-03-31",
      temperature_c: -0.17,
      pressure_hpa: 987.77,
      speed_ms: 1.9,
      samples: 115,
      expected_samples: 144,
      coverage: 79.9,
    },
  ],
};

/** Daily means outside the recorded data, 2025-05-01T00:00:00 to 2025-05-02T00:00:00. */
export const emptyMeasurements: MeasurementsResponse = {
  metadata: {
    ...dailyMeasurements.metadata,
    start: "2025-05-01T00:00:00+02:00",
    end: "2025-05-02T00:00:00+02:00",
    count: 2,
    notice:
      "Demo mode: there is no recorded data in this range. Recorded data for Juan Carlos I " +
      "covers 2025-03-01T01:00:00+01:00 to 2025-04-01T01:50:00+02:00.",
  },
  fields: allFields,
  data: [
    {
      station: "Juan Carlos I",
      datetime: "2025-04-30T05:00:00+02:00",
      period: "2025-04-30",
      temperature_c: null,
      pressure_hpa: null,
      speed_ms: null,
      samples: 0,
      expected_samples: 144,
      coverage: 0.0,
    },
    {
      station: "Juan Carlos I",
      datetime: "2025-05-01T05:00:00+02:00",
      period: "2025-05-01",
      temperature_c: null,
      pressure_hpa: null,
      speed_ms: null,
      samples: 0,
      expected_samples: 144,
      coverage: 0.0,
    },
  ],
};
