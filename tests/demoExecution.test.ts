import { describe, expect, it, vi } from "vitest";
import { executeFuturesDemoLanes } from "../src/live/demoExecution.js";
import { NoopNewsGate } from "../src/news/base.js";
import { getConfig } from "../src/config.js";
import type { Bar } from "../src/domain.js";
import type { DemoStrategySampleSnapshot } from "../src/live/demoSampling.js";

function buildIntradayBars(): Bar[] {
  return [
    { ts: "2026-04-17T13:35:00.000Z", symbol: "NQ", open: 18000, high: 18001, low: 17999.5, close: 18000.5, volume: 100 },
    { ts: "2026-04-17T13:40:00.000Z", symbol: "NQ", open: 18000.5, high: 18001.5, low: 18000, close: 18001, volume: 100 },
    { ts: "2026-04-17T13:45:00.000Z", symbol: "NQ", open: 18001, high: 18002, low: 18000.5, close: 18001.5, volume: 100 },
    { ts: "2026-04-17T13:50:00.000Z", symbol: "NQ", open: 18001.5, high: 18002.5, low: 18001, close: 18002, volume: 100 },
    { ts: "2026-04-17T13:55:00.000Z", symbol: "NQ", open: 18002, high: 18003, low: 18001.5, close: 18002.5, volume: 100 },
    { ts: "2026-04-17T14:00:00.000Z", symbol: "NQ", open: 18002.5, high: 18003.5, low: 18002, close: 18003, volume: 100 },
    { ts: "2026-04-17T14:05:00.000Z", symbol: "NQ", open: 18003, high: 18004.5, low: 18002.8, close: 18004.2, volume: 150 }
  ];
}

describe("executeFuturesDemoLanes", () => {
  it("submits a demo order when a lane has a valid signal and execution is enabled", async () => {
    const config = getConfig();
    config.mode = "live";
    config.live.enabled = true;
    config.live.demoOnly = true;
    config.live.readOnly = false;
    config.live.accountId = "465";
    config.live.allowedAccountIds = ["465"];
    config.live.baseUrl = "https://api.example.com";
    config.live.username = "demo-user";
    config.live.apiKey = "secret";
    config.guardrails.allowedSymbols = ["NQ"];

    const sampleSnapshot: DemoStrategySampleSnapshot = {
      ts: "2026-04-17T14:05:00.000Z",
      sampleSequence: 0,
      laneCount: 1,
      sampledStrategies: ["session-momentum"],
      lanes: [
        {
          accountId: "465",
          label: "Momentum",
          slot: 1,
          primaryStrategy: "session-momentum",
          strategies: ["session-momentum"],
          focusSymbol: "NQ",
          action: "shadow-observe",
          rationale: "Momentum lane",
          candidate: null,
          alternatives: []
        }
      ]
    };

    const submit = vi.fn().mockResolvedValue({
      accepted: true,
      orderId: "ord-1",
      message: "demo submitted"
    });

    const report = await executeFuturesDemoLanes({
      bars: buildIntradayBars(),
      config,
      newsGate: new NoopNewsGate(),
      trades: [],
      sampleSnapshot,
      killSwitchActive: false,
      enabled: true,
      maxOrdersPerRun: 1,
      preflightBlockers: [],
      adapterFactory: () => ({
        submit,
        flattenAll: vi.fn()
      })
    });

    expect(report.submittedCount).toBe(1);
    expect(report.lanes[0]?.status).toBe("submitted");
    expect(report.lanes[0]?.signal?.symbol).toBe("NQ");
    expect(submit).toHaveBeenCalledTimes(1);
  });
});
