import { mkdtemp, mkdir, writeFile } from "node:fs/promises";
import { join } from "node:path";
import { tmpdir } from "node:os";
import { describe, expect, it } from "vitest";
import { buildCompetitiveReadinessReport } from "../src/engine/competitiveReadiness.js";

describe("competitive readiness", () => {
  it("keeps live blocked and reports lane-level data needs", async () => {
    const baseDir = await mkdtemp(join(tmpdir(), "bill-competitive-"));
    await mkdir(join(baseDir, ".rumbling-hedge/state"), { recursive: true });
    await mkdir(join(baseDir, ".rumbling-hedge/runtime/prediction"), { recursive: true });
    await writeFile(join(baseDir, ".rumbling-hedge/state/prediction-cycle.latest.json"), JSON.stringify({
      ts: "2026-05-06T15:26:11.560Z",
      venuesHealthy: 2,
      scan: { counts: { reject: 0, watch: 0, "paper-trade": 0 } },
      training: { selectedPolicy: { paperEdgeThresholdPct: 0.25 } }
    }), "utf8");
    await writeFile(join(baseDir, ".rumbling-hedge/runtime/prediction/opportunities.jsonl"), "\n", "utf8");

    const report = await buildCompetitiveReadinessReport({
      baseDir,
      now: () => "2026-05-06T15:30:00.000Z",
      env: {
        BILL_ACTIVE_TRACKS: "prediction,futures-core",
        BILL_EXECUTION_TRACKS: "prediction,futures-core",
        BILL_PREDICTION_EXECUTION_MODE: "paper",
        BILL_PREDICTION_LIVE_EXECUTION_ENABLED: "false",
        RH_LIVE_EXECUTION_ENABLED: "false"
      } as NodeJS.ProcessEnv
    });

    expect(report.liveExecutionAllowed).toBe(false);
    expect(report.globalBlockers).toContain("no lane has enough edge evidence for live capital");
    expect(report.lanes.find((lane) => lane.lane === "prediction")?.blockers).toContain("missing-paper-candidates");
    expect(report.dataShoppingList).toContain("tick/L2 or at least bid-ask bars");
    expect(report.scalingLawAnswer.verdict).toMatch(/conditional scaling laws/i);
  });
});
