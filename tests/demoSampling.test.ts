import { describe, expect, it } from "vitest";
import type { StrategyCandidate } from "../src/engine/expectedValueSurface.js";
import { buildDemoStrategySampleSnapshot } from "../src/live/demoSampling.js";

describe("demo strategy sampling", () => {
  it("covers each configured lane and rotates candidates by sequence", () => {
    const lanes = [
      {
        accountId: "acct-1",
        label: "lane-1",
        slot: 1,
        selected: false,
        strategies: ["opening-range-reversal"],
        primaryStrategy: "opening-range-reversal"
      },
      {
        accountId: "acct-2",
        label: "lane-2",
        slot: 2,
        selected: false,
        strategies: ["opening-range-reversal"],
        primaryStrategy: "opening-range-reversal"
      },
      {
        accountId: "acct-3",
        label: "lane-3",
        slot: 3,
        selected: false,
        strategies: ["ict-displacement"],
        primaryStrategy: "ict-displacement"
      }
    ];

    const candidates: StrategyCandidate[] = [
      {
        symbol: "NQ",
        strategyId: "opening-range-reversal",
        marketFamily: "index",
        regime: "trend-up",
        directionalBias: "long",
        expectedValueScore: 0.8,
        regimeConfidence: 0.7,
        strategyAverageR: 0.2,
        symbolAverageR: 0.15,
        familyActive: true,
        rationale: []
      },
      {
        symbol: "ES",
        strategyId: "opening-range-reversal",
        marketFamily: "index",
        regime: "trend-up",
        directionalBias: "long",
        expectedValueScore: 0.7,
        regimeConfidence: 0.65,
        strategyAverageR: 0.2,
        symbolAverageR: 0.1,
        familyActive: true,
        rationale: []
      },
      {
        symbol: "NQ",
        strategyId: "ict-displacement",
        marketFamily: "index",
        regime: "trend-down",
        directionalBias: "short",
        expectedValueScore: 0.9,
        regimeConfidence: 0.75,
        strategyAverageR: 0.25,
        symbolAverageR: 0.15,
        familyActive: true,
        rationale: []
      }
    ];

    const first = buildDemoStrategySampleSnapshot({
      ts: "2026-04-15T00:00:00.000Z",
      sampleSequence: 0,
      lanes,
      candidates,
      preferredSymbols: ["NQ", "ES"],
      allowedSymbols: ["NQ", "ES"],
      deployableNow: false,
      whyNotTrading: ["promotion gate still failing"]
    });
    const second = buildDemoStrategySampleSnapshot({
      ts: "2026-04-15T01:00:00.000Z",
      sampleSequence: 1,
      lanes,
      candidates,
      preferredSymbols: ["NQ", "ES"],
      allowedSymbols: ["NQ", "ES"],
      deployableNow: false,
      whyNotTrading: ["promotion gate still failing"]
    });

    expect(first.laneCount).toBe(3);
    expect(first.sampledStrategies).toEqual(["opening-range-reversal", "ict-displacement"]);
    expect(first.lanes[0]?.candidate?.symbol).toBe("NQ");
    expect(first.lanes[1]?.candidate?.symbol).toBe("ES");
    expect(second.lanes[0]?.candidate?.symbol).toBe("ES");
    expect(first.lanes[2]?.action).toBe("shadow-observe");
  });
});
