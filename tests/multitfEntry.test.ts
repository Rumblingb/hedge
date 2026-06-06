import { describe, expect, it } from "vitest";
import type { Bar, StrategySignal } from "../src/domain.js";
import { enhanceSignalWithMtfEntry, findPullbackEntry } from "../src/signals/multitfEntry.js";

const bar = (open: number, high: number, low: number, close: number, ts = "2026-06-08T14:30:00.000Z"): Bar => ({
  ts,
  symbol: "NQ",
  open,
  high,
  low,
  close,
  volume: 100,
});

const signal = (side: "long" | "short"): StrategySignal => ({
  symbol: "NQ",
  strategyId: "orb-breakout-15m",
  side,
  entry: side === "long" ? 100 : 100,
  stop: side === "long" ? 96 : 104,
  target: side === "long" ? 110 : 90,
  rr: 2.5,
  confidence: 0.6,
  contracts: 1,
  maxHoldMinutes: 45,
  meta: { researchOnly: true },
});

const atrBars = Array.from({ length: 16 }, (_, i) => bar(100 + i, 102 + i, 98 + i, 101 + i));

describe("multi-timeframe entry research module", () => {
  it("finds a red pullback then green confirmation for long signals", () => {
    const tickBars = [
      bar(100, 101, 99.5, 100.5),
      bar(100.5, 100.8, 99.8, 100.0),
      bar(100.0, 101.2, 99.9, 101.0),
      bar(101.0, 101.5, 100.7, 101.3),
      bar(101.3, 102.0, 101.0, 101.8),
    ];

    const pullback = findPullbackEntry(atrBars, tickBars, "long", 100);

    expect(pullback?.found).toBe(true);
    expect(pullback?.entryPrice).toBe(101.0);
    expect(pullback?.pullbackDirection).toBe("red");
  });

  it("finds a green bounce then red confirmation for short signals", () => {
    const tickBars = [
      bar(100, 100.5, 99.5, 99.8),
      bar(99.8, 100.4, 99.7, 100.2),
      bar(100.2, 100.3, 98.9, 99.4),
      bar(99.4, 99.8, 98.8, 99.0),
      bar(99.0, 99.2, 98.5, 98.7),
    ];

    const pullback = findPullbackEntry(atrBars, tickBars, "short", 100);

    expect(pullback?.found).toBe(true);
    expect(pullback?.entryPrice).toBe(99.4);
    expect(pullback?.pullbackDirection).toBe("green");
  });

  it("recalculates RR after improving entry while staying research-only metadata", () => {
    const tickBars = [
      bar(100, 101, 99.5, 100.5),
      bar(100.5, 100.8, 99.8, 100.0),
      bar(100.0, 101.2, 99.9, 101.0),
      bar(101.0, 101.5, 100.7, 101.3),
      bar(101.3, 102.0, 101.0, 101.8),
    ];

    const enhanced = enhanceSignalWithMtfEntry(signal("long"), tickBars, atrBars);

    expect(enhanced.entry).toBe(101.0);
    expect(enhanced.stop).toBe(96);
    expect(enhanced.rr).toBeCloseTo(9 / 5, 6);
    expect(enhanced.meta?.mtfEntryApplied).toBe(true);
    expect(enhanced.meta?.researchOnly).toBe(true);
  });
});
