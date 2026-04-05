import { describe, expect, it } from "vitest";
import { getConfig } from "../src/config.js";
import { generateSyntheticBars } from "../src/data/synthetic.js";
import { runWalkforwardResearch } from "../src/engine/walkforward.js";
import { NoopNewsGate } from "../src/news/base.js";

describe("runWalkforwardResearch", () => {
  it("returns ranked research profiles with a winner", async () => {
    const config = getConfig();
    const result = await runWalkforwardResearch({
      baseConfig: config,
      bars: generateSyntheticBars({ symbols: ["NQ", "ES", "CL", "GC"], days: 5, seed: 17 }),
      newsGate: new NoopNewsGate()
    });

    expect(result.profiles.length).toBeGreaterThan(1);
    expect(result.winner).not.toBeNull();
    expect(result.profiles[0]?.profileId).toBe(result.winner?.profileId);
  });
});
