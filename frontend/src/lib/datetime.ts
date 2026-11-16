/**
 * Show an API datetime ("2025-03-01T01:00:00+01:00") as "2025-03-01 01:00".
 *
 * API datetimes are already in Europe/Madrid, so only the text changes. Parsing them into a Date
 * would convert them to the browser's time zone, which may not be Madrid.
 */
export function formatApiDateTime(value: string): string {
  return value.slice(0, 16).replace("T", " ");
}
