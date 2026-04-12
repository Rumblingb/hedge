import { describe, expect, it } from "vitest";
import { getConfig } from "../src/config.js";
import { generateSyntheticBars } from "../src/data/synthetic.js";
import { buildJarvisBrief } from "../src/engine/jarvisBrief.js";
import { NoopNewsGate } from "../src/news/base.js";
import { collectResearchUniverse } from "../src/research/profiles.js";

describe("buildJarvisBrief", () => {
  it("returns a K/main-friendly handoff envelope", async () => {
    const config = getConfig();
    const result = await buildJarvisBrief({
      baseConfig: config,
      bars: generateSyntheticBars({
        symbols: collectResearchUniverse(config),
        days: 5,
        seed: 61
      }),
      newsGate: new NoopNewsGate(),
      operatorNote: "Rajiv wants K to stay demo-first."
    });

    expect(result.source.module).toBe("open-jarvis");
    expect(result.summary.headline.length).toBeGreaterThan(0);
    expect(result.kMainHandoff.tellRajiv.length).toBeGreaterThan(0);
    expect(Array.isArray(result.kMainHandoff.askRajiv)).toBe(true);
    expect(result.kMainHandoff.nextChecklist.length).toBeGreaterThan(0);
    expect(result.operatorNote).toContain("demo-first");
    expect(result.machineContext).toHaveProperty("failedChecks");
  }, 45000);
});
