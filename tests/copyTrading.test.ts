import { describe, expect, it } from "vitest";
import { buildPredictionCopyIdeas, classifyPredictionDomain, isFounderApprovedPredictionDomain } from "../src/prediction/copyTrading.js";

describe("prediction copy trading domain filters", () => {
  it("treats presidential nomination markets as politics", () => {
    expect(classifyPredictionDomain({
      title: "Who will win the 2028 Republican presidential nomination?",
      slug: "2028-republican-presidential-nomination"
    })).toBe("politics");
  });

  it("keeps presidential nomination markets inside the founder-approved filter", () => {
    expect(isFounderApprovedPredictionDomain(
      "Who will win the 2028 Republican presidential nomination?",
      "2028-republican-presidential-nomination"
    )).toBe(true);
  });

  it("adds digital-exhaust hypotheses to top-wallet copy ideas", () => {
    const ideas = buildPredictionCopyIdeas({
      minConsensusWallets: 2,
      minIdeaValueUsd: 1_000,
      leaders: [
        {
          trader: {
            rank: 1,
            wallet: "0x111",
            displayName: "leader-a",
            verifiedBadge: true,
            pnl: 200_000,
            volume: 1_000_000,
            activePositionCount: 1,
            recentActivityCount: 3,
            score: 8
          },
          positions: [{
            wallet: "0x111",
            displayName: "leader-a",
            marketId: "btc-150k",
            slug: "bitcoin-above-150k-in-2026",
            title: "Will Bitcoin be above $150k in 2026?",
            outcome: "Yes",
            size: 15_000,
            avgPrice: 0.41,
            currentPrice: 0.55,
            currentValue: 8_250,
            percentPnl: 34,
            lastActivityTs: new Date().toISOString(),
            convictionScore: 66_000
          }]
        },
        {
          trader: {
            rank: 2,
            wallet: "0x222",
            displayName: "leader-b",
            verifiedBadge: false,
            pnl: 120_000,
            volume: 800_000,
            activePositionCount: 1,
            recentActivityCount: 2,
            score: 7
          },
          positions: [{
            wallet: "0x222",
            displayName: "leader-b",
            marketId: "btc-150k",
            slug: "bitcoin-above-150k-in-2026",
            title: "Will Bitcoin be above $150k in 2026?",
            outcome: "Yes",
            size: 10_000,
            avgPrice: 0.43,
            currentPrice: 0.55,
            currentValue: 5_500,
            percentPnl: 28,
            lastActivityTs: new Date().toISOString(),
            convictionScore: 38_500
          }]
        }
      ]
    });

    expect(ideas[0].action).toBe("shadow-buy");
    expect(ideas[0].exhaust.domain).toBe("crypto");
    expect(ideas[0].exhaust.inferredStrategy).toBe("early-informed");
    expect(ideas[0].exhaust.externalSignalsToCheck.join(" ")).toMatch(/funding|open interest|Coinbase|Binance/i);
    expect(ideas[0].reason).toMatch(/exhaust classifies it/);
  });
});
