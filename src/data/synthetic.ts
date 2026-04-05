import { DateTime } from "luxon";
import type { Bar } from "../domain.js";

function seededRandom(seed: number): () => number {
  let value = seed % 2147483647;
  if (value <= 0) {
    value += 2147483646;
  }

  return () => {
    value = (value * 16807) % 2147483647;
    return (value - 1) / 2147483646;
  };
}

const BASE_PRICE: Record<string, number> = {
  NQ: 18250,
  ES: 5200,
  CL: 78,
  GC: 2325,
  "6E": 1.09
};

export function generateSyntheticBars(args?: {
  symbols?: string[];
  days?: number;
  seed?: number;
}): Bar[] {
  const symbols = args?.symbols ?? ["NQ", "ES", "CL", "GC", "6E"];
  const days = args?.days ?? 4;
  const rand = seededRandom(args?.seed ?? 42);
  const bars: Bar[] = [];

  for (let day = 0; day < days; day += 1) {
    for (const symbol of symbols) {
      let price = BASE_PRICE[symbol] ?? 100;
      const sessionStart = DateTime.fromISO("2026-04-01T13:30:00.000Z").plus({ days: day });

      for (let minute = 0; minute < 170; minute += 1) {
        const ts = sessionStart.plus({ minutes: minute }).toUTC().toISO();
        if (!ts) {
          continue;
        }

        const regimeBias = minute < 55 ? 0.22 : minute < 110 ? -0.18 : 0.08;
        const shock = (rand() - 0.5) * (symbol === "6E" ? 0.004 : 2.2);
        const drift = regimeBias * (symbol === "6E" ? 0.0006 : 1);
        const open = price;
        const close = open + drift + shock;
        const high = Math.max(open, close) + (rand() * (symbol === "6E" ? 0.002 : 1.4));
        const low = Math.min(open, close) - (rand() * (symbol === "6E" ? 0.002 : 1.4));
        const volume = Math.round(700 + (rand() * 800) + (Math.abs(close - open) * 200));

        bars.push({
          ts,
          symbol,
          open,
          high,
          low,
          close,
          volume
        });

        price = close;
      }
    }
  }

  return bars.sort((left, right) => left.ts.localeCompare(right.ts) || left.symbol.localeCompare(right.symbol));
}
