import { describe, expect, it } from "vitest";
import { getConfig } from "../src/config.js";
import { generateSyntheticBars } from "../src/data/synthetic.js";
import { runBacktest } from "../src/engine/backtest.js";
import { summarizeTrades } from "../src/engine/report.js";
import { NoopNewsGate } from "../src/news/base.js";
import type { Bar, Strategy, StrategyContext, StrategySignal, TradeRecord } from "../src/domain.js";
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
    expect(summary.bySymbol.NQ.trades).toBeGreaterThan(0);
  });

  it("groups performance by market family and suggests focus from positive contributors", () => {
    const trades: TradeRecord[] = [
      {
        id: "trade_0001",
        symbol: "NQ",
        strategyId: "session-momentum",
        side: "long",
        entry: 100,
        stop: 99,
        target: 102,
        rr: 2,
        confidence: 0.9,
        contracts: 1,
        maxHoldMinutes: 10,
        entryTs: "2026-04-01T13:30:00.000Z",
        exitTs: "2026-04-01T13:40:00.000Z",
        exitPrice: 102,
        exitReason: "target",
        pnlPoints: 2,
        grossRMultiple: 2,
        netRMultiple: 1.9,
        executionCostR: 0.1,
        rMultiple: 1.9,
        status: "closed"
      },
      {
        id: "trade_0002",
        symbol: "CL",
        strategyId: "session-momentum",
        side: "short",
        entry: 80,
        stop: 81,
        target: 78,
        rr: 2,
        confidence: 0.8,
        contracts: 1,
        maxHoldMinutes: 10,
        entryTs: "2026-04-01T13:30:00.000Z",
        exitTs: "2026-04-01T13:40:00.000Z",
        exitPrice: 81,
        exitReason: "stop",
        pnlPoints: -1,
        grossRMultiple: -1,
        netRMultiple: -1.05,
        executionCostR: 0.05,
        rMultiple: -1.05,
        status: "closed"
      },
      {
        id: "trade_0003",
        symbol: "ZN",
        strategyId: "session-momentum",
        side: "long",
        entry: 100,
        stop: 99,
        target: 101,
        rr: 1,
        confidence: 0.8,
        contracts: 1,
        maxHoldMinutes: 10,
        entryTs: "2026-04-01T13:30:00.000Z",
        exitTs: "2026-04-01T13:40:00.000Z",
        exitPrice: 100.5,
        exitReason: "timeout",
        pnlPoints: 0.5,
        grossRMultiple: 0.5,
        netRMultiple: 0.45,
        executionCostR: 0.05,
        rMultiple: 0.45,
        status: "closed"
      }
    ];

    const summary = summarizeTrades(trades);

    expect(summary.byMarketFamily.index.netTotalR).toBeGreaterThan(0);
    expect(summary.byMarketFamily.energy.netTotalR).toBeLessThan(0);
    expect(summary.byMarketFamily.bond.netTotalR).toBeGreaterThan(0);
    expect(summary.byMarketFamily.fx.trades).toBe(0);
    expect(summary.suggestedFocus[0]?.marketFamily).toBe("index");
    expect(summary.suggestedFocus[0]?.weight).toBeGreaterThan(summary.suggestedFocus[2]?.weight ?? 0);
  });
});
