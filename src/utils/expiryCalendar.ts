import { DateTime } from "luxon";
import { CHICAGO_TZ } from "./time.js";

export type ExpiryWindow =
  | "vix-wednesday"
  | "monthly-opex"
  | "quarterly-expiry"
  | "roll-window";

export interface ExpiryEvent {
  date: string;
  kind: ExpiryWindow;
  label: string;
}

function nthWeekdayOfMonth(year: number, month: number, weekday: number, n: number): DateTime {
  const first = DateTime.fromObject({ year, month, day: 1 }, { zone: CHICAGO_TZ });
  const offset = (weekday - first.weekday + 7) % 7;
  return first.plus({ days: offset + (n - 1) * 7 });
}

function thirdFridayOf(year: number, month: number): DateTime {
  return nthWeekdayOfMonth(year, month, 5, 3);
}

function thirdWednesdayOf(year: number, month: number): DateTime {
  return nthWeekdayOfMonth(year, month, 3, 3);
}

export function buildExpiryCalendar(fromDate: DateTime, months = 3): ExpiryEvent[] {
  const events: ExpiryEvent[] = [];
  const QUARTERLY_MONTHS = new Set([3, 6, 9, 12]);

  for (let offset = 0; offset < months; offset++) {
    const target = fromDate.plus({ months: offset });
    const year = target.year;
    const month = target.month;

    const opexFriday = thirdFridayOf(year, month);
    const isQuarterly = QUARTERLY_MONTHS.has(month);

    if (isQuarterly) {
      events.push({
        date: opexFriday.toISODate()!,
        kind: "quarterly-expiry",
        label: `Q${Math.ceil(month / 3)} CME quarterly expiry — ES/NQ/CL/GC/ZN roll+settle`
      });
      // Roll window: 8 to 5 business days before expiry
      const rollStart = opexFriday.minus({ days: 11 });
      const rollEnd = opexFriday.minus({ days: 7 });
      events.push({
        date: rollStart.toISODate()!,
        kind: "roll-window",
        label: `Roll window opens — ${rollEnd.toISODate()} to ${opexFriday.toISODate()}`
      });
    } else {
      events.push({
        date: opexFriday.toISODate()!,
        kind: "monthly-opex",
        label: `Monthly OPEX Friday — ${year}-${String(month).padStart(2, "0")}`
      });
    }

    // VIX settles the Wednesday 30 days before the next month's OPEX
    // Approximated as: 3rd Wednesday of the month (close enough for signal detection)
    const vixWed = thirdWednesdayOf(year, month);
    events.push({
      date: vixWed.toISODate()!,
      kind: "vix-wednesday",
      label: `VIX AM settlement — ${year}-${String(month).padStart(2, "0")}`
    });
  }

  return events.sort((a, b) => a.date.localeCompare(b.date));
}

export interface ExpiryProximity {
  daysToNearest: number;
  nearestKind: ExpiryWindow | null;
  nearestLabel: string | null;
  inRollWindow: boolean;
  isOpexDay: boolean;
  isVixDay: boolean;
  isQuarterlyExpiryDay: boolean;
}

export function getExpiryProximity(barDateStr: string, calendar: ExpiryEvent[]): ExpiryProximity {
  const barDate = DateTime.fromISO(barDateStr, { zone: CHICAGO_TZ });

  let daysToNearest = Infinity;
  let nearestKind: ExpiryWindow | null = null;
  let nearestLabel: string | null = null;
  let isOpexDay = false;
  let isVixDay = false;
  let isQuarterlyExpiryDay = false;
  let inRollWindow = false;

  for (const event of calendar) {
    const eventDate = DateTime.fromISO(event.date, { zone: CHICAGO_TZ });
    const diff = Math.abs(barDate.diff(eventDate, "days").days);
    const exact = barDate.toISODate() === event.date;

    if (exact) {
      if (event.kind === "monthly-opex" || event.kind === "quarterly-expiry") isOpexDay = true;
      if (event.kind === "quarterly-expiry") isQuarterlyExpiryDay = true;
      if (event.kind === "vix-wednesday") isVixDay = true;
      if (event.kind === "roll-window") inRollWindow = true;
    }

    if (diff < daysToNearest && event.kind !== "roll-window") {
      daysToNearest = diff;
      nearestKind = event.kind;
      nearestLabel = event.label;
    }
  }

  // Also flag in roll window if within 5-11 days of a quarterly expiry
  if (!inRollWindow) {
    for (const event of calendar) {
      if (event.kind !== "quarterly-expiry") continue;
      const eventDate = DateTime.fromISO(event.date, { zone: CHICAGO_TZ });
      const daysUntil = eventDate.diff(barDate, "days").days;
      if (daysUntil >= 5 && daysUntil <= 11) {
        inRollWindow = true;
        break;
      }
    }
  }

  return {
    daysToNearest: Math.round(daysToNearest),
    nearestKind,
    nearestLabel,
    inRollWindow,
    isOpexDay,
    isVixDay,
    isQuarterlyExpiryDay
  };
}
