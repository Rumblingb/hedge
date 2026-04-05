import { describe, expect, it } from "vitest";
import { getConfig } from "../src/config.js";
import { generateSyntheticBars } from "../src/data/synthetic.js";
import { runBacktest } from "../src/engine/backtest.js";
import { summarizeTrades } from "../src/engine/report.js";
import { NoopNewsGate } from "../src/news/base.js";
import type { Bar, Strategy, StrategyContext, StrategySignal } from "../src/domain.js";
import { buildDefaultEnsemble } from "../src/strategies/wctcEnsemble.js";

describe("runBacktest", () => {
  it("produces a stable result shape on synthetic bars", async () => {
    const config = getConfig();
    const result = await runBacktest({
      bars: generateSyntheticBars({ symbols: ["NQ", "ES"], days: 2, seed: 7 }),
      strategy: buildDefaultEnsemble(config),
      config,
      newsGate: new NoopNewsGate()
    });

    expect(Array.isArray(result.trades)).toBe(true);
    expect(result.rejectedSignals).toBeGreaterThanOrEqual(0);
  });

  it("reflects execution friction in gross vs net reporting", async () => {
    const config = getConfig();
    const bars: Bar[] = [
      { ts: "2026-04-01T13:30:00.000Z", symbol: "NQ", open: 100, high: 101, low: 99, close: 100.5, volume: 1000 },
      { ts: "2026-04-01T13:31:00.000Z", symbol: "NQ", open: 100.5, high: 104, low: 100.4, close: 103.8, volume: 1200 }
    ];

    const strategy: Strategy = {
      id: "one-shot",
      description: "One-shot test strategy",
      generateSignal(context: StrategyContext): StrategySignal | null {
        if (context.history.length > 0) {
          return null;
        }

        return {
          symbol: context.symbol,
          strategyId: "one-shot",
          side: "long",
          entry: context.bar.close,
          stop: context.bar.close - 1,
          target: context.bar.close + 2.5,
          rr: 2.5,
          confidence: 0.9,
          contracts: 1,
          maxHoldMinutes: 10
        };
      }
    };

    const result = await runBacktest({
      bars,
      strategy,
      config,
      newsGate: new NoopNewsGate()
    });

    const summary = summarizeTrades(result.trades);
    expect(summary.grossTotalR).toBeGreaterThan(summary.netTotalR);
    expect(summary.frictionR).toBeGreaterThan(0);
    expect(result.trades[0]?.grossRMultiple).toBeGreaterThan(result.trades[0]?.netRMultiple ?? 0);
  });
});
