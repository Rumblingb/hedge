import { mkdtemp, readFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { getConfig } from "../src/config.js";
import { generateSyntheticBars } from "../src/data/synthetic.js";
import { buildStrategyResearchContracts } from "../src/engine/strategyResearchContracts.js";
import { NoopNewsGate } from "../src/news/base.js";

describe("strategy research contracts", () => {
  it("turns strategy improvement into measurable rejectable research contracts", async () => {
    const dir = await mkdtemp(join(tmpdir(), "strategy-contracts-"));
    const outputPath = join(dir, "contracts.json");
    const report = await buildStrategyResearchContracts({
      bars: generateSyntheticBars({ symbols: ["NQ", "ES"], days: 5, seed: 88 }),
      baseConfig: getConfig(),
      newsGate: new NoopNewsGate(),
      csvPath: "synthetic.csv",
      outputPath,
      now: () => "2026-05-07T09:00:00.000Z"
    });

    expect(report.command).toBe("strategy-research-contracts");
    expect(report.contract.objective).toMatch(/OOS risk-adjusted return/i);
    expect(report.contract.rejectionCondition).toMatch(/Reject/i);
    expect(report.walkforward.profileDiagnostics.length).toBeGreaterThan(0);
    expect(report.hypotheses.map((item) => item.id)).toEqual(expect.arrayContaining([
      "volatility-filter",
      "volume-confirmation",
      "session-filter",
      "strategy-kill-list"
    ]));
    expect(report.imageFeedAudit.find((item) => item.source === "swpc.noaa.gov")).toMatchObject({
      decision: "catalog-only"
    });
    expect(JSON.parse(await readFile(outputPath, "utf8")).command).toBe("strategy-research-contracts");
  }, 45000);
});
