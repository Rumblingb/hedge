import { describe, expect, it } from "vitest";
import { getConfig } from "../src/config.js";
import { generateSyntheticBars } from "../src/data/synthetic.js";
import { runBacktest } from "../src/engine/backtest.js";
import { NoopNewsGate } from "../src/news/base.js";
import { buildDefaultEnsemble } from "../src/strategies/wctcEnsemble.js";

describe("runBacktest", () => {
  it("produces a stable result shape on synthetic bars", async () => {
    const config = getConfig();
    const result = await runBacktest({
      bars: generateSyntheticBars({ symbols: ["NQ", "ES"], days: 2, seed: 7 }),
      strategy: buildDefaultEnsemble(config),
      config,
      newsGate: new NoopNewsGate()
    });

    expect(Array.isArray(result.trades)).toBe(true);
    expect(result.rejectedSignals).toBeGreaterThanOrEqual(0);
  });
});
