import { mkdtemp, mkdir, readFile, writeFile } from "node:fs/promises";
import { join } from "node:path";
import { tmpdir } from "node:os";
import { describe, expect, it } from "vitest";
import { buildEdgeForensics } from "../src/engine/edgeForensics.js";

describe("edge forensics", () => {
  it("explains zero deployable edge from prediction mismatch and thin futures evidence", async () => {
    const root = await mkdtemp(join(tmpdir(), "edge-forensics-"));
    const outputPath = join(root, "state", "edge.json");
    const predictionSnapshotPath = join(root, "prediction.json");
    const predictionReviewPath = join(root, "review.json");
    const macroPolicyPath = join(root, "macro.json");
    const strategyFactoryPath = join(root, "factory.json");
    await mkdir(join(root, "state"), { recursive: true });
    await writeFile(predictionSnapshotPath, JSON.stringify([
      { venue: "polymarket", externalId: "p1", eventTitle: "Bitcoin by June", marketQuestion: "Will Bitcoin hit 150k?", outcomeLabel: "Yes", side: "yes", price: 0.1 },
      { venue: "kalshi", externalId: "k1", eventTitle: "Will CPI rise more than 0.6%?", marketQuestion: "Will CPI rise more than 0.6%?", outcomeLabel: "Above", side: "yes", price: 0.2 }
    ]), "utf8");
    await writeFile(predictionReviewPath, JSON.stringify({
      counts: { reject: 0, watch: 0, "paper-trade": 0 }
    }), "utf8");
    await writeFile(macroPolicyPath, JSON.stringify({
      selected: {
        profileId: "p",
        symbol: "NQ",
        strategyId: "liquidity-reversion",
        action: "paper-allow",
        score: 0.6,
        trades: 4,
        netTotalR: 2,
        averageR: 0.5,
        winRate: 0.75,
        profitFactor: 2,
        sharpePerTrade: 0.4,
        cvar95TradeR: -1,
        riskOfRuinProb: 0.01,
        maxConsecutiveLosses: 1,
        macroGate: { riskRegime: "normal", vixTermStructure: "contango", creditRiskProxy: "normal", equityTrendProxy: "risk-on", maxTailScore: 6 },
        rationale: []
      },
      candidates: [],
      rejectedLeaves: []
    }), "utf8");
    await writeFile(strategyFactoryPath, JSON.stringify({
      blockers: ["walkforward report is not deployable"]
    }), "utf8");

    const report = await buildEdgeForensics({
      outputPath,
      predictionSnapshotPath,
      predictionReviewPath,
      macroPolicyPath,
      strategyFactoryPath,
      now: () => "2026-05-06T12:00:00.000Z"
    });

    expect(report.status).toBe("edge-candidate-unproven");
    expect(report.predictionMarkets.rootCauses).toContain("no paper candidates survived fees, liquidity, settlement, and semantic matching");
    expect(report.futures.rootCauses.some((reason) => reason.includes("sample is too thin"))).toBe(true);
    expect(JSON.parse(await readFile(outputPath, "utf8")).command).toBe("edge-forensics");
  });
});
