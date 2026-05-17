import { mkdir, writeFile } from "node:fs/promises";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { buildPropFirmEdgeMatrix } from "../src/engine/propFirmEdgeMatrix.js";

async function writeJson(path: string, value: unknown): Promise<void> {
  await mkdir(join(path, ".."), { recursive: true });
  await writeFile(path, `${JSON.stringify(value, null, 2)}\n`, "utf8");
}

const candidate = {
  candidateId: "NQ:ret_15:5",
  symbol: "NQ",
  feature: "ret_15",
  horizonBars: 5,
  direction: "short",
  trainIc: -0.08,
  testIc: -0.12,
  stability: 0.94,
  observations: 1400,
  trainObservations: 900,
  testObservations: 500,
  featureCenter: 0,
  purgedWalkforward: [],
  cvMeanTestIc: -0.11,
  cvPositiveFoldRate: 1,
  cvMinNetEdgePct: 0.03,
  regimeValidation: [
    { regime: "low-vol", observations: 200, testIc: -0.07, netEdgePct: 0.02, verdict: "pass" },
    { regime: "mid-vol", observations: 700, testIc: -0.12, netEdgePct: 0.04, verdict: "pass" },
    { regime: "high-vol", observations: 500, testIc: -0.10, netEdgePct: 0.05, verdict: "pass" }
  ],
  meanForwardReturnPct: 0.06,
  costStressPct: 0.015,
  netEdgePct: 0.045,
  verdict: "shadow",
  blockers: [],
  paperStrategy: null
};

describe("prop-firm edge matrix", () => {
  it("promotes only candidates with stable folds and regime coverage to demo-payout candidate", async ({ task }) => {
    const baseDir = join("/tmp", `bill-prop-matrix-${task.id}`);
    const alphaPath = join(baseDir, "alpha.json");
    await writeJson(alphaPath, {
      command: "alpha-lab",
      bars: 2000,
      symbols: ["NQ"],
      blockers: [],
      topCandidates: [candidate]
    });

    const report = await buildPropFirmEdgeMatrix({
      outputPath: join(baseDir, "matrix.json"),
      optionsContextPath: join(baseDir, "missing-options.json"),
      inputs: [{ label: "15m", timeframe: "15m", path: alphaPath }],
      now: () => "2026-05-17T00:00:00.000Z"
    });

    expect(report.lanes[0].status).toBe("demo-payout-candidate");
    expect(report.lanes[0].symbol).toBe("NQ");
    expect(report.blockers).toContain("options-context-missing");
    expect(report.operatingRules.join(" ")).toContain("No lane can execute live");
  });
});
