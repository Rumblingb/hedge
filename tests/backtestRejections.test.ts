import { describe, expect, it } from "vitest";
import { getConfig } from "../src/config.js";
import { runBacktest } from "../src/engine/backtest.js";
import type { Bar, Strategy } from "../src/domain.js";
import { NoopNewsGate } from "../src/news/base.js";

describe("runBacktest rejection telemetry", () => {
  it("captures rejected reasons and detailed rejection records", async () => {
    const config = getConfig();
    const bars: Bar[] = [
      { ts: "2026-04-01T13:30:00.000Z", symbol: "NQ", open: 100, high: 101, low: 99, close: 100, volume: 1000 }
    ];

    const strategy: Strategy = {
      id: "reject-rr",
      description: "always emits low RR",
      generateSignal(context) {
        return {
          symbol: context.symbol,
          strategyId: "reject-rr",
          side: "long",
          entry: context.bar.close,
          stop: context.bar.close - 1,
          target: context.bar.close + 1,
          rr: 1,
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

    expect(result.rejectedSignals).toBe(1);
    expect(result.rejectedSignalRecords).toHaveLength(1);
    expect(result.rejectedSignalRecords[0]?.reasons).toContain("rr below minimum");
    expect(result.rejectedReasonCounts["rr below minimum"]).toBe(1);
  });
});
