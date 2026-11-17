import { lazy, Suspense, useState } from "react";

import { ApiError, measurementsUrl } from "./api/client";
import { type SubmittedQuery, useMeasurements, useMeta, useStations } from "./api/queries";
import styles from "./App.module.css";
import { DemoBanner } from "./components/DemoBanner";
import { EmptyResult } from "./components/EmptyResult";
import { ErrorBoundary } from "./components/ErrorBoundary";
import { ErrorMessage } from "./components/ErrorMessage";
import { Footer } from "./components/Footer";
import { MeasurementsTable } from "./components/MeasurementsTable";
import { QueryForm } from "./components/QueryForm";
import { ResultSummary } from "./components/ResultSummary";
import { formFieldOf } from "./lib/queryForm";
import { hasData } from "./lib/result";

// Recharts is most of the front-end's code: the charts are fetched with the first result, so the
// page itself loads fast. lazy() needs a default export; the module exports a named component.
const MeasurementCharts = lazy(() =>
  import("./components/MeasurementCharts").then((module) => ({
    default: module.MeasurementCharts,
  })),
);

export function App() {
  const meta = useMeta();
  const stations = useStations();
  const [query, setQuery] = useState<SubmittedQuery | null>(null);
  const measurements = useMeasurements(query);

  const setupError = meta.error ?? stations.error;
  // An error about a form field (such as a non-existent local time) is shown next to the field.
  const fieldError =
    measurements.error instanceof ApiError && formFieldOf(measurements.error.parameter) !== null
      ? measurements.error
      : null;

  // While the next query loads, the previous result stays on screen; its CSV link is hidden,
  // because the submitted query is already the new one.
  const csvUrl =
    query === null || measurements.isPlaceholderData
      ? null
      : measurementsUrl(query.stationId, { ...query.params, format: "csv" });

  function handleSubmit(next: SubmittedQuery) {
    // The same query again (for example after a 503) would hit the same cache entry: fetch again.
    if (query !== null && JSON.stringify(next) === JSON.stringify(query)) {
      void measurements.refetch();
    } else {
      setQuery(next);
    }
  }

  return (
    <div className={styles.layout}>
      <header className={styles.header}>
        <h1 className={styles.title}>AEMET Antarctica Weather</h1>
        <p className={styles.subtitle}>Weather measurements from the Spanish Antarctic stations</p>
      </header>
      <main className={styles.main}>
        <DemoBanner />
        {setupError === null ? null : <ErrorMessage error={setupError} />}
        {meta.data && stations.data ? (
          <QueryForm
            meta={meta.data}
            stations={stations.data}
            pending={measurements.isFetching}
            fieldError={fieldError}
            onSubmit={handleSubmit}
          />
        ) : null}
        {measurements.error !== null && fieldError === null ? (
          <ErrorMessage error={measurements.error} />
        ) : null}
        {measurements.data && meta.data ? (
          // While a query loads, the previous result stays, dimmed, instead of a blank page.
          <div
            className={measurements.isFetching ? styles.refreshing : undefined}
            aria-busy={measurements.isFetching}
          >
            <ResultSummary result={measurements.data} />
            {hasData(measurements.data) ? (
              <>
                {/* If the charts' code cannot be loaded (offline, or a new deployment replaced it),
                    the rest of the result still works. */}
                <ErrorBoundary
                  fallback={
                    <p className={styles.chartsMessage} role="alert">
                      The charts could not be loaded. Reload the page to try again; the table below
                      has every value.
                    </p>
                  }
                >
                  <Suspense fallback={<p className={styles.chartsMessage}>Loading charts…</p>}>
                    <MeasurementCharts result={measurements.data} meta={meta.data} />
                  </Suspense>
                </ErrorBoundary>
                {/* A new result is a new table: first page, in the API's order. */}
                <MeasurementsTable
                  key={measurements.dataUpdatedAt}
                  result={measurements.data}
                  csvUrl={csvUrl}
                />
              </>
            ) : (
              // No data at all: the summary's notice says why; the empty rows are one click away.
              <EmptyResult
                key={measurements.dataUpdatedAt}
                result={measurements.data}
                csvUrl={csvUrl}
              />
            )}
          </div>
        ) : null}
      </main>
      <Footer />
    </div>
  );
}
