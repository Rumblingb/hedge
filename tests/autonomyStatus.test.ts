import { mkdtemp, mkdir, readFile, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { writeAutonomyStatus } from "../src/engine/autonomyStatus.js";

describe("writeAutonomyStatus", () => {
  it("keeps v1 autonomy paper-only and reports fork/OOS blockers", async () => {
    const workspace = await mkdtemp(join(tmpdir(), "autonomy-status-"));
    const stateDir = resolve(workspace, ".rumbling-hedge/state");
    const researchForksDir = resolve(workspace, ".rumbling-hedge/research/forks");
    const logDir = resolve(workspace, ".rumbling-hedge/logs");
    await Promise.all([
      mkdir(stateDir, { recursive: true }),
      mkdir(researchForksDir, { recursive: true }),
      mkdir(logDir, { recursive: true })
    ]);
    await Promise.all([
      writeFile(resolve(stateDir, "prediction-cycle.latest.json"), JSON.stringify({
        scan: { counts: { reject: 0, watch: 1, "paper-trade": 0 } }
      })),
      writeFile(resolve(stateDir, "researcher-scheduler.latest.json"), JSON.stringify({
        report: { report: { strategyHypothesesCount: 0 } }
      })),
      writeFile(resolve(stateDir, "strategy-lab.latest.json"), JSON.stringify({
        rollingOos: { aggregate: { windowsEvaluated: 1 } }
      })),
      writeFile(resolve(researchForksDir, "_latest-report.json"), JSON.stringify({ written: 2 })),
      writeFile(resolve(stateDir, "openjarvis-board.md"), "# board\n"),
      writeFile(resolve(logDir, "bill-health.latest.json"), JSON.stringify({ timestamp: "2026-04-30T00:00:00.000Z" }))
    ]);

    const status = await writeAutonomyStatus({
      baseDir: workspace,
      now: () => "2026-04-30T00:00:00.000Z",
      env: {
        BILL_MAX_HEAVY_JOBS: "1",
        BILL_PREDICTION_EXECUTION_MODE: "paper",
        BILL_PREDICTION_LIVE_EXECUTION_ENABLED: "false",
        BILL_ENABLE_FUTURES_DEMO_EXECUTION: "false"
      }
    });

    expect(status.mode).toBe("paper-only");
    expect(status.paperGates.liveTradingDisabled).toBe(true);
    expect(status.paperGates.futuresDemoExecutionDisabled).toBe(true);
    expect(status.compute.maxHeavyJobs).toBe(1);
    expect(status.trustBoundary.voiceInputMode).toBe("advisory-only");
    expect(status.trustBoundary.executionWideningRequiresApproval).toBe(true);
    expect(status.warnings).toContain("prediction cycle has zero paper-trade candidates");
    expect(status.warnings).toContain("strategy lab OOS evidence is thin");
    const persisted = JSON.parse(await readFile(resolve(workspace, ".rumbling-hedge/state/autonomy-status.latest.json"), "utf8")) as typeof status;
    expect(persisted.status).toBe(status.status);
  });
});
