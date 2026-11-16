import { type ChartPoint, measurementValue } from "../lib/chart";
import { formatApiDateTimeWithOffset } from "../lib/datetime";
import styles from "./MeasurementCharts.module.css";

interface Props {
  /** The point under the cursor; nothing is shown for a break in the line. */
  point: ChartPoint | undefined;
  measurementKey: string;
  unit: string;
}

/**
 * The reading at the cursor: the value first, then when it was measured (the API's own text,
 * with its offset) and, for aggregated rows, how many observations it is based on.
 */
export function ChartTooltip({ point, measurementKey, unit }: Props) {
  if (point?.row == null) {
    return null;
  }
  const { row } = point;
  const value = measurementValue(point, measurementKey);
  return (
    <div className={styles.tooltip}>
      <p className={styles.tooltipValue}>
        {value === null ? "No data" : `${String(value)} ${unit}`}
      </p>
      <p className={styles.tooltipLine}>{formatApiDateTimeWithOffset(row.datetime)}</p>
      {row.coverage == null ? null : (
        <p className={styles.tooltipLine}>
          {row.samples}/{row.expected_samples} samples · {row.coverage} % coverage
        </p>
      )}
    </div>
  );
}
