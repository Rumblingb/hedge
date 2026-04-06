import { describe, expect, it } from "vitest";
import { getConfig } from "../src/config.js";
import { generateSyntheticBars } from "../src/data/synthetic.js";
import { runLiveDeploymentReadiness } from "../src/engine/liveReadiness.js";
import { NoopNewsGate } from "../src/news/base.js";

describe("runLiveDeploymentReadiness", () => {
  it("returns baseline, stressed, and iterative live readiness diagnostics", async () => {
    const config = getConfig();
    const bars = generateSyntheticBars({ symbols: ["NQ", "ES"], days: 3, seed: 41 });

    const result = await runLiveDeploymentReadiness({
      bars,
      baseConfig: config,
      newsGate: new NoopNewsGate(),
      iterations: 1
    });

    expect(result).toHaveProperty("baseline");
    expect(result).toHaveProperty("stressedBaseline");
    expect(result).toHaveProperty("final");
    expect(result.iterations.length).toBeGreaterThan(0);
    expect(typeof result.delta.baselineToLiveSurvivability).toBe("number");
  }, 45000);
});
