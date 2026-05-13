import { mkdir, writeFile } from "node:fs/promises";
import { dirname, join } from "node:path";
import { describe, expect, it } from "vitest";
import { buildLiveReadinessGate } from "../src/engine/liveReadinessGate.js";

async function writeJson(path: string, value: unknown): Promise<void> {
  await mkdir(dirname(path), { recursive: true });
  await writeFile(path, `${JSON.stringify(value, null, 2)}\n`, "utf8");
}

describe("live-readiness gate", () => {
  it("fails closed when OOS and strategy evidence are missing", async ({ task }) => {
    const baseDir = join("/tmp", `bill-live-gate-${task.id}`);
    await mkdir(join(baseDir, ".rumbling-hedge/state"), { recursive: true });
    await mkdir(join(baseDir, ".rumbling-hedge/research/researcher"), { recursive: true });
    await mkdir(join(baseDir, ".rumbling-hedge/research/no-edge-ledger"), { recursive: true });
    await mkdir(join(baseDir, ".rumbling-hedge/logs"), { recursive: true });

    const now = "2026-05-08T00:00:00.000Z";
    await writeJson(join(baseDir, ".rumbling-hedge/state/prediction-cycle.latest.json"), { ts: now, scan: { counts: { "paper-trade": 0 }, diagnostics: { viablePairs: 0 } } });
    await writeJson(join(baseDir, ".rumbling-hedge/state/researcher-scheduler.latest.json"), { report: { report: { strategyHypothesesCount: 0 } } });
    await writeJson(join(baseDir, ".rumbling-hedge/state/strategy-lab.latest.json"), { mode: "light", rollingOos: { aggregate: { windowsEvaluated: 1 } } });
    await writeJson(join(baseDir, ".rumbling-hedge/state/quant-autonomy.latest.json"), {});
    await writeJson(join(baseDir, ".rumbling-hedge/state/openjarvis-board.md"), {});
    await writeJson(join(baseDir, ".rumbling-hedge/state/strategy-factory.latest.json"), {
      gates: {
        walkforwardDeployable: false,
        rollingOosWindows: 1,
        minRollingOosWindows: 4,
        rollingOosDeployableWindows: 0,
        liveReadinessDeployable: false
      }
    });
    await writeJson(join(baseDir, ".rumbling-hedge/state/futures-demo.latest.json"), { execution: { submittedCount: 0, submitted: [] } });
    await writeJson(join(baseDir, ".rumbling-hedge/research/researcher/strategy-feed.latest.json"), { directives: [], preferredStrategies: [] });
    await writeJson(join(baseDir, ".rumbling-hedge/research/no-edge-ledger/latest.json"), { count: 1, blockedStrategies: ["ict-displacement"] });
    await writeJson(join(baseDir, ".rumbling-hedge/research/forks/_latest-report.json"), { written: 1 });
    await writeJson(join(baseDir, ".rumbling-hedge/research/forks/_synthesis.latest.json"), { adoptedCount: 1 });
    await writeJson(join(baseDir, ".rumbling-hedge/research/positioning/latest.json"), { cot: { symbols: ["ES"] } });
    await writeJson(join(baseDir, ".rumbling-hedge/research/strategy-iterations/latest.json"), {});
    await writeJson(join(baseDir, ".rumbling-hedge/logs/bill-health.latest.json"), {});

    const report = await buildLiveReadinessGate({
      baseDir,
      now: () => now,
      env: {
        ...process.env,
        BILL_PREDICTION_LIVE_EXECUTION_ENABLED: "true",
        BILL_PREDICTION_MICRO_LIVE_SANDBOX_ENABLED: "true",
        BILL_PREDICTION_LIVE_MAX_STAKE: "2",
        BILL_PREDICTION_MAX_RISK_PCT: "1",
        BILL_PREDICTION_MAX_EXPOSURE_PCT: "1",
        BILL_ENABLE_FUTURES_DEMO_EXECUTION: "false",
        BILL_PREDICTION_EXECUTION_MODE: "live"
      }
    });

    expect(report.readyForLive).toBe(false);
    expect(report.blockers.join(" ")).toContain("walk-forward gate is not deployable");
    expect(report.blockers.join(" ")).toContain("rolling OOS deployable windows 0/4");
    expect(report.blockers.join(" ")).not.toContain("live prediction execution is enabled");
    expect(report.checks.find((item) => item.name === "live-routing-disabled-or-micro-sandboxed")?.passed).toBe(true);
  });
});
