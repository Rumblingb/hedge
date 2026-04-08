import { describe, expect, it } from "vitest";
import { getConfig } from "../src/config.js";
import type { Bar, Strategy, StrategyContext, StrategySignal } from "../src/domain.js";
import { runRiskTradeModel } from "../src/engine/riskModel.js";
import { NoopNewsGate } from "../src/news/base.js";

describe("runRiskTradeModel", () => {
  it("compares current, frictionless, and stressed execution and ranks RR buckets", async () => {
    const config = getConfig();
    const bars: Bar[] = [
      { ts: "2026-04-01T13:30:00.000Z", symbol: "NQ", open: 100, high: 100.2, low: 99.8, close: 100, volume: 1000 },
      { ts: "2026-04-01T13:31:00.000Z", symbol: "NQ", open: 100, high: 101.5, low: 99.9, close: 101.4, volume: 1000 },
      { ts: "2026-04-01T13:32:00.000Z", symbol: "NQ", open: 101.4, high: 103.3, low: 101.0, close: 103, volume: 1000 }
    ];

    const strategy: Strategy = {
      id: "risk-model-test",
      description: "single-entry test strategy",
      generateSignal(context: StrategyContext): StrategySignal | null {
        if (context.history.length > 0) {
          return null;
        }

        return {
          symbol: context.symbol,
          strategyId: "risk-model-test",
          side: "long",
          entry: 100,
          stop: 99,
          target: 103,
          rr: 3,
          confidence: 0.9,
          contracts: 1,
          maxHoldMinutes: 20
        };
      }
    };

    const result = await runRiskTradeModel({
      bars,
      baseConfig: config,
      strategy,
      newsGate: new NoopNewsGate()
    });

    expect(result.current.trades).toBeGreaterThan(0);
    expect(result.frictionless.netTotalR).toBeGreaterThanOrEqual(result.current.netTotalR);
    expect(result.stressed.netTotalR).toBeLessThanOrEqual(result.current.netTotalR);
    expect(result.rrBuckets.some((bucket) => bucket.bucket === "3.0-4.0R")).toBe(true);
    expect(result.recommendation.modelView).toMatch(/slightly risky but good risk-to-reward trades/i);
    expect(result.strategyInsights).toHaveLength(1);
    expect(result.strategyInsights[0]?.recommendation.preferredBucket).toBe("3.0-4.0R");
    expect(result.symbolInsights).toHaveLength(1);
    expect(result.symbolInsights[0]?.recommendation.preferredBucket).toBe("3.0-4.0R");
  });
});
