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
    expect(Array.isArray(result.selection.rankedCandidates)).toBe(true);
    expect(result.report).toHaveProperty("status");
  }, 45000);
});
