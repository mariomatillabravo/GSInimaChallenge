/**
 * Show an API datetime ("2025-03-01T01:00:00+01:00") as "2025-03-01 01:00".
 *
 * API datetimes are already in Europe/Madrid, so only the text changes. Formatting them through
 * a Date would convert them to the browser's time zone, which may not be Madrid.
 */
export function formatApiDateTime(value: string): string {
  return value.slice(0, 16).replace("T", " ");
}

/**
 * Show an API datetime with its UTC offset: "2025-10-26 02:00 +01:00". On the night summer time
 * ends, Madrid lives 02:00 to 03:00 twice; the offset tells the two apart.
 */
export function formatApiDateTimeWithOffset(value: string): string {
  return `${formatApiDateTime(value)} ${value.slice(19)}`;
}

/**
 * The instant of an API datetime, in milliseconds since 1970 (UTC), to sort by real time.
 *
 * Sorting the text is wrong when the offset changes: "2025-10-26T02:00:00+01:00" sorts before
 * "2025-10-26T02:00:00+02:00", yet it happens an hour later. Parsing is safe here because every
 * API datetime carries its offset: the browser's time zone plays no part.
 */
export function apiInstant(value: string): number {
  return Date.parse(value);
}
