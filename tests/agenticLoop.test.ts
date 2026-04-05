import { describe, expect, it } from "vitest";
import { getConfig } from "../src/config.js";
import { generateSyntheticBars } from "../src/data/synthetic.js";
import { runAgenticImprovementLoop } from "../src/engine/agenticLoop.js";
import { NoopNewsGate } from "../src/news/base.js";
import { collectResearchUniverse } from "../src/research/profiles.js";

describe("runAgenticImprovementLoop", () => {
  it("returns baseline and tuned reports with an applied patch object", async () => {
    const config = getConfig();
    const bars = generateSyntheticBars({
      symbols: collectResearchUniverse(config),
      days: 5,
      seed: 41
    });

    const result = await runAgenticImprovementLoop({
      baseConfig: config,
      bars,
      newsGate: new NoopNewsGate()
    });

    expect(result).toHaveProperty("baseline.report.survivabilityScore");
    expect(result).toHaveProperty("tuned.report.survivabilityScore");
    expect(result).toHaveProperty("appliedPatch");
    expect(result).toHaveProperty("delta.survivabilityScore");
    expect(result.tuned.config.guardrails.maxContracts).toBeLessThanOrEqual(config.guardrails.maxContracts);
    expect(result.tuned.config.guardrails.maxTradesPerDay).toBeLessThanOrEqual(config.guardrails.maxTradesPerDay);
    expect(result.tuned.config.guardrails.maxDailyLossR).toBeLessThanOrEqual(config.guardrails.maxDailyLossR);
  }, 50000);
});
