import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type { MeasurementsResponse, MetaResponse } from "../api/client";
import {
  type ChartPoint,
  chartPoints,
  formatTick,
  isolatedIndexes,
  measurementValue,
  suggestAggregation,
  timeTicks,
} from "../lib/chart";
import { apiInstant } from "../lib/datetime";
import { AGGREGATION_LABELS } from "../lib/labels";
import { ChartTooltip } from "./ChartTooltip";
import styles from "./MeasurementCharts.module.css";

const CHART_HEIGHT = 180;
/** The same for every chart, so their plot areas, and their time axes, line up. */
const Y_AXIS_WIDTH = 56;
const count = new Intl.NumberFormat("en-US");

interface ChartProps {
  points: ChartPoint[];
  measurementKey: string;
  label: string;
  unit: string;
  ticks: number[];
  formatX: (instant: number) => string;
}

/** One measurement over time. Colours come from the CSS Module, so they follow the theme. */
function MeasurementChart({ points, measurementKey, label, unit, ticks, formatX }: ChartProps) {
  const isolated = isolatedIndexes(points.map((point) => measurementValue(point, measurementKey)));
  return (
    <figure className={styles.figure}>
      <figcaption className={styles.caption}>{label}</figcaption>
      {/* initialDimension: the size before the container is measured (and in tests, where it never is). */}
      <ResponsiveContainer
        width="100%"
        height={CHART_HEIGHT}
        initialDimension={{ width: 800, height: CHART_HEIGHT }}
      >
        <LineChart data={points} syncId="measurements" margin={{ top: 8, right: 16, left: 0 }}>
          <CartesianGrid vertical={false} />
          <XAxis
            dataKey="x"
            type="number"
            domain={["dataMin", "dataMax"]}
            ticks={ticks}
            tickFormatter={formatX}
          />
          <YAxis width={Y_AXIS_WIDTH} domain={["auto", "auto"]} />
          <Tooltip
            isAnimationActive={false}
            content={({ active, activeIndex }) => (
              <ChartTooltip
                point={active ? points[Number(activeIndex)] : undefined}
                measurementKey={measurementKey}
                unit={unit}
              />
            )}
          />
          <Line
            dataKey={(point: ChartPoint) => measurementValue(point, measurementKey)}
            name={label}
            strokeWidth={2}
            connectNulls={false}
            isAnimationActive={false}
            // A value with no neighbours has no line to sit on: draw it as a dot.
            dot={({ cx, cy, index }) =>
              isolated.has(index) ? (
                <circle key={index} className={styles.dot} cx={cx} cy={cy} r={4} />
              ) : null
            }
            activeDot={{ r: 4, className: styles.activeDot }}
          />
        </LineChart>
      </ResponsiveContainer>
    </figure>
  );
}

interface Props {
  result: MeasurementsResponse;
  meta: MetaResponse;
}

/**
 * One chart per measurement in the result, stacked, all on the same time axis (small
 * multiples): each keeps its own scale, so no chart needs a second axis.
 */
export function MeasurementCharts({ result, meta }: Props) {
  const { metadata } = result;
  const points = chartPoints(result.data, metadata.aggregation);
  const first = points[0];
  const last = points.at(-1);
  const measurements = meta.measurement_types.filter((type) => type.key in result.fields);
  if (first === undefined || last === undefined || measurements.length === 0) {
    return null;
  }
  const { ticks, unit } = timeTicks(first.x, last.x, meta.output_timezone);
  const formatX = (instant: number) => formatTick(instant, unit, meta.output_timezone);
  const suggestion = suggestAggregation(
    meta.aggregations,
    metadata.aggregation,
    apiInstant(metadata.start),
    apiInstant(metadata.end),
    result.data.length,
  );

  return (
    <section className={styles.section} aria-label="Charts">
      {suggestion === null ? null : (
        <p className={styles.density}>
          {count.format(result.data.length)} points per chart, more than a chart can show clearly.{" "}
          {AGGREGATION_LABELS[suggestion.aggregation]} (about {count.format(suggestion.points)}{" "}
          points) would show the trend better.
        </p>
      )}
      {measurements.map((type) => (
        <MeasurementChart
          key={type.key}
          points={points}
          measurementKey={type.key}
          label={result.fields[type.key]?.label ?? type.label}
          unit={type.unit}
          ticks={ticks}
          formatX={formatX}
        />
      ))}
    </section>
  );
}
