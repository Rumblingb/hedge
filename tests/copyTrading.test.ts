import { mkdir, writeFile } from "node:fs/promises";
import { join } from "node:path";
import { tmpdir } from "node:os";
import { describe, expect, it } from "vitest";
import { buildPredictionCopyIdeas, classifyPredictionDomain, fetchPolymarketLeaderboard, isFounderApprovedPredictionDomain } from "../src/prediction/copyTrading.js";

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

  it("requires five fresh leader wallets and safe entry premium before shadow-buy", () => {
    const now = new Date().toISOString();
    const leaders = Array.from({ length: 5 }, (_, index) => ({
      trader: {
        wallet: `wallet-${index}`,
        displayName: `leader-${index}`,
        pnl: 100_000,
        rank: index + 1,
        verifiedBadge: false,
        volume: 1_000_000,
        activePositionCount: 1,
        recentActivityCount: 4,
        score: 6
      },
      positions: [
        {
          wallet: `wallet-${index}`,
          displayName: `leader-${index}`,
          marketId: "m1",
          slug: "fed-rate-cut-2026",
          title: "Fed rate cut in 2026?",
          outcome: "Yes",
          size: 1000,
          avgPrice: 0.42,
          currentPrice: 0.44,
          currentValue: 1000,
          percentPnl: 4,
          lastActivityTs: now,
          convictionScore: 6000
        }
      ]
    }));

    const ideas = buildPredictionCopyIdeas({
      leaders,
      minConsensusWallets: 2,
      minIdeaValueUsd: 2500,
      minShadowConsensusWallets: 5,
      maxCopyEntryPremium: 0.03,
      maxLeaderActivityAgeHours: 72
    });

    expect(ideas[0]?.action).toBe("shadow-buy");
    expect(ideas[0]?.copySafety.pass).toBe(true);
  });

  it("downgrades consensus to watch when the copy entry is worse than leader entry", () => {
    const now = new Date().toISOString();
    const leaders = Array.from({ length: 5 }, (_, index) => ({
      trader: {
        wallet: `wallet-${index}`,
        displayName: `leader-${index}`,
        pnl: 100_000,
        rank: index + 1,
        verifiedBadge: false,
        volume: 1_000_000,
        activePositionCount: 1,
        recentActivityCount: 4,
        score: 6
      },
      positions: [
        {
          wallet: `wallet-${index}`,
          displayName: `leader-${index}`,
          marketId: "m1",
          slug: "fed-rate-cut-2026",
          title: "Fed rate cut in 2026?",
          outcome: "Yes",
          size: 1000,
          avgPrice: 0.42,
          currentPrice: 0.55,
          currentValue: 1000,
          percentPnl: 4,
          lastActivityTs: now,
          convictionScore: 6000
        }
      ]
    }));

    const ideas = buildPredictionCopyIdeas({
      leaders,
      minConsensusWallets: 2,
      minIdeaValueUsd: 2500,
      minShadowConsensusWallets: 5,
      maxCopyEntryPremium: 0.03,
      maxLeaderActivityAgeHours: 72
    });

    expect(ideas[0]?.action).toBe("watch");
    expect(ideas[0]?.copySafety.failures.some((failure) => failure.includes("copy premium"))).toBe(true);
  });

  it("adds digital-exhaust hypotheses to top-wallet copy ideas", () => {
    const now = new Date().toISOString();
    const leaders = Array.from({ length: 5 }, (_, index) => ({
      trader: {
        wallet: `wallet-${index}`,
        displayName: `leader-${index}`,
        pnl: 100_000,
        rank: index + 1,
        verifiedBadge: false,
        volume: 1_000_000,
        activePositionCount: 1,
        recentActivityCount: 4,
        score: 6
      },
      positions: [
        {
          wallet: `wallet-${index}`,
          displayName: `leader-${index}`,
          marketId: "btc-150k",
          slug: "bitcoin-above-150k-in-2026",
          title: "Will Bitcoin be above $150k in 2026?",
          outcome: "Yes",
          size: 10_000,
          avgPrice: 0.41,
          currentPrice: 0.43,
          currentValue: 3_000,
          percentPnl: 12,
          lastActivityTs: now,
          convictionScore: 18_000
        }
      ]
    }));

    const ideas = buildPredictionCopyIdeas({
      leaders,
      minConsensusWallets: 2,
      minIdeaValueUsd: 2_500,
      minShadowConsensusWallets: 5,
      maxCopyEntryPremium: 0.03,
      maxLeaderActivityAgeHours: 72
    });

    expect(ideas[0]?.action).toBe("shadow-buy");
    expect(ideas[0]?.exhaust.domain).toBe("crypto");
    expect(ideas[0]?.exhaust.inferredStrategy).toBe("crowded-consensus");
    expect(ideas[0]?.exhaust.externalSignalsToCheck.join(" ")).toMatch(/funding|open interest|Coinbase|Binance/i);
    expect(ideas[0]?.reason).toMatch(/exhaust classifies it/);
  });

  it("loads known local wallet addresses before falling back to leaderboard scraping", async () => {
    const dir = join(tmpdir(), `wallet-source-${Date.now()}`);
    await mkdir(dir, { recursive: true });
    const path = join(dir, "wallets.json");
    await writeFile(path, JSON.stringify({
      wallets: [
        { name: "Trader A", address: "0x1111111111111111111111111111111111111111", pnl: 1000 },
        { name: "NoAddress", type: "username" },
        { name: "0x2222222222222222222222222222222222222222", type: "address" }
      ]
    }));

    const entries = await fetchPolymarketLeaderboard({ leaderSourcePath: path, leaderboardLimit: 10 });

    expect(entries).toHaveLength(2);
    expect(entries[0]?.proxyWallet).toBe("0x1111111111111111111111111111111111111111");
    expect(entries[1]?.proxyWallet).toBe("0x2222222222222222222222222222222222222222");
  });
});
