import { mkdtemp } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { getConfig } from "../src/config.js";
import { generateSyntheticBars } from "../src/data/synthetic.js";
import { runMacroConditionedPolicyLab } from "../src/engine/macroConditionedPolicy.js";
import { NoopNewsGate } from "../src/news/base.js";

describe("macro-conditioned policy lab", () => {
  it("keeps pre-open policy selection paper-only and macro-audited", async () => {
    const dir = await mkdtemp(join(tmpdir(), "macro-policy-"));
    const config = getConfig();
    const report = await runMacroConditionedPolicyLab({
      bars: generateSyntheticBars({ symbols: ["NQ", "ES"], days: 3, seed: 77 }),
      baseConfig: config,
      newsGate: new NoopNewsGate(),
      outputPath: join(dir, "policy.json"),
      env: {
        RH_LIVE_EXECUTION_ENABLED: "false",
        BILL_PREDICTION_LIVE_EXECUTION_ENABLED: "false",
        BILL_ENABLE_FUTURES_DEMO_EXECUTION: "false"
      } as NodeJS.ProcessEnv,
      now: () => "2026-05-06T13:00:00.000Z",
      minTradesPerLeaf: 1,
      macroContext: {
        source: "free-macro-context",
        generatedAt: "2026-05-06T12:00:00.000Z",
        tailScore: 6.9,
        riskRegime: "normal",
        vixLevel: 17.2,
        vixTermStructure: "contango",
        yieldCurveProxyBps: 34,
        creditRiskProxy: "normal",
        equityTrendProxy: "risk-on"
      }
    });

    expect(report.command).toBe("macro-conditioned-policy");
    expect(report.mode).toBe("paper-only");
    expect(report.gates.macroJoined).toBe(true);
    expect(report.gates.liveExecutionDisabled).toBe(true);
    expect(report.policyPatch.RH_MAX_CONTRACTS).toBe(1);
    expect(report.policyPatch.RH_MAX_TRADES_PER_DAY).toBe(1);
    expect(report.preOpenRunbook.join(" ")).toMatch(/30 minutes before/i);
    expect(report.llmBoundary.join(" ")).toMatch(/observers/i);
  });
});
