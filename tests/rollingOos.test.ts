import { describe, expect, it } from "vitest";
import { getConfig } from "../src/config.js";
import { generateSyntheticBars } from "../src/data/synthetic.js";
import { runRollingOosEvaluation } from "../src/engine/rollingOos.js";
import { NoopNewsGate } from "../src/news/base.js";

describe("runRollingOosEvaluation", () => {
  it("evaluates explicit rolling train/test windows without delegating to an internal re-split", async () => {
    const config = getConfig();
    const bars = generateSyntheticBars({ symbols: ["NQ", "ES"], days: 8, seed: 19 });

    const result = await runRollingOosEvaluation({
      bars,
      baseConfig: config,
      newsGate: new NoopNewsGate(),
      windows: 2,
      minTrainDays: 3,
      testDays: 1,
      embargoDays: 1
    });

    expect(result.windows.length).toBeGreaterThan(0);
    for (const window of result.windows) {
      expect(window.trainDays).toBe(3);
      expect(window.testDays).toBe(1);
    }
  }, 45000);

  it("uses substantial rolling defaults for live-style validation", async () => {
    const config = getConfig();
    const bars = generateSyntheticBars({ symbols: ["NQ", "ES"], days: 35, seed: 29 });

    const result = await runRollingOosEvaluation({
      bars,
      baseConfig: config,
      newsGate: new NoopNewsGate()
    });

    expect(result.config.minTrainDays).toBe(20);
    expect(result.config.testDays).toBe(5);
    expect(result.config.embargoDays).toBe(1);
    expect(result.windows.length).toBeGreaterThan(0);
  }, 45000);
});
