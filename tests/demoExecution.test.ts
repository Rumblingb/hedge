import { afterEach, describe, expect, it, vi } from "vitest";
import { mkdirSync, mkdtempSync, writeFileSync } from "fs";
import { tmpdir } from "os";
import { join } from "path";
import { executeFuturesDemoLanes, demoExecutionCanaryBlockers, demoExecutionRouteApprovalBlockers } from "../src/live/demoExecution.js";
import { NoopNewsGate } from "../src/news/base.js";
import { getConfig } from "../src/config.js";
import { STRATEGY_CLASSIFICATION } from "../src/domain.js";
import type { Bar } from "../src/domain.js";
import type { DemoStrategySampleSnapshot } from "../src/live/demoSampling.js";

function buildIntradayBars(): Bar[] {
  return [
    { ts: "2026-04-17T13:35:00.000Z", symbol: "NQ", open: 18000, high: 18001, low: 17999.5, close: 18000.5, volume: 100 },
    { ts: "2026-04-17T13:40:00.000Z", symbol: "NQ", open: 18000.5, high: 18001.5, low: 18000, close: 18001, volume: 100 },
    { ts: "2026-04-17T13:45:00.000Z", symbol: "NQ", open: 18001, high: 18002, low: 18000.5, close: 18001.5, volume: 100 },
    { ts: "2026-04-17T13:50:00.000Z", symbol: "NQ", open: 18001.5, high: 18002.5, low: 18001, close: 18002, volume: 100 },
    { ts: "2026-04-17T13:55:00.000Z", symbol: "NQ", open: 18002, high: 18003, low: 18001.5, close: 18002.5, volume: 100 },
    { ts: "2026-04-17T14:00:00.000Z", symbol: "NQ", open: 18002.5, high: 18003.5, low: 18002, close: 18003, volume: 100 },
    { ts: "2026-04-17T14:05:00.000Z", symbol: "NQ", open: 18003, high: 18004.5, low: 18002.8, close: 18004.2, volume: 150 }
  ];
}

describe("executeFuturesDemoLanes", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
    STRATEGY_CLASSIFICATION["session-momentum"] = "QUARANTINED";
  });

  it("requires exact daily route approval and broker reconciliation before demo routing", () => {
    const root = mkdtempSync(join(tmpdir(), "bill-demo-route-gate-"));
    const stateDir = join(root, "state");
    const dailyPlanPath = join(root, "daily-plan.md");
    mkdirSync(stateDir, { recursive: true });
    vi.stubEnv("BILL_STATE_DIR", stateDir);
    vi.stubEnv("BILL_DAILY_PLAN_PATH", dailyPlanPath);

    writeFileSync(dailyPlanPath, [
      "No new Bill/Hermes orders approved.",
      "- `BILL_ROUTE_APPROVAL: APPROVED`",
      "BROKER_RECONCILIATION: GREEN"
    ].join("\n"));

    expect(demoExecutionRouteApprovalBlockers()).toEqual(expect.arrayContaining([
      "daily plan explicitly says no new Bill/Hermes orders approved",
      "daily plan lacks BILL_ROUTE_APPROVAL: APPROVED",
      "Topstep monitor is not OK: missing",
      "live-readiness gate does not allow demo expansion"
    ]));

    writeFileSync(dailyPlanPath, [
      "BILL_ROUTE_APPROVAL: APPROVED",
      "BROKER_RECONCILIATION: GREEN"
    ].join("\n"));
    writeFileSync(join(stateDir, "topstep-100k-monitor.latest.json"), JSON.stringify({
      status: "OK",
      hard_blockers: [],
      warnings: []
    }));
    writeFileSync(join(stateDir, "live-readiness-gate.latest.json"), JSON.stringify({
      readyForDemoExpansion: true,
      blockers: []
    }));

    expect(demoExecutionRouteApprovalBlockers()).toEqual([]);
  });

  it("allows a bounded demo canary to bypass broad demo expansion only with fresh broker/data proof", () => {
    const root = mkdtempSync(join(tmpdir(), "bill-demo-canary-gate-"));
    const stateDir = join(root, "state");
    const dailyPlanPath = join(root, "daily-plan.md");
    mkdirSync(stateDir, { recursive: true });
    vi.stubEnv("BILL_STATE_DIR", stateDir);
    vi.stubEnv("BILL_DAILY_PLAN_PATH", dailyPlanPath);
    vi.stubEnv("BILL_ENABLE_FUTURES_DEMO_EXECUTION", "true");
    vi.stubEnv("RH_TOPSTEP_READ_ONLY", "false");
    vi.stubEnv("RH_LIVE_EXECUTION_ENABLED", "true");
    vi.stubEnv("RH_TOPSTEP_DEMO_ONLY", "true");
    vi.stubEnv("BILL_FUTURES_DEMO_CANARY_ENABLED", "true");
    vi.stubEnv("BILL_FUTURES_DEMO_APPROVAL_ID", "demo-canary-2026-06-08");
    vi.stubEnv("BILL_FUTURES_DEMO_MAX_ORDERS_PER_RUN", "1");
    vi.stubEnv("RH_MAX_CONTRACTS", "1");

    writeFileSync(dailyPlanPath, [
      "BILL_ROUTE_APPROVAL: APPROVED",
      "BROKER_RECONCILIATION: GREEN",
      "BILL_DEMO_CANARY: APPROVED"
    ].join("\n"));
    writeFileSync(join(stateDir, "topstep-100k-monitor.latest.json"), JSON.stringify({
      status: "OK",
      hard_blockers: [],
      warnings: []
    }));
    writeFileSync(join(stateDir, "live-readiness-gate.latest.json"), JSON.stringify({
      readyForDemoExpansion: false,
      blockers: ["walk-forward gate is not deployable"]
    }));
    writeFileSync(join(stateDir, "realtime-data-preflight.latest.json"), JSON.stringify({
      readyForExecutionData: true,
      blockers: [],
      decision: "allow-execution-data"
    }));
    writeFileSync(join(stateDir, "futures-broker-parity-plan.latest.json"), JSON.stringify({
      current: {
        topstepBrokerLocalBarParityPassed: true,
        topstepRealtimeReadyForExecutionDataProof: true,
        topstep: {
          brokerFlat: true,
          openPositions: 0
        }
      }
    }));

    expect(demoExecutionCanaryBlockers()).toEqual([]);
    expect(demoExecutionRouteApprovalBlockers()).toEqual([]);
  });

  it("keeps demo canary blocked without explicit daily canary approval and fresh data", () => {
    const root = mkdtempSync(join(tmpdir(), "bill-demo-canary-blocked-"));
    const stateDir = join(root, "state");
    const dailyPlanPath = join(root, "daily-plan.md");
    mkdirSync(stateDir, { recursive: true });
    vi.stubEnv("BILL_STATE_DIR", stateDir);
    vi.stubEnv("BILL_DAILY_PLAN_PATH", dailyPlanPath);
    vi.stubEnv("BILL_FUTURES_DEMO_CANARY_ENABLED", "true");
    vi.stubEnv("BILL_FUTURES_DEMO_APPROVAL_ID", "");
    vi.stubEnv("BILL_FUTURES_DEMO_MAX_ORDERS_PER_RUN", "2");
    vi.stubEnv("RH_MAX_CONTRACTS", "2");

    writeFileSync(dailyPlanPath, [
      "BILL_ROUTE_APPROVAL: APPROVED",
      "BROKER_RECONCILIATION: GREEN"
    ].join("\n"));
    writeFileSync(join(stateDir, "topstep-100k-monitor.latest.json"), JSON.stringify({
      status: "OK",
      hard_blockers: [],
      warnings: []
    }));

    const blockers = demoExecutionRouteApprovalBlockers();

    expect(blockers).toContain("daily plan lacks BILL_DEMO_CANARY: APPROVED");
    expect(blockers).toContain("BILL_FUTURES_DEMO_APPROVAL_ID is required for demo canary routing");
    expect(blockers).toContain("demo canary max orders per run must be <= 1");
    expect(blockers).toContain("demo canary RH_MAX_CONTRACTS must be <= 1");
    expect(blockers).toContain("demo canary requires realtime-data-preflight readyForExecutionData=true, got missing");
  });

  it("does not submit non-executable strategy classes even when a lane has a valid signal", async () => {
    const config = getConfig();
    config.mode = "live";
    config.live.enabled = true;
    config.live.demoOnly = true;
    config.live.readOnly = false;
    config.live.accountId = "465";
    config.live.allowedAccountIds = ["465"];
    config.live.baseUrl = "https://api.example.com";
    config.live.username = "demo-user";
    config.live.apiKey = "secret";
    config.guardrails.allowedSymbols = ["NQ"];

    const sampleSnapshot: DemoStrategySampleSnapshot = {
      ts: "2026-04-17T14:05:00.000Z",
      sampleSequence: 0,
      laneCount: 1,
      sampledStrategies: ["session-momentum"],
      lanes: [
        {
          accountId: "465",
          label: "Momentum",
          slot: 1,
          primaryStrategy: "session-momentum",
          strategies: ["session-momentum"],
          focusSymbol: "NQ",
          action: "shadow-observe",
          rationale: "Momentum lane",
          candidate: null,
          alternatives: []
        }
      ]
    };

    const submit = vi.fn().mockResolvedValue({
      accepted: true,
      orderId: "ord-1",
      message: "demo submitted"
    });

    const report = await executeFuturesDemoLanes({
      bars: buildIntradayBars(),
      config,
      newsGate: new NoopNewsGate(),
      trades: [],
      sampleSnapshot,
      killSwitchActive: false,
      enabled: true,
      maxOrdersPerRun: 1,
      preflightBlockers: [],
      nqChallengeState: null,
      adapterFactory: () => ({
        submit,
        flattenAll: vi.fn()
      })
    });

    expect(report.submittedCount).toBe(0);
    expect(report.telemetry.signalCount).toBe(1);
    expect(report.telemetry.byStrategy["session-momentum"]?.submitted).toBe(0);
    expect(report.lanes[0]?.status).toBe("skipped");
    expect(report.lanes[0]?.reason).toContain("strategy classification");
    expect(report.lanes[0]?.signal?.symbol).toBe("NQ");
    expect(submit).not.toHaveBeenCalled();
  });

  it("blocks quarantined lanes before account routing", async () => {
    const config = getConfig();
    config.mode = "live";
    config.live.enabled = true;
    config.live.demoOnly = true;
    config.live.readOnly = false;
    config.live.allowedAccountIds = ["inactive", "active"];
    config.live.baseUrl = "https://api.example.com";
    config.live.username = "demo-user";
    config.live.apiKey = "secret";
    config.guardrails.allowedSymbols = ["NQ"];

    const sampleSnapshot: DemoStrategySampleSnapshot = {
      ts: "2026-04-17T14:05:00.000Z",
      sampleSequence: 0,
      laneCount: 2,
      sampledStrategies: ["session-momentum"],
      lanes: [
        {
          accountId: "inactive",
          label: "Inactive",
          slot: 1,
          primaryStrategy: "session-momentum",
          strategies: ["session-momentum"],
          focusSymbol: "NQ",
          action: "shadow-observe",
          rationale: "Inactive lane",
          candidate: null,
          alternatives: []
        },
        {
          accountId: "active",
          label: "Active",
          slot: 2,
          primaryStrategy: "session-momentum",
          strategies: ["session-momentum"],
          focusSymbol: "NQ",
          action: "shadow-observe",
          rationale: "Active lane",
          candidate: null,
          alternatives: []
        }
      ]
    };

    const submitFailed = vi.fn().mockRejectedValue(new Error("account inactive"));
    const submitSucceeded = vi.fn().mockResolvedValue({
      accepted: true,
      orderId: "ord-2",
      message: "demo submitted"
    });

    const report = await executeFuturesDemoLanes({
      bars: buildIntradayBars(),
      config,
      newsGate: new NoopNewsGate(),
      trades: [],
      sampleSnapshot,
      killSwitchActive: false,
      enabled: true,
      maxOrdersPerRun: 1,
      preflightBlockers: [],
      nqChallengeState: null,
      adapterFactory: (liveConfig) => ({
        submit: liveConfig.accountId === "inactive" ? submitFailed : submitSucceeded,
        flattenAll: vi.fn()
      })
    });

    expect(report.submittedCount).toBe(0);
    expect(report.skippedCount).toBe(2);
    expect(report.telemetry.signalCount).toBe(2);
    expect(report.telemetry.byStrategy["session-momentum"]?.skipped).toBe(2);
    expect(report.lanes[0]?.reason).toContain("strategy classification");
    expect(report.lanes[1]?.status).toBe("skipped");
    expect(submitFailed).not.toHaveBeenCalled();
    expect(submitSucceeded).not.toHaveBeenCalled();
  });

  it("captures shadow signals when execution routing is blocked", async () => {
    const config = getConfig();
    config.mode = "paper";
    config.live.enabled = false;
    config.live.demoOnly = true;
    config.live.readOnly = true;
    config.live.allowedAccountIds = ["shadow"];
    config.guardrails.allowedSymbols = ["NQ"];

    const sampleSnapshot: DemoStrategySampleSnapshot = {
      ts: "2026-04-17T14:05:00.000Z",
      sampleSequence: 0,
      laneCount: 1,
      sampledStrategies: ["session-momentum"],
      lanes: [
        {
          accountId: "shadow",
          label: "Shadow",
          slot: 1,
          primaryStrategy: "session-momentum",
          strategies: ["session-momentum"],
          focusSymbol: "NQ",
          action: "shadow-observe",
          rationale: "Blocked but learnable lane",
          candidate: null,
          alternatives: []
        }
      ]
    };

    const submit = vi.fn();
    const report = await executeFuturesDemoLanes({
      bars: buildIntradayBars(),
      config,
      newsGate: new NoopNewsGate(),
      trades: [],
      sampleSnapshot,
      killSwitchActive: false,
      enabled: false,
      maxOrdersPerRun: 1,
      preflightBlockers: ["promotion gate is not deployable"],
      nqChallengeState: null,
      adapterFactory: () => ({
        submit,
        flattenAll: vi.fn()
      })
    });

    expect(report.mode).toBe("shadow-only");
    expect(report.submittedCount).toBe(0);
    expect(report.telemetry.signalCount).toBe(1);
    expect(report.telemetry.routedBlockerCount).toBeGreaterThan(0);
    expect(report.telemetry.byStrategy["session-momentum"]?.signals).toBe(1);
    expect(report.lanes[0]?.status).toBe("skipped");
    expect(report.lanes[0]?.reason).toContain("shadow signal captured");
    expect(report.lanes[0]?.signal?.strategyId).toBe("session-momentum");
    expect(submit).not.toHaveBeenCalled();
  });

  it("never routes synthetic demo fallback signals to Topstep", async () => {
    vi.stubEnv("BILL_FUTURES_DEMO_EXPLORATION_ENABLED", "true");

    const config = getConfig();
    config.mode = "live";
    config.live.enabled = true;
    config.live.demoOnly = true;
    config.live.readOnly = false;
    config.live.accountId = "465";
    config.live.allowedAccountIds = ["465"];
    config.live.baseUrl = "https://api.example.com";
    config.live.username = "demo-user";
    config.live.apiKey = "secret";
    config.guardrails.allowedSymbols = ["NQ"];

    const sampleSnapshot: DemoStrategySampleSnapshot = {
      ts: "2026-04-17T14:05:00.000Z",
      sampleSequence: 0,
      laneCount: 1,
      sampledStrategies: ["opening-range-reversal"],
      lanes: [
        {
          accountId: "465",
          label: "Fallback",
          slot: 1,
          primaryStrategy: "opening-range-reversal",
          strategies: ["opening-range-reversal"],
          focusSymbol: "NQ",
          action: "standby",
          rationale: "No edge lane",
          candidate: null,
          alternatives: []
        }
      ]
    };

    const submit = vi.fn().mockResolvedValue({
      accepted: true,
      orderId: "ord-fallback",
      message: "should not submit"
    });

    const report = await executeFuturesDemoLanes({
      bars: buildIntradayBars(),
      config,
      newsGate: new NoopNewsGate(),
      trades: [],
      sampleSnapshot,
      killSwitchActive: false,
      enabled: true,
      maxOrdersPerRun: 1,
      preflightBlockers: [],
      nqChallengeState: null,
      adapterFactory: () => ({
        submit,
        flattenAll: vi.fn()
      })
    });

    expect(report.submittedCount).toBe(0);
    expect(report.telemetry.signalCount).toBe(1);
    expect(report.lanes[0]?.status).toBe("skipped");
    expect(report.lanes[0]?.reason).toContain("synthetic demo fallback signal is shadow-only");
    expect(report.lanes[0]?.signal?.strategyId).toBe("opening-range-reversal-demo-fallback");
    expect(submit).not.toHaveBeenCalled();
  });
});
