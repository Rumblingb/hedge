import { describe, expect, it } from "vitest";
import { getConfig } from "../src/config.js";
import { generateSyntheticBars } from "../src/data/synthetic.js";
import { buildDailyStrategyPlan } from "../src/engine/dailyPlan.js";
import { NoopNewsGate } from "../src/news/base.js";
import { collectResearchUniverse } from "../src/research/profiles.js";

describe("buildDailyStrategyPlan", () => {
  it("returns an operator-facing strategy selection explanation", async () => {
    const config = getConfig();
    const result = await buildDailyStrategyPlan({
      baseConfig: config,
      bars: generateSyntheticBars({
        symbols: collectResearchUniverse(config),
        days: 5,
        seed: 59
      }),
      newsGate: new NoopNewsGate()
    });

    expect(result.selection.mode === "demo-paper-ready" || result.selection.mode === "research-only").toBe(true);
    expect(result.selection.decisionFlow.length).toBeGreaterThan(0);
    expect(result.selection.intradayExecutionRule.length).toBeGreaterThan(0);
    expect(result.selection.strategyRoles.length).toBeGreaterThan(0);
    expect(result.selection.regimeAssessments.length).toBeGreaterThan(0);
    expect(result.selection.selectedExecutionPlan.action === "paper-trade" || result.selection.selectedExecutionPlan.action === "stand-down").toBe(true);
    expect(["paper-trade", "shadow-observe", "stand-down"]).toContain(result.selection.councilDecision.portfolioManager.action);
    expect(result.selection.councilDecision.riskReview.vetoReasons.length).toBeGreaterThanOrEqual(0);
    expect(Array.isArray(result.selection.rankedCandidates)).toBe(true);
    expect(["promotion-ready", "evidence-build", "repair"]).toContain(result.selection.evidencePlan.mode);
    expect(result.selection.evidencePlan.rationale.length).toBeGreaterThan(0);
    expect(result.report).toHaveProperty("status");
  }, 45000);

  it("biases plan focus toward transcript-derived ICT hints when available", async () => {
    const config = getConfig();
    const result = await buildDailyStrategyPlan({
      baseConfig: config,
      bars: generateSyntheticBars({
        symbols: collectResearchUniverse(config),
        days: 5,
        seed: 61
      }),
      newsGate: new NoopNewsGate(),
      researchStrategyFeed: {
        artifactPath: ".rumbling-hedge/research/researcher/strategy-hypotheses.latest.json",
        generatedAt: "2026-04-27T00:00:00.000Z",
        runId: "run-ict",
        strategyCount: 2,
        topStrategyTitles: ["London session displacement continuation", "Opening range raid and reclaim"],
        preferredStrategies: ["ict-displacement", "opening-range-reversal"],
        preferredSymbols: ["NQ", "ES"],
        preferredSessions: ["london", "new york"],
        directives: []
      }
    });

    expect(result.selection.researchStrategyFeed?.preferredStrategies[0]).toBe("ict-displacement");
    expect(result.selection.preferredSymbols[0]).toBe("NQ");
    expect(result.selection.evidencePlan.rationale).toContain("Transcript research bias favors");
  }, 45000);
});
