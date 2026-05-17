import { mkdir, writeFile } from "node:fs/promises";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { buildGoalReport } from "../src/engine/goal.js";

async function writeJson(path: string, value: unknown): Promise<void> {
  await mkdir(join(path, ".."), { recursive: true });
  await writeFile(path, `${JSON.stringify(value, null, 2)}\n`, "utf8");
}

describe("goal report", () => {
  it("fails closed for demo/live when OOS and non-fallback demo evidence are absent", async ({ task }) => {
    const baseDir = join("/tmp", `bill-goal-${task.id}`);
    const now = "2026-05-17T00:00:00.000Z";

    await mkdir(join(baseDir, ".rumbling-hedge/state"), { recursive: true });
    await mkdir(join(baseDir, ".rumbling-hedge/research/researcher"), { recursive: true });
    await mkdir(join(baseDir, ".rumbling-hedge/research/no-edge-ledger"), { recursive: true });
    await mkdir(join(baseDir, ".rumbling-hedge/research/forks"), { recursive: true });
    await mkdir(join(baseDir, ".rumbling-hedge/research/positioning"), { recursive: true });
    await mkdir(join(baseDir, ".rumbling-hedge/research/strategy-iterations"), { recursive: true });
    await mkdir(join(baseDir, ".rumbling-hedge/logs"), { recursive: true });

    await writeJson(join(baseDir, ".rumbling-hedge/state/prediction-cycle.latest.json"), { ts: now, venuesHealthy: 2, scan: { counts: { watch: 0, "paper-trade": 0 }, diagnostics: { viablePairs: 0 } } });
    await writeJson(join(baseDir, ".rumbling-hedge/state/researcher-scheduler.latest.json"), { report: { report: { strategyHypothesesCount: 1 } } });
    await writeJson(join(baseDir, ".rumbling-hedge/state/strategy-lab.latest.json"), { generatedAt: now, mode: "light", rollingOos: { aggregate: { windowsEvaluated: 1 } } });
    await writeJson(join(baseDir, ".rumbling-hedge/state/quant-autonomy.latest.json"), {});
    await writeFile(join(baseDir, ".rumbling-hedge/state/openjarvis-board.md"), "# board\n", "utf8");
    await writeJson(join(baseDir, ".rumbling-hedge/state/strategy-factory.latest.json"), {
      generatedAt: now,
      gates: {
        walkforwardDeployable: false,
        rollingOosWindows: 1,
        minRollingOosWindows: 4,
        rollingOosDeployableWindows: 0,
        liveReadinessDeployable: false
      },
      rollingOos: { aggregate: { windowsEvaluated: 1 } }
    });
    await writeJson(join(baseDir, ".rumbling-hedge/state/futures-demo.latest.json"), { execution: { submittedCount: 0, submitted: [] } });
    await writeJson(join(baseDir, ".rumbling-hedge/research/researcher/strategy-feed.latest.json"), { directives: [], preferredStrategies: [] });
    await writeJson(join(baseDir, ".rumbling-hedge/research/no-edge-ledger/latest.json"), { count: 1, blockedStrategies: ["ict-displacement"] });
    await writeJson(join(baseDir, ".rumbling-hedge/research/forks/_latest-report.json"), { written: 1 });
    await writeJson(join(baseDir, ".rumbling-hedge/research/forks/_synthesis.latest.json"), { adoptedCount: 1 });
    await writeJson(join(baseDir, ".rumbling-hedge/research/positioning/latest.json"), { cot: { symbols: ["ES"] } });
    await writeJson(join(baseDir, ".rumbling-hedge/research/strategy-iterations/latest.json"), {});
    await writeJson(join(baseDir, ".rumbling-hedge/logs/bill-health.latest.json"), {});

    const report = await buildGoalReport({
      baseDir,
      now: () => now,
      env: {
        ...process.env,
        BILL_ACTIVE_TRACKS: "prediction,futures-core",
        BILL_EXECUTION_TRACKS: "prediction,futures-core",
        BILL_PREDICTION_EXECUTION_MODE: "paper",
        BILL_PREDICTION_LIVE_EXECUTION_ENABLED: "false",
        RH_LIVE_EXECUTION_ENABLED: "false",
        BILL_ENABLE_FUTURES_DEMO_EXECUTION: "false"
      }
    });

    expect(report.liveCanBeNext).toBe(false);
    expect(report.demoCanBeNext).toBe(false);
    expect(report.noOrdersSubmitted).toBe(true);
    expect(report.gaps.map((gap) => gap.id)).toContain("demo-fill-evidence");
    expect(report.gaps.some((gap) => gap.id === "live-gate-rolling-oos-depth")).toBe(true);
    expect(report.nextLiveSteps.join(" ")).toContain("Do not route live");
  });
});
