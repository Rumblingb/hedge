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
      newsGate: new NoopNewsGate(),
      noEdgeLedger: null
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
      noEdgeLedger: null,
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

  it("keeps no-edge strategies out of demo/paper focus and exposes unblocked fallback research", async () => {
    const config = getConfig();
    const result = await buildDailyStrategyPlan({
      baseConfig: {
        ...config,
        enabledStrategies: ["ict-displacement", "session-momentum"]
      },
      bars: generateSyntheticBars({
        symbols: collectResearchUniverse(config),
        days: 5,
        seed: 63
      }),
      newsGate: new NoopNewsGate(),
      noEdgeLedger: {
        generatedAt: "2026-05-06T00:00:00.000Z",
        runId: "test-no-edge",
        count: 1,
        noEdgeCount: 2,
        blockedCount: 0,
        needsMoreDataCount: 0,
        promotableCount: 0,
        blockedStrategies: ["ict-displacement", "session-momentum"],
        nonPromotableStrategies: ["ict-displacement", "session-momentum"],
        learningSummary: ["ict-displacement failed OOS and is quarantined."],
        entries: []
      },
      traderIntuition: {
        paths: [],
        loadedPaths: [],
        preferredStrategies: ["capitulation-score", "structural-flows"],
        preferredSymbols: ["NQ"],
        riskNotes: ["research only; promotion guardrails still apply"],
        summaryLines: ["test intuition"]
      },
      researchStrategyFeed: {
        artifactPath: ".rumbling-hedge/research/researcher/strategy-hypotheses.latest.json",
        generatedAt: "2026-04-27T00:00:00.000Z",
        runId: "run-ict",
        strategyCount: 1,
        topStrategyTitles: ["ICT displacement"],
        preferredStrategies: ["ict-displacement"],
        preferredSymbols: ["NQ"],
        preferredSessions: ["new york"],
        directives: []
      }
    });

    expect(result.selection.noEdgeGuard.active).toBe(true);
    expect(result.selection.noEdgeGuard.quarantinedStrategies).toContain("ict-displacement");
    expect(result.selection.noEdgeGuard.fallbackStrategies).toContain("capitulation-score");
    expect(result.selection.enabledStrategies).not.toContain("ict-displacement");
    expect(result.selection.enabledStrategies).not.toContain("session-momentum");
    expect(result.selection.configuredStrategyCandidates.every((candidate) => candidate.strategyId !== "ict-displacement")).toBe(true);
    expect(result.selection.decisionFlow.join(" ")).toContain("No-edge ledger quarantines ict-displacement");
  }, 45000);
});
