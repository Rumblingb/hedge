import { describe, expect, it } from "vitest";
import { buildDemoStrategySampleSnapshot } from "../src/live/demoSampling.js";

describe("buildDemoStrategySampleSnapshot", () => {
  it("rotates shadow lanes across the wider allowed symbol set when Bill is not deployable", () => {
    const snapshot = buildDemoStrategySampleSnapshot({
      ts: "2026-04-18T00:00:00.000Z",
      sampleSequence: 0,
      lanes: [
        { accountId: "acct-1", label: "lane-1", slot: 1, selected: false, strategies: ["session-momentum"], primaryStrategy: "session-momentum" },
        { accountId: "acct-2", label: "lane-2", slot: 2, selected: false, strategies: ["opening-range-reversal"], primaryStrategy: "opening-range-reversal" },
        { accountId: "acct-3", label: "lane-3", slot: 3, selected: false, strategies: ["liquidity-reversion"], primaryStrategy: "liquidity-reversion" },
        { accountId: "acct-4", label: "lane-4", slot: 4, selected: false, strategies: ["ict-displacement"], primaryStrategy: "ict-displacement" }
      ],
      candidates: [
        {
          symbol: "NQ",
          strategyId: "session-momentum",
          marketFamily: "index",
          regime: "trend-up",
          directionalBias: "long",
          expectedValueScore: 0.8,
          regimeConfidence: 0.7,
          strategyAverageR: 0.4,
          symbolAverageR: 0.3,
          strategyTrades: 6,
          resilienceScore: 0.6,
          convexityScore: 0.4,
          familyActive: true,
          rationale: []
        },
        {
          symbol: "ES",
          strategyId: "opening-range-reversal",
          marketFamily: "index",
          regime: "range-chop",
          directionalBias: "short",
          expectedValueScore: 0.6,
          regimeConfidence: 0.65,
          strategyAverageR: 0.3,
          symbolAverageR: 0.2,
          strategyTrades: 5,
          resilienceScore: 0.55,
          convexityScore: 0.35,
          familyActive: true,
          rationale: []
        }
      ],
      preferredSymbols: ["NQ"],
      allowedSymbols: ["NQ", "ES", "CL", "GC", "6E", "ZN"],
      deployableNow: false,
      whyNotTrading: ["keep iterating"]
    });

    expect(snapshot.lanes.map((lane) => lane.focusSymbol)).toEqual(["NQ", "ES", "CL", "GC"]);
  });

  it("avoids assigning lanes to symbols that are missing from the current dataset", () => {
    const snapshot = buildDemoStrategySampleSnapshot({
      ts: "2026-04-18T00:00:00.000Z",
      sampleSequence: 4,
      lanes: [
        { accountId: "acct-1", label: "lane-1", slot: 1, selected: false, strategies: ["session-momentum"], primaryStrategy: "session-momentum" },
        { accountId: "acct-2", label: "lane-2", slot: 2, selected: false, strategies: ["opening-range-reversal"], primaryStrategy: "opening-range-reversal" },
        { accountId: "acct-3", label: "lane-3", slot: 3, selected: false, strategies: ["liquidity-reversion"], primaryStrategy: "liquidity-reversion" },
        { accountId: "acct-4", label: "lane-4", slot: 4, selected: false, strategies: ["ict-displacement"], primaryStrategy: "ict-displacement" }
      ],
      candidates: [
        {
          symbol: "6E",
          strategyId: "session-momentum",
          marketFamily: "fx",
          regime: "trend-up",
          directionalBias: "long",
          expectedValueScore: 0.8,
          regimeConfidence: 0.7,
          strategyAverageR: 0.4,
          symbolAverageR: 0.3,
          strategyTrades: 6,
          resilienceScore: 0.58,
          convexityScore: 0.42,
          familyActive: true,
          rationale: []
        },
        {
          symbol: "NQ",
          strategyId: "session-momentum",
          marketFamily: "index",
          regime: "trend-up",
          directionalBias: "long",
          expectedValueScore: 0.6,
          regimeConfidence: 0.65,
          strategyAverageR: 0.3,
          symbolAverageR: 0.2,
          strategyTrades: 5,
          resilienceScore: 0.53,
          convexityScore: 0.31,
          familyActive: true,
          rationale: []
        }
      ],
      preferredSymbols: ["NQ", "6E"],
      allowedSymbols: ["NQ", "ES", "CL", "GC", "6E", "ZN"],
      availableSymbols: ["NQ", "ES", "CL", "GC", "ZN"],
      deployableNow: false,
      whyNotTrading: ["keep iterating"]
    });

    expect(snapshot.lanes.map((lane) => lane.focusSymbol)).toEqual(["NQ", "NQ", "ES", "CL"]);
    expect(snapshot.lanes.some((lane) => lane.focusSymbol === "6E")).toBe(false);
    expect(snapshot.lanes[0]?.candidate?.symbol).toBe("NQ");
  });

  it("keeps the lane focus aligned with the selected candidate during repair mode", () => {
    const snapshot = buildDemoStrategySampleSnapshot({
      ts: "2026-04-18T00:00:00.000Z",
      sampleSequence: 0,
      lanes: [
        { accountId: "acct-1", label: "lane-1", slot: 1, selected: false, strategies: ["liquidity-reversion"], primaryStrategy: "liquidity-reversion" }
      ],
      candidates: [
        {
          symbol: "NQ",
          strategyId: "liquidity-reversion",
          marketFamily: "index",
          regime: "trend-up",
          directionalBias: "long",
          expectedValueScore: 1.05,
          regimeConfidence: 0.71,
          strategyAverageR: 0.85,
          symbolAverageR: 0.8,
          strategyTrades: 6,
          resilienceScore: 0.8,
          convexityScore: 0.64,
          familyActive: true,
          rationale: []
        }
      ],
      preferredSymbols: ["ES"],
      allowedSymbols: ["ES", "NQ"],
      availableSymbols: ["ES", "NQ"],
      deployableNow: false,
      whyNotTrading: ["need more evidence"]
    });

    expect(snapshot.lanes[0]?.candidate?.symbol).toBe("NQ");
    expect(snapshot.lanes[0]?.focusSymbol).toBe("NQ");
  });

  it("concentrates duplicate shadow lanes on resilient positive candidates", () => {
    const snapshot = buildDemoStrategySampleSnapshot({
      ts: "2026-04-18T00:00:00.000Z",
      sampleSequence: 0,
      lanes: [
        { accountId: "acct-1", label: "lane-1", slot: 1, selected: false, strategies: ["liquidity-reversion"], primaryStrategy: "liquidity-reversion" },
        { accountId: "acct-2", label: "lane-2", slot: 2, selected: false, strategies: ["liquidity-reversion"], primaryStrategy: "liquidity-reversion" }
      ],
      candidates: [
        {
          symbol: "NQ",
          strategyId: "liquidity-reversion",
          marketFamily: "index",
          regime: "trend-up",
          directionalBias: "long",
          expectedValueScore: 1.1,
          regimeConfidence: 0.72,
          strategyAverageR: 0.9,
          symbolAverageR: 0.8,
          strategyTrades: 6,
          resilienceScore: 0.82,
          convexityScore: 0.68,
          familyActive: true,
          rationale: []
        },
        {
          symbol: "ES",
          strategyId: "liquidity-reversion",
          marketFamily: "index",
          regime: "trend-up",
          directionalBias: "long",
          expectedValueScore: 0.2,
          regimeConfidence: 0.68,
          strategyAverageR: 0.4,
          symbolAverageR: 0.1,
          strategyTrades: 6,
          resilienceScore: 0.41,
          convexityScore: 0.35,
          familyActive: true,
          rationale: []
        }
      ],
      preferredSymbols: ["NQ"],
      allowedSymbols: ["NQ", "ES"],
      availableSymbols: ["NQ", "ES"],
      deployableNow: false,
      whyNotTrading: ["need more evidence"]
    });

    expect(snapshot.lanes.map((lane) => lane.candidate?.symbol)).toEqual(["NQ", "NQ"]);
    expect(snapshot.lanes.every((lane) => lane.action === "shadow-observe")).toBe(true);
  });

  it("borrows weak lanes into the strongest evidence-building candidate mix", () => {
    const snapshot = buildDemoStrategySampleSnapshot({
      ts: "2026-04-18T00:00:00.000Z",
      sampleSequence: 0,
      lanes: [
        { accountId: "acct-1", label: "lane-1", slot: 1, selected: false, strategies: ["ict-displacement"], primaryStrategy: "ict-displacement" },
        { accountId: "acct-2", label: "lane-2", slot: 2, selected: false, strategies: ["liquidity-reversion"], primaryStrategy: "liquidity-reversion" },
        { accountId: "acct-3", label: "lane-3", slot: 3, selected: false, strategies: ["ict-displacement"], primaryStrategy: "ict-displacement" }
      ],
      candidates: [
        {
          symbol: "NQ",
          strategyId: "ict-displacement",
          marketFamily: "index",
          regime: "trend-up",
          directionalBias: "long",
          expectedValueScore: -0.2,
          regimeConfidence: 0.65,
          strategyAverageR: -0.1,
          symbolAverageR: 0.2,
          strategyTrades: 6,
          resilienceScore: 0.33,
          convexityScore: 0.52,
          familyActive: true,
          rationale: []
        },
        {
          symbol: "NQ",
          strategyId: "liquidity-reversion",
          marketFamily: "index",
          regime: "trend-up",
          directionalBias: "long",
          expectedValueScore: 1.12,
          regimeConfidence: 0.74,
          strategyAverageR: 0.92,
          symbolAverageR: 0.81,
          strategyTrades: 6,
          resilienceScore: 0.84,
          convexityScore: 0.69,
          familyActive: true,
          rationale: []
        },
        {
          symbol: "ES",
          strategyId: "liquidity-reversion",
          marketFamily: "index",
          regime: "trend-up",
          directionalBias: "long",
          expectedValueScore: 0.81,
          regimeConfidence: 0.68,
          strategyAverageR: 0.61,
          symbolAverageR: 0.45,
          strategyTrades: 6,
          resilienceScore: 0.72,
          convexityScore: 0.58,
          familyActive: true,
          rationale: []
        }
      ],
      preferredSymbols: ["NQ"],
      allowedSymbols: ["NQ", "ES"],
      availableSymbols: ["NQ", "ES"],
      deployableNow: false,
      whyNotTrading: ["need more evidence"],
      evidencePlan: {
        mode: "evidence-build",
        focusStrategies: ["liquidity-reversion"],
        focusSymbols: ["NQ", "ES"]
      }
    });

    expect(snapshot.lanes.map((lane) => lane.candidate?.strategyId)).toEqual([
      "liquidity-reversion",
      "liquidity-reversion",
      "liquidity-reversion"
    ]);
    expect(snapshot.lanes.map((lane) => lane.focusSymbol)).toEqual(["NQ", "ES", "ES"]);
    expect(snapshot.lanes.every((lane) => lane.action === "shadow-observe")).toBe(true);
    expect(snapshot.lanes[0]?.rationale).toContain("temporarily reassigned");
  });
});
