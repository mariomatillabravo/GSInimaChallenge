import type { TimeSpan } from "../api/client";
import { useMeta, useStations } from "../api/queries";
import { formatApiDateTime } from "../lib/datetime";
import styles from "./DemoBanner.module.css";

/** In demo mode, tells the user that the data is recorded and which periods it covers. */
export function DemoBanner() {
  const meta = useMeta();
  const stations = useStations();
  if (meta.data?.source !== "demo" || stations.data === undefined) {
    return null;
  }
  return (
    <aside className={styles.banner} aria-label="Demo mode">
      <p className={styles.text}>
        <strong>Demo mode.</strong> The API serves recorded AEMET data, so only these periods have
        measurements ({meta.data.output_timezone} time):
      </p>
      <ul className={styles.list}>
        {stations.data.map((station) => (
          <li key={station.id}>
            {station.name}: {describeRange(station.available_range)}
          </li>
        ))}
      </ul>
    </aside>
  );
}

function describeRange(range: TimeSpan | null | undefined): string {
  if (range === null || range === undefined) {
    return "no recorded data";
  }
  return `${formatApiDateTime(range.start)} to ${formatApiDateTime(range.end)}`;
}
