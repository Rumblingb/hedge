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
    await writeJson(join(baseDir, ".rumbling-hedge/state/data-freshness-gate.latest.json"), {
      verdict: "PASS",
      action: "allow_trades",
      checks: [
        { symbol: "nq", status: "PASS", source: "tradingview_pro", reason: "ok" },
        { symbol: "es", status: "PASS", source: "tradingview_pro", reason: "ok" }
      ]
    });
    await writeJson(join(baseDir, ".rumbling-hedge/state/futures-cost-slippage-gate.latest.json"), {
      writesOrders: false,
      backtrader: { survivorCount: 3 },
      volRegimeOos: { survivorCount: 0 }
    });
    await writeJson(join(baseDir, ".rumbling-hedge/state/signal-quality-advisor.latest.json"), {
      writesOrders: false,
      overallRating: 8,
      blockers: []
    });
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
    expect(report.blockers.join(" ")).toContain("futures cost/slippage gate is not deployable");
    expect(report.blockers.join(" ")).toContain("prediction evidence is not live-ready");
    expect(report.checks.find((item) => item.name === "signal-quality-clean")?.passed).toBe(true);
    expect(report.blockers.join(" ")).not.toContain("live prediction execution is enabled");
    expect(report.checks.find((item) => item.name === "live-routing-disabled-or-micro-sandboxed")?.passed).toBe(true);
  });

  it("blocks demo expansion when futures realtime data is stale or fallback-only", async ({ task }) => {
    const baseDir = join("/tmp", `bill-live-gate-stale-data-${task.id}`);
    await mkdir(join(baseDir, ".rumbling-hedge/state"), { recursive: true });
    await mkdir(join(baseDir, ".rumbling-hedge/research/researcher"), { recursive: true });
    await mkdir(join(baseDir, ".rumbling-hedge/research/no-edge-ledger"), { recursive: true });
    await mkdir(join(baseDir, ".rumbling-hedge/logs"), { recursive: true });

    const now = "2026-05-08T00:00:00.000Z";
    await writeJson(join(baseDir, ".rumbling-hedge/state/prediction-cycle.latest.json"), { ts: now, scan: { counts: { "paper-trade": 1 }, diagnostics: { viablePairs: 1 } } });
    await writeJson(join(baseDir, ".rumbling-hedge/state/researcher-scheduler.latest.json"), { report: { report: { strategyHypothesesCount: 1 } } });
    await writeJson(join(baseDir, ".rumbling-hedge/state/data-freshness-gate.latest.json"), {
      verdict: "STALE",
      action: "block_all_trades",
      checks: [
        { symbol: "nq", status: "STALE", source: "yahoo_fallback", reason: "fallback quote is delayed/research-only" },
        { symbol: "es", status: "STALE", source: "yahoo_fallback", reason: "fallback quote is delayed/research-only" }
      ]
    });
    await writeJson(join(baseDir, ".rumbling-hedge/state/futures-cost-slippage-gate.latest.json"), {
      writesOrders: false,
      backtrader: { survivorCount: 8 },
      volRegimeOos: { survivorCount: 4 }
    });
    await writeJson(join(baseDir, ".rumbling-hedge/state/signal-quality-advisor.latest.json"), {
      writesOrders: false,
      overallRating: 8,
      blockers: []
    });
    await writeJson(join(baseDir, ".rumbling-hedge/state/strategy-lab.latest.json"), { mode: "light", rollingOos: { aggregate: { windowsEvaluated: 4 } } });
    await writeJson(join(baseDir, ".rumbling-hedge/state/quant-autonomy.latest.json"), {});
    await writeJson(join(baseDir, ".rumbling-hedge/state/openjarvis-board.md"), {});
    await writeJson(join(baseDir, ".rumbling-hedge/state/strategy-factory.latest.json"), {
      gates: {
        walkforwardDeployable: true,
        rollingOosWindows: 4,
        minRollingOosWindows: 4,
        rollingOosDeployableWindows: 4,
        liveReadinessDeployable: true
      }
    });
    await writeJson(join(baseDir, ".rumbling-hedge/state/futures-demo.latest.json"), { execution: { submittedCount: 0, submitted: [] } });
    await writeJson(join(baseDir, ".rumbling-hedge/research/researcher/strategy-feed.latest.json"), { directives: [], preferredStrategies: [] });
    await writeJson(join(baseDir, ".rumbling-hedge/research/no-edge-ledger/latest.json"), { count: 1, blockedStrategies: [] });
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
        BILL_PREDICTION_LIVE_EXECUTION_ENABLED: "false",
        BILL_ENABLE_FUTURES_DEMO_EXECUTION: "false",
        BILL_PREDICTION_EXECUTION_MODE: "paper"
      }
    });

    expect(report.readyForDemoExpansion).toBe(false);
    expect(report.checks.find((item) => item.name === "futures-data-fresh")?.passed).toBe(false);
    expect(report.checks.find((item) => item.name === "futures-cost-slippage-deployable")?.passed).toBe(true);
    expect(report.checks.find((item) => item.name === "signal-quality-clean")?.passed).toBe(true);
    expect(report.checks.find((item) => item.name === "prediction-live-evidence-ready")?.passed).toBe(true);
    expect(report.blockers.join(" ")).toContain("futures realtime data is not execution-grade");
  });

  it("blocks demo expansion when futures cost stress has no OOS survivors", async ({ task }) => {
    const baseDir = join("/tmp", `bill-live-gate-cost-${task.id}`);
    await mkdir(join(baseDir, ".rumbling-hedge/state"), { recursive: true });
    await mkdir(join(baseDir, ".rumbling-hedge/research/researcher"), { recursive: true });
    await mkdir(join(baseDir, ".rumbling-hedge/research/no-edge-ledger"), { recursive: true });
    await mkdir(join(baseDir, ".rumbling-hedge/logs"), { recursive: true });

    const now = "2026-05-08T00:00:00.000Z";
    await writeJson(join(baseDir, ".rumbling-hedge/state/prediction-cycle.latest.json"), { ts: now, scan: { counts: { "paper-trade": 1 }, diagnostics: { viablePairs: 1 } } });
    await writeJson(join(baseDir, ".rumbling-hedge/state/researcher-scheduler.latest.json"), { report: { report: { strategyHypothesesCount: 1 } } });
    await writeJson(join(baseDir, ".rumbling-hedge/state/data-freshness-gate.latest.json"), {
      verdict: "PASS",
      action: "allow_trades",
      checks: [
        { symbol: "nq", status: "PASS", source: "tradingview_pro", reason: "ok" },
        { symbol: "es", status: "PASS", source: "tradingview_pro", reason: "ok" }
      ]
    });
    await writeJson(join(baseDir, ".rumbling-hedge/state/futures-cost-slippage-gate.latest.json"), {
      writesOrders: false,
      backtrader: { survivorCount: 57 },
      volRegimeOos: { survivorCount: 0 }
    });
    await writeJson(join(baseDir, ".rumbling-hedge/state/signal-quality-advisor.latest.json"), {
      writesOrders: false,
      overallRating: 8,
      blockers: []
    });
    await writeJson(join(baseDir, ".rumbling-hedge/state/strategy-lab.latest.json"), { mode: "light", rollingOos: { aggregate: { windowsEvaluated: 4 } } });
    await writeJson(join(baseDir, ".rumbling-hedge/state/quant-autonomy.latest.json"), {});
    await writeJson(join(baseDir, ".rumbling-hedge/state/openjarvis-board.md"), {});
    await writeJson(join(baseDir, ".rumbling-hedge/state/strategy-factory.latest.json"), {
      gates: {
        walkforwardDeployable: true,
        rollingOosWindows: 4,
        minRollingOosWindows: 4,
        rollingOosDeployableWindows: 4,
        liveReadinessDeployable: true
      }
    });
    await writeJson(join(baseDir, ".rumbling-hedge/state/futures-demo.latest.json"), { execution: { submittedCount: 0, submitted: [] } });
    await writeJson(join(baseDir, ".rumbling-hedge/research/researcher/strategy-feed.latest.json"), { directives: [], preferredStrategies: [] });
    await writeJson(join(baseDir, ".rumbling-hedge/research/no-edge-ledger/latest.json"), { count: 1, blockedStrategies: [] });
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
        BILL_PREDICTION_LIVE_EXECUTION_ENABLED: "false",
        BILL_ENABLE_FUTURES_DEMO_EXECUTION: "false",
        BILL_PREDICTION_EXECUTION_MODE: "paper"
      }
    });

    expect(report.readyForDemoExpansion).toBe(false);
    expect(report.checks.find((item) => item.name === "futures-cost-slippage-deployable")?.passed).toBe(false);
    expect(report.checks.find((item) => item.name === "signal-quality-clean")?.passed).toBe(true);
    expect(report.checks.find((item) => item.name === "prediction-live-evidence-ready")?.passed).toBe(true);
    expect(report.blockers.join(" ")).toContain("futures cost/slippage gate is not deployable");
  });

  it("blocks demo expansion when signal quality advisor reports stale or fallback shadow inputs", async ({ task }) => {
    const baseDir = join("/tmp", `bill-live-gate-signal-quality-${task.id}`);
    await mkdir(join(baseDir, ".rumbling-hedge/state"), { recursive: true });
    await mkdir(join(baseDir, ".rumbling-hedge/research/researcher"), { recursive: true });
    await mkdir(join(baseDir, ".rumbling-hedge/research/no-edge-ledger"), { recursive: true });
    await mkdir(join(baseDir, ".rumbling-hedge/logs"), { recursive: true });

    const now = "2026-05-08T00:00:00.000Z";
    await writeJson(join(baseDir, ".rumbling-hedge/state/prediction-cycle.latest.json"), { ts: now, scan: { counts: { "paper-trade": 1 }, diagnostics: { viablePairs: 1 } } });
    await writeJson(join(baseDir, ".rumbling-hedge/state/researcher-scheduler.latest.json"), { report: { report: { strategyHypothesesCount: 1 } } });
    await writeJson(join(baseDir, ".rumbling-hedge/state/data-freshness-gate.latest.json"), {
      verdict: "PASS",
      action: "allow_trades",
      checks: [
        { symbol: "nq", status: "PASS", source: "tradingview_pro", reason: "ok" },
        { symbol: "es", status: "PASS", source: "tradingview_pro", reason: "ok" }
      ]
    });
    await writeJson(join(baseDir, ".rumbling-hedge/state/futures-cost-slippage-gate.latest.json"), {
      writesOrders: false,
      backtrader: { survivorCount: 57 },
      volRegimeOos: { survivorCount: 4 }
    });
    await writeJson(join(baseDir, ".rumbling-hedge/state/signal-quality-advisor.latest.json"), {
      writesOrders: false,
      overallRating: 5.5,
      blockers: ["shadow no-data/fallback input: whale_flow"]
    });
    await writeJson(join(baseDir, ".rumbling-hedge/state/strategy-lab.latest.json"), { mode: "light", rollingOos: { aggregate: { windowsEvaluated: 4 } } });
    await writeJson(join(baseDir, ".rumbling-hedge/state/quant-autonomy.latest.json"), {});
    await writeJson(join(baseDir, ".rumbling-hedge/state/openjarvis-board.md"), {});
    await writeJson(join(baseDir, ".rumbling-hedge/state/strategy-factory.latest.json"), {
      gates: {
        walkforwardDeployable: true,
        rollingOosWindows: 4,
        minRollingOosWindows: 4,
        rollingOosDeployableWindows: 4,
        liveReadinessDeployable: true
      }
    });
    await writeJson(join(baseDir, ".rumbling-hedge/state/futures-demo.latest.json"), { execution: { submittedCount: 0, submitted: [] } });
    await writeJson(join(baseDir, ".rumbling-hedge/research/researcher/strategy-feed.latest.json"), { directives: [], preferredStrategies: [] });
    await writeJson(join(baseDir, ".rumbling-hedge/research/no-edge-ledger/latest.json"), { count: 1, blockedStrategies: [] });
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
        BILL_PREDICTION_LIVE_EXECUTION_ENABLED: "false",
        BILL_ENABLE_FUTURES_DEMO_EXECUTION: "false",
        BILL_PREDICTION_EXECUTION_MODE: "paper"
      }
    });

    expect(report.readyForDemoExpansion).toBe(false);
    expect(report.checks.find((item) => item.name === "signal-quality-clean")?.passed).toBe(false);
    expect(report.blockers.join(" ")).toContain("shadow no-data/fallback input: whale_flow");
  });
});
