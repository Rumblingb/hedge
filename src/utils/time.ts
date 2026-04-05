import { DateTime } from "luxon";

export const CHICAGO_TZ = "America/Chicago";

function toMinutes(hhmm: string): number {
  const [hours, minutes] = hhmm.split(":").map((value) => Number(value));
  return (hours * 60) + minutes;
}

export function chicagoTime(iso: string): DateTime {
  return DateTime.fromISO(iso, { zone: "utc" }).setZone(CHICAGO_TZ);
}

export function chicagoDateKey(iso: string): string {
  return chicagoTime(iso).toFormat("yyyy-LL-dd");
}

export function minutesSinceMidnightCt(iso: string): number {
  const dt = chicagoTime(iso);
  return (dt.hour * 60) + dt.minute;
}

export function isWithinCtWindow(iso: string, start: string, end: string): boolean {
  const value = minutesSinceMidnightCt(iso);
  return value >= toMinutes(start) && value <= toMinutes(end);
}

export function isAfterCtTime(iso: string, cutoff: string): boolean {
  return minutesSinceMidnightCt(iso) > toMinutes(cutoff);
}

export function elapsedMinutes(startIso: string, endIso: string): number {
  const start = DateTime.fromISO(startIso, { zone: "utc" });
  const end = DateTime.fromISO(endIso, { zone: "utc" });
  return Math.floor(end.diff(start, "minutes").minutes);
}

export function minutesFromCtTime(iso: string, hhmm: string): number {
  return minutesSinceMidnightCt(iso) - toMinutes(hhmm);
}
