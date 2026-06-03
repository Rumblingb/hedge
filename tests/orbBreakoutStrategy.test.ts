import { describe, expect, it } from "vitest";
import type { Bar, StrategyContext } from "../src/domain.js";
import { OrbBreakoutStrategy } from "../src/strategies/orbBreakout.js";
import { orbBreakoutRustProven } from "../src/strategies/orbBreakoutRustProven.js";

function bar(index: number, overrides: Partial<Bar> = {}): Bar {
  return {
    ts: `2026-06-03T14:${String(index).padStart(2, "0")}:00Z`,
    symbol: "NQ",
    open: 95,
    high: 100,
    low: 90,
    close: 95,
    volume: 1000,
    ...overrides,
  };
}

function context(args: {
  current: Bar;
  history: Bar[];
  sessionHistory: Bar[];
}): StrategyContext {
  return {
    symbol: "NQ",
    bar: args.current,
    history: args.history,
    sessionHistory: args.sessionHistory,
    dailyTradeCount: 0,
    config: {} as StrategyContext["config"],
  };
}

describe("ORB breakout strategies", () => {
  it("reports actual opening range levels separately from range ratio", () => {
    const strategy = new OrbBreakoutStrategy();
    const opening = Array.from({ length: 12 }, (_, i) => bar(i, { high: 100, low: 90, close: 95 }));
    const filler = bar(12, { high: 99, low: 94, close: 98, volume: 1200 });
    const current = bar(13, { high: 103, low: 99, close: 101, volume: 2000 });

    const signal = strategy.generateSignal(context({
      current,
      history: Array.from({ length: 12 }, (_, i) => bar(i, { volume: 1000 })),
      sessionHistory: [...opening, filler, current],
    }));

    expect(signal?.side).toBe("long");
    expect(signal?.meta?.rangeHigh).toBe(100);
    expect(signal?.meta?.rangeLow).toBe(90);
    expect(signal?.meta?.rangeRatio).toBeTypeOf("number");
    expect(signal?.meta?.researchOnly).toBe(true);
  });

  it("uses the prior opening range for the rust research wrapper", () => {
    const opening = Array.from({ length: 16 }, (_, i) => bar(i, { high: 100, low: 90, close: 95 }));
    const confirmOne = bar(16, { high: 110, low: 99, close: 101, volume: 1500 });
    const confirmTwo = bar(17, { high: 106, low: 100, close: 102, volume: 1500 });
    const current = bar(18, { high: 104, low: 101, close: 103, volume: 1500 });

    const signal = orbBreakoutRustProven.generateSignal(context({
      current,
      history: [...opening, confirmOne, confirmTwo],
      sessionHistory: [...opening, confirmOne, confirmTwo, current],
    }));

    expect(signal?.side).toBe("long");
    expect(signal?.contracts).toBe(1);
    expect(signal?.meta?.rangeHigh).toBe(100);
    expect(signal?.meta?.confirmationBars).toBe(3);
    expect(signal?.meta?.researchOnly).toBe(true);
  });
});
