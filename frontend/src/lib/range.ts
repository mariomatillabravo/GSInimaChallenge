/**
 * Date and time handling of the query form (pure functions).
 *
 * A datetime-local input holds a wall-clock time without a time zone, such as "2025-03-30T00:00".
 * The form sends it as is, and the API interprets it in Europe/Madrid. These functions never turn
 * such a value into a Date: that would interpret it in the browser's time zone, which may not be
 * Madrid. Date.UTC is used only as a calendar, to count days and minutes.
 */

/** "YYYY-MM-DDTHH:MM", optionally with ":SS", as datetime-local inputs produce. */
export type LocalDateTime = string;

const LOCAL_DATETIME = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2})?$/;
const MINUTES_PER_DAY = 24 * 60;

/**
 * The most a daylight saving time change can make real elapsed time differ from the calendar
 * difference in Europe/Madrid: the clocks move by one hour.
 */
export const DST_TOLERANCE_MINUTES = 60;

/** The API expects seconds: "2025-03-30T00:00" becomes "2025-03-30T00:00:00". */
export function toApiDateTime(value: LocalDateTime): string {
  return value.length === 16 ? `${value}:00` : value;
}

/** Minutes from a fixed origin, counting every calendar day as 24 hours; null if malformed. */
export function wallClockMinutes(value: LocalDateTime): number | null {
  if (!LOCAL_DATETIME.test(value)) {
    return null;
  }
  const part = (start: number, end: number) => Number(value.slice(start, end));
  const milliseconds = Date.UTC(
    part(0, 4),
    part(5, 7) - 1,
    part(8, 10),
    part(11, 13),
    part(14, 16),
  );
  return milliseconds / 60_000;
}

export interface RangeProblem {
  field: "start" | "end";
  message: string;
}

/**
 * Orientative check of a range before sending it. The API measures the real time elapsed between
 * the two instants; this check only sees calendar values, which differ from it by up to one hour
 * across a daylight saving time change. It therefore rejects only ranges that are too long even
 * with that hour of margin: it never rejects a range the API would accept, and the API's 422
 * answers the doubtful cases.
 */
export function checkRange(
  start: LocalDateTime,
  end: LocalDateTime,
  maxRangeDays: number | null,
): RangeProblem | null {
  const startMinutes = wallClockMinutes(start);
  const endMinutes = wallClockMinutes(end);
  if (startMinutes === null) {
    return { field: "start", message: "Enter a start date and time." };
  }
  if (endMinutes === null) {
    return { field: "end", message: "Enter an end date and time." };
  }
  if (endMinutes <= startMinutes) {
    return { field: "end", message: "The end must be later than the start." };
  }
  if (
    maxRangeDays !== null &&
    endMinutes - startMinutes > maxRangeDays * MINUTES_PER_DAY + DST_TOLERANCE_MINUTES
  ) {
    return {
      field: "end",
      message:
        `The range is longer than ${String(maxRangeDays)} days, the maximum for this ` +
        "aggregation. Shorten it or choose a coarser aggregation.",
    };
  }
  return null;
}

/** Shift a calendar date ("YYYY-MM-DD") by a number of days. */
export function shiftDate(date: string, days: number): string {
  const shifted = new Date(
    Date.UTC(
      Number(date.slice(0, 4)),
      Number(date.slice(5, 7)) - 1,
      Number(date.slice(8, 10)) + days,
    ),
  );
  return shifted.toISOString().slice(0, 10);
}

/** The wall-clock time of an instant in a time zone, as "YYYY-MM-DDTHH:MM". */
export function wallClockAt(instant: Date, timeZone: string): LocalDateTime {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).formatToParts(instant);
  const get = (type: Intl.DateTimeFormatPartTypes) =>
    parts.find((part) => part.type === type)?.value ?? "00";
  return `${get("year")}-${get("month")}-${get("day")}T${get("hour")}:${get("minute")}`;
}

export interface LocalRange {
  start: LocalDateTime;
  end: LocalDateTime;
}

/**
 * Demo mode: the last two days of recorded data, from midnight to midnight. With the current
 * recording (March 2025) this covers the change to summer time on 30 March.
 *
 * @param recordedEnd The end of the station's recorded data, as the API returns it.
 */
export function demoDefaultRange(recordedEnd: string): LocalRange {
  const lastDay = recordedEnd.slice(0, 10);
  return { start: `${shiftDate(lastDay, -2)}T00:00`, end: `${lastDay}T00:00` };
}

/**
 * Real data: the last seven days, from midnight seven days ago to the current hour, in the given
 * time zone. Starting at midnight avoids the times a daylight saving time change skips or
 * repeats (02:00 to 03:00 in Madrid). The end, the current hour, can only hit one of them
 * between 02:00 and 03:00 on the night summer time ends; the API then explains it with a 422.
 */
export function recentDefaultRange(now: Date, timeZone: string): LocalRange {
  const current = wallClockAt(now, timeZone);
  return {
    start: `${shiftDate(current.slice(0, 10), -7)}T00:00`,
    end: `${current.slice(0, 13)}:00`,
  };
}
