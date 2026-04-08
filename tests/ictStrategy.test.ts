import { describe, expect, it } from "vitest";
import { getConfig } from "../src/config.js";
import type { Bar, StrategyContext } from "../src/domain.js";
import { IctDisplacementStrategy } from "../src/strategies/ictDisplacement.js";

describe("IctDisplacementStrategy", () => {
  it("emits a bullish ICT displacement signal after a sweep and fair value gap", () => {
    const baseConfig = getConfig();
    const config = {
      ...baseConfig,
      tuning: {
        ...baseConfig.tuning,
        reversionLookbackBars: 4
      }
    };
    const strategy = new IctDisplacementStrategy();
    const sessionHistory: Bar[] = [
      { ts: "2026-04-01T13:30:00.000Z", symbol: "NQ", open: 100, high: 101, low: 99.2, close: 100.4, volume: 1000 },
      { ts: "2026-04-01T13:31:00.000Z", symbol: "NQ", open: 100.4, high: 100.8, low: 99.6, close: 100, volume: 980 },
      { ts: "2026-04-01T13:32:00.000Z", symbol: "NQ", open: 100, high: 100.2, low: 99.3, close: 99.5, volume: 960 },
      { ts: "2026-04-01T13:33:00.000Z", symbol: "NQ", open: 99.5, high: 99.8, low: 99.1, close: 99.3, volume: 940 },
      { ts: "2026-04-01T13:34:00.000Z", symbol: "NQ", open: 99.3, high: 99.4, low: 99.05, close: 99.2, volume: 930 },
      { ts: "2026-04-01T13:35:00.000Z", symbol: "NQ", open: 99.2, high: 99.35, low: 98.6, close: 98.9, volume: 1100 }
    ];
    const current: Bar = {
      ts: "2026-04-01T13:36:00.000Z",
      symbol: "NQ",
      open: 99.25,
      high: 100.8,
      low: 99.45,
      close: 100.4,
      volume: 1500
    };

    const context: StrategyContext = {
      symbol: "NQ",
      bar: current,
      history: sessionHistory,
      sessionHistory,
      config,
      dailyTradeCount: 0
    };

    const signal = strategy.generateSignal(context);

    expect(signal).not.toBeNull();
    expect(signal?.strategyId).toBe("ict-displacement");
    expect(signal?.side).toBe("long");
    expect(signal?.rr).toBeGreaterThanOrEqual(config.guardrails.minRr);
    expect(signal?.meta?.pattern).toBe("liquidity-sweep-displacement-fvg");
  });
});
