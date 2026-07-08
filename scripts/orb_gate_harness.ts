/**
 * orb_gate_harness.ts — Focused ORB edge promotion-gate check.
 *
 * Runs the REAL production walk-forward + agentic-fund-report pipeline for the
 * orb-breakout-proven profile only (NQ 15m), using the exact same functions the
 * `research` and `live-readiness` commands use. Reports survival score, the two
 * failing gate checks (testTradeCount, deflatedExpectancyR) at both the
 * single-candidate (profilesTested=1) and production (profilesTested=53) thresholds.
 *
 * Run: npx tsx scripts/orb_gate_harness.ts
 */
import { resolve } from "node:path";
import { loadBarsFromCsv } from "../src/data/csv.js";
import { getConfig } from "../src/config.js";
import { NoopNewsGate } from "../src/news/base.js";
import { runWalkforwardResearch } from "../src/engine/walkforward.js";
import { buildAgenticFundReport } from "../src/engine/agenticFund.js";
import { evaluateResearchPromotion } from "../src/engine/promotionGate.js";
import { RESEARCH_PROFILES, mergeProfile } from "../src/research/profiles.js";

async function main(): Promise<void> {
  const config = getConfig();
  const csvPath = resolve("data/free/NQ-15m-2y-orb.csv");
  const bars = await loadBarsFromCsv(csvPath);
  console.error(`[harness] loaded ${bars.length} NQ 15m bars`);

  const orbProfile = RESEARCH_PROFILES.find((p) => p.id === "orb-breakout-proven");
  if (!orbProfile) {
    throw new Error("orb-breakout-proven profile not found");
  }

  const newsGate = new NoopNewsGate();
  const research = await runWalkforwardResearch({
    baseConfig: config,
    bars,
    newsGate,
    profiles: [orbProfile]
  });

  const winner = research.winner;
  if (!winner) {
    console.log(JSON.stringify({ error: "no winner produced" }, null, 2));
    return;
  }

  const report = buildAgenticFundReport({ research, config });

  // Production threshold: profilesTested = full RESEARCH_PROFILES length.
  const prodProfilesTested = RESEARCH_PROFILES.length;
  const prodGate = evaluateResearchPromotion({
    winner,
    recommendedFamilyBudget: winner.familyBudget,
    phase: config.accountPhase,
    profilesTested: prodProfilesTested
  });

  // Single-candidate (honest ORB-only selection) threshold.
  const singleGate = evaluateResearchPromotion({
    winner,
    recommendedFamilyBudget: winner.familyBudget,
    phase: config.accountPhase,
    profilesTested: 1
  });

  const summary = {
    winnerProfileId: winner.profileId,
    totalTrades: winner.testSummary.totalTrades,
    netTotalR: Number(winner.testSummary.netTotalR.toFixed(4)),
    expectancyR: Number(winner.testSummary.tradeQuality.expectancyR.toFixed(4)),
    winRate: Number(winner.testSummary.winRate.toFixed(4)),
    maxDrawdownR: Number(winner.testSummary.maxDrawdownR.toFixed(4)),
    riskOfRuinProb: Number(winner.testSummary.tradeQuality.riskOfRuinProb.toFixed(4)),
    scoreStability: Number(winner.scoreStability.toFixed(4)),
    survivabilityScore: report.survivabilityScore,
    status: report.status,
    deployableNow: report.deployableNow,
    prodProfilesTested,
    prodDeflatedThreshold: Number((Math.log(Math.max(1, prodProfilesTested)) * 0.05).toFixed(4)),
    prodGate: {
      ready: prodGate.ready,
      failed: prodGate.checks.filter((c) => !c.passed).map((c) => ({ name: c.name, observed: c.observed, threshold: c.threshold }))
    },
    singleGate: {
      ready: singleGate.ready,
      failed: singleGate.checks.filter((c) => !c.passed).map((c) => ({ name: c.name, observed: c.observed, threshold: c.threshold }))
    }
  };

  console.log(JSON.stringify(summary, null, 2));
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
