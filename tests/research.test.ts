import { mkdtemp, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { getConfig } from "../src/config.js";
import { inspectBarsFromCsv, loadBarsFromCsv } from "../src/data/csv.js";
import { generateSyntheticBars } from "../src/data/synthetic.js";
import { runWalkforwardResearch } from "../src/engine/walkforward.js";
import { NoopNewsGate } from "../src/news/base.js";
import { collectResearchUniverse, mergeProfile, RESEARCH_PROFILES } from "../src/research/profiles.js";
import { getMarketCategory, getMarketSpec, normalizeFuturesSymbol } from "../src/utils/markets.js";
import { sortWalkforwardProfilesForSelection } from "../src/engine/walkforward.js";

describe("runWalkforwardResearch", () => {
  it("returns ranked research profiles with a winner", async () => {
    const config = getConfig();
    const result = await runWalkforwardResearch({
      baseConfig: config,
      bars: generateSyntheticBars({ symbols: collectResearchUniverse(config), days: 5, seed: 17 }),
      newsGate: new NoopNewsGate()
    });

    expect(result.profiles.length).toBeGreaterThan(1);
    expect(result.winner).not.toBeNull();
    expect(result.profiles[0]?.profileId).toBe(result.winner?.profileId);
    expect(result.recommendedFamilyBudget).not.toBeNull();
    expect(result).toHaveProperty("deployableWinner");
    expect(result).toHaveProperty("deployableFamilyBudget");
    expect(result).toHaveProperty("deployablePromotionGate");
    if (result.deployableWinner) {
      expect(result.deployablePromotionGate?.ready).toBe(true);
    }
    const totalWeight = Object.values(result.winner?.familyBudget.targetWeights ?? {}).reduce((sum, weight) => sum + weight, 0);
    if ((result.winner?.familyBudget.activeFamilies.length ?? 0) > 0) {
      expect(totalWeight).toBeGreaterThan(0.99);
      expect(totalWeight).toBeLessThan(1.01);
    } else {
      expect(result.winner?.familyBudget.activeFamilies).toHaveLength(0);
      expect(totalWeight).toBe(0);
    }
  }, 45000);

  it("includes the broader research universe when the base config already allows it", () => {
    const config = getConfig();
    const universe = collectResearchUniverse(config);

    expect(universe).toEqual(expect.arrayContaining(["ES", "NQ", "CL", "GC", "6E"]));
  });

  it("keeps every supported strategy represented in research profiles", () => {
    const strategies = new Set(RESEARCH_PROFILES.flatMap((profile) => profile.overrides.enabledStrategies ?? []));

    expect([...strategies]).toEqual(expect.arrayContaining([
      "session-momentum",
      "opening-range-reversal",
      "liquidity-reversion",
      "ict-displacement"
    ]));
  });

  it("keeps a narrower base universe locked even when profiles try to widen it", () => {
    const previousAllowed = process.env.RH_ALLOWED_SYMBOLS;
    process.env.RH_ALLOWED_SYMBOLS = "NQ,ES";

    try {
      const config = getConfig();
      const universe = collectResearchUniverse(config);
      const ictProfile = RESEARCH_PROFILES.find((profile) => profile.id === "ict-killzone-core");

      expect(universe).toEqual(["NQ", "ES"]);
      expect(ictProfile).toBeTruthy();

      const merged = mergeProfile(config, ictProfile!);
      expect(merged.guardrails.allowedSymbols).toEqual(["ES", "NQ"]);
    } finally {
      if (previousAllowed === undefined) {
        delete process.env.RH_ALLOWED_SYMBOLS;
      } else {
        process.env.RH_ALLOWED_SYMBOLS = previousAllowed;
      }
    }
  });

  it("prioritizes promotion-fit profiles over raw score when selecting the winner", () => {
    const ranked = sortWalkforwardProfilesForSelection({
      phase: "challenge",
      profiles: [
        {
          profileId: "high-score-loser",
          description: "High raw score but negative test edge.",
          score: 9,
          scoreStability: 0.9,
          windowCount: 3,
          splitScores: [9],
          familyBudget: {
            mode: "paused",
            activeFamilies: [],
            rankedFamilies: [],
            targetWeights: {},
            reasons: []
          },
          trainSummary: {
            totalTrades: 20,
            wins: 12,
            losses: 8,
            winRate: 0.6,
            totalR: 0,
            averageR: 0,
            maxDrawdownR: 1.5,
            grossToNetRetention: 0.9,
            bySymbol: {},
            byStrategy: {},
            byMarketFamily: {},
            grossTotalR: 0,
            netTotalR: 4,
            frictionR: 0.4,
            profitFactor: 1.4,
            tradeQuality: {
              expectancyR: 0.2,
              payoffRatio: 1.6,
              avgWinR: 1.2,
              avgLossR: -0.8,
              winRate: 0.6,
              lossRate: 0.4,
              maxConsecutiveWins: 3,
              maxConsecutiveLosses: 2,
              sharpePerTrade: 0.2,
              sortinoPerTrade: 0.3,
              ulcerIndexR: 0.5,
              cvar95TradeR: -0.8,
              riskOfRuinProb: 0.1
            }
          },
          testSummary: {
            totalTrades: 20,
            wins: 8,
            losses: 12,
            winRate: 0.4,
            totalR: 0,
            averageR: 0,
            maxDrawdownR: 5.2,
            grossToNetRetention: 0.9,
            bySymbol: {},
            byStrategy: {},
            byMarketFamily: {},
            grossTotalR: 0,
            netTotalR: -1.2,
            frictionR: 0.4,
            profitFactor: 0.9,
            tradeQuality: {
              expectancyR: -0.06,
              payoffRatio: 1.1,
              avgWinR: 1.1,
              avgLossR: -0.9,
              winRate: 0.4,
              lossRate: 0.6,
              maxConsecutiveWins: 2,
              maxConsecutiveLosses: 4,
              sharpePerTrade: -0.1,
              sortinoPerTrade: -0.1,
              ulcerIndexR: 1.1,
              cvar95TradeR: -1.3,
              riskOfRuinProb: 0.45
            }
          }
        },
        {
          profileId: "promotion-fit",
          description: "Lower raw score but positive test edge and active families.",
          score: 4,
          scoreStability: 0.7,
          windowCount: 3,
          splitScores: [4],
          familyBudget: {
            mode: "active",
            activeFamilies: ["index"],
            rankedFamilies: [
              {
                family: "index",
                score: 1.2,
                targetWeight: 1,
                active: true,
                reason: "positive test contribution"
              }
            ],
            targetWeights: {
              index: 1
            },
            reasons: []
          },
          trainSummary: {
            totalTrades: 18,
            wins: 9,
            losses: 9,
            winRate: 0.5,
            totalR: 0,
            averageR: 0,
            maxDrawdownR: 1.2,
            grossToNetRetention: 0.9,
            bySymbol: {},
            byStrategy: {},
            byMarketFamily: {},
            grossTotalR: 0,
            netTotalR: 3.1,
            frictionR: 0.3,
            profitFactor: 1.3,
            tradeQuality: {
              expectancyR: 0.17,
              payoffRatio: 1.4,
              avgWinR: 1.1,
              avgLossR: -0.8,
              winRate: 0.5,
              lossRate: 0.5,
              maxConsecutiveWins: 2,
              maxConsecutiveLosses: 2,
              sharpePerTrade: 0.15,
              sortinoPerTrade: 0.2,
              ulcerIndexR: 0.4,
              cvar95TradeR: -0.9,
              riskOfRuinProb: 0.12
            }
          },
          testSummary: {
            totalTrades: 12,
            wins: 6,
            losses: 6,
            winRate: 0.5,
            totalR: 0,
            averageR: 0,
            maxDrawdownR: 2.1,
            grossToNetRetention: 0.9,
            bySymbol: {},
            byStrategy: {},
            byMarketFamily: {},
            grossTotalR: 0,
            netTotalR: 1.4,
            frictionR: 0.2,
            profitFactor: 1.2,
            tradeQuality: {
              expectancyR: 0.12,
              payoffRatio: 1.3,
              avgWinR: 1,
              avgLossR: -0.77,
              winRate: 0.5,
              lossRate: 0.5,
              maxConsecutiveWins: 2,
              maxConsecutiveLosses: 2,
              sharpePerTrade: 0.12,
              sortinoPerTrade: 0.18,
              ulcerIndexR: 0.35,
              cvar95TradeR: -0.8,
              riskOfRuinProb: 0.18
            }
          }
        }
      ] as any
    });

    expect(ranked[0]?.profile.profileId).toBe("promotion-fit");
  });
});

describe("real data ingest", () => {
  it("normalizes contract symbols and reads headered minute-bar CSVs", async () => {
    const tempDir = await mkdtemp(join(tmpdir(), "rumbling-hedge-"));
    const csvPath = join(tempDir, "bars.csv");

    try {
      await writeFile(
        csvPath,
        [
          "timestamp,root,open,high,low,close,volume",
          "2026-04-01T13:30:00.000Z,NQM26,18250,18253,18248,18252,1320",
          "2026-04-01T13:31:00.000Z,ESM26,5200,5202,5198,5201,900"
        ].join("\n"),
        "utf8"
      );

      const bars = await loadBarsFromCsv(csvPath);

      expect(bars).toEqual([
        {
          ts: "2026-04-01T13:30:00.000Z",
          symbol: "NQ",
          open: 18250,
          high: 18253,
          low: 18248,
          close: 18252,
          volume: 1320
        },
        {
          ts: "2026-04-01T13:31:00.000Z",
          symbol: "ES",
          open: 5200,
          high: 5202,
          low: 5198,
          close: 5201,
          volume: 900
        }
      ]);
      expect(normalizeFuturesSymbol("NQM26")).toBe("NQ");
      expect(getMarketCategory("ESM26")).toBe("index");
      expect(getMarketSpec("MNQM26")).toMatchObject({
        symbol: "MNQ",
        category: "index",
        contractStyle: "micro"
      });
    } finally {
      await rm(tempDir, { recursive: true, force: true });
    }
  });

  it("inspects raw CSVs for order and value issues", async () => {
    const tempDir = await mkdtemp(join(tmpdir(), "rumbling-hedge-"));
    const csvPath = join(tempDir, "bars.csv");

    try {
      await writeFile(
        csvPath,
        [
          "timestamp,root,open,high,low,close,volume",
          "2026-04-01T13:31:00.000Z,NQM26,18252,18255,18249,18250,1184",
          "2026-04-01T13:30:00.000Z,NQM26,18250,18253,18248,18252,1320",
          "2026-04-01T13:32:00.000Z,NQM26,18252,18255,18249,not-a-number,1184"
        ].join("\n"),
        "utf8"
      );

      const inspection = await inspectBarsFromCsv(csvPath);

      expect(inspection.hasHeader).toBe(true);
      expect(inspection.dataRows).toBe(3);
      expect(inspection.symbols).toEqual(["NQ"]);
      expect(inspection.orderedByTimestamp).toBe(false);
      expect(inspection.issues.some((issue) => issue.message.includes("Rows are not ordered by timestamp."))).toBe(true);
      expect(inspection.issues.some((issue) => issue.message.includes("Invalid close value: not-a-number"))).toBe(true);
    } finally {
      await rm(tempDir, { recursive: true, force: true });
    }
  });
});
