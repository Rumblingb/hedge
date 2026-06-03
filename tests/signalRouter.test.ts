import { afterEach, describe, expect, it, vi } from "vitest";
import SignalRouter, {
  billTradingDateKey,
  evaluateSignalRouterExecutionGate,
  futuresPointValueDollars,
  pickMyTradeDollarBracket,
  todayDailyPlanPath,
  validatePreTradeDecision,
  type OrbSignal
} from "../src/live/signalRouter.js";

const signal: OrbSignal = {
  ticker: "MNQ",
  action: "buy",
  quantity: 1,
  entryPrice: 29000,
  stopLoss: 28970,
  takeProfit: 29050
};

const originalFetch = globalThis.fetch;

afterEach(() => {
  globalThis.fetch = originalFetch;
  vi.restoreAllMocks();
});

function decision(overrides: Record<string, unknown> = {}) {
  return {
    timestamp: "2026-05-17T10:00:00.000Z",
    decision: "TRADE",
    direction: "LONG",
    conviction: "HIGH",
    contracts: 1,
    sl_pts: 30,
    tp1_pts: 50,
    tp2_pts: 100,
    trail_pts: 30,
    account_split: { Topstep: 1 },
    stagger_min: 5,
    warnings: [],
    ...overrides
  } as any;
}

describe("validatePreTradeDecision", () => {
  const now = new Date("2026-05-17T10:05:00.000Z");

  it("fails closed when the pre-trade artifact is missing", () => {
    expect(validatePreTradeDecision(null, signal, now)).toEqual({
      ok: false,
      reason: "missing pre-trade decision"
    });
  });

  it("requires an explicit TRADE decision", () => {
    expect(validatePreTradeDecision(decision({ decision: "REDUCED" }), signal, now).ok).toBe(false);
    expect(validatePreTradeDecision(decision({ decision: "NO_TRADE" }), signal, now).ok).toBe(false);
  });

  it("blocks stale, forced, and direction-mismatched decisions", () => {
    expect(validatePreTradeDecision(decision({ timestamp: "2026-05-17T09:40:00.000Z" }), signal, now).reason).toContain("stale");
    expect(validatePreTradeDecision(decision({ warnings: ["STALE DATA - use --force to override"] }), signal, now).reason).toContain("blocking warning");
    expect(validatePreTradeDecision(decision({ direction: "SHORT" }), signal, now).reason).toContain("conflicts");
  });

  it("allows a fresh matched TRADE decision inside the approved size", () => {
    expect(validatePreTradeDecision(decision(), signal, now)).toEqual({ ok: true });
  });
});

describe("evaluateSignalRouterExecutionGate", () => {
  const approvedEnv = {
    BILL_SIGNAL_ROUTER_ENABLED: "true",
    BILL_SIGNAL_ROUTER_LEGACY_FANOUT_ENABLED: "true",
    BILL_ENABLE_FUTURES_DEMO_EXECUTION: "true",
    RH_TOPSTEP_READ_ONLY: "false",
    RH_LIVE_EXECUTION_ENABLED: "false"
  } as NodeJS.ProcessEnv;
  const monitor = { status: "OK", hard_blockers: [], warnings: [] };
  const liveReadinessGate = { readyForDemoExpansion: true };

  it("does not accept approval tokens embedded in prose or markdown examples", () => {
    const gate = evaluateSignalRouterExecutionGate(signal, {
      env: approvedEnv,
      monitor,
      liveReadinessGate,
      dailyPlanText: [
        "No new Bill/Hermes orders approved.",
        "- `BILL_ROUTE_APPROVAL: APPROVED`",
        "BROKER_RECONCILIATION: GREEN"
      ].join("\n")
    });

    expect(gate.ok).toBe(false);
    expect(gate.blockers).toContain("daily plan explicitly says no new Bill/Hermes orders approved");
    expect(gate.blockers).toContain("daily plan lacks BILL_ROUTE_APPROVAL: APPROVED");
  });

  it("requires the same deterministic route controls as the master bridge", () => {
    expect(evaluateSignalRouterExecutionGate(signal, {
      env: approvedEnv,
      monitor,
      liveReadinessGate,
      dailyPlanText: [
        "BILL_ROUTE_APPROVAL: APPROVED",
        "BROKER_RECONCILIATION: GREEN"
      ].join("\n")
    })).toEqual({ ok: true, reason: undefined, blockers: [] });
  });

  it("blocks when live-readiness or broker monitor state is not green", () => {
    const gate = evaluateSignalRouterExecutionGate(signal, {
      env: approvedEnv,
      monitor: { status: "OK", hard_blockers: [], warnings: ["needs reconciliation"] },
      liveReadinessGate: { readyForDemoExpansion: false },
      dailyPlanText: [
        "BILL_ROUTE_APPROVAL: APPROVED",
        "BROKER_RECONCILIATION: GREEN"
      ].join("\n")
    });

    expect(gate.ok).toBe(false);
    expect(gate.blockers).toContain("Topstep monitor warnings require reconciliation");
    expect(gate.blockers).toContain("live-readiness gate does not allow demo expansion");
  });

  it("requires an extra explicit acknowledgement for the legacy fanout router", () => {
    const gate = evaluateSignalRouterExecutionGate(signal, {
      env: {
        BILL_SIGNAL_ROUTER_ENABLED: "true",
        BILL_ENABLE_FUTURES_DEMO_EXECUTION: "true",
        RH_TOPSTEP_READ_ONLY: "false",
        RH_LIVE_EXECUTION_ENABLED: "false"
      } as NodeJS.ProcessEnv,
      monitor,
      liveReadinessGate,
      dailyPlanText: [
        "BILL_ROUTE_APPROVAL: APPROVED",
        "BROKER_RECONCILIATION: GREEN"
      ].join("\n")
    });

    expect(gate.ok).toBe(false);
    expect(gate.blockers).toContain("BILL_SIGNAL_ROUTER_LEGACY_FANOUT_ENABLED is not true");
  });

  it("keeps the legacy direct Topstep path quarantined because it is not the OCO bridge", () => {
    const gate = evaluateSignalRouterExecutionGate(signal, {
      env: {
        ...approvedEnv,
        BILL_SIGNAL_ROUTER_TOPSTEP_DIRECT_ENABLED: "true"
      } as NodeJS.ProcessEnv,
      monitor,
      liveReadinessGate,
      dailyPlanText: [
        "BILL_ROUTE_APPROVAL: APPROVED",
        "BROKER_RECONCILIATION: GREEN"
      ].join("\n")
    });

    expect(gate.ok).toBe(false);
    expect(gate.blockers).toContain("SignalRouter direct Topstep path is quarantined; use the OCO Topstep demo bridge");
  });
});

describe("PickMyTrade futures dollar brackets", () => {
  it("uses symbol-specific futures point values instead of assuming MNQ is MES", () => {
    expect(futuresPointValueDollars("CON.F.US.MNQ.M26")).toBe(2);
    expect(futuresPointValueDollars("MNQ")).toBe(2);
    expect(futuresPointValueDollars("NQ")).toBe(20);
    expect(futuresPointValueDollars("MES")).toBe(5);
    expect(futuresPointValueDollars("ES")).toBe(50);

    expect(pickMyTradeDollarBracket({
      ticker: "CON.F.US.MNQ.M26",
      action: "buy",
      quantity: 8,
      entryPrice: 30000,
      stopLoss: 29993,
      takeProfit: 30020
    })).toEqual({
      dollarSl: 112,
      dollarTp: 320,
      pointValue: 2
    });
  });
});

describe("Bill trading date routing", () => {
  it("uses the Bill trading timezone for the daily plan date", () => {
    const now = new Date("2026-05-29T23:30:00.000Z");
    expect(billTradingDateKey(now, "Europe/London")).toBe("2026-05-30");
    expect(todayDailyPlanPath({} as NodeJS.ProcessEnv, now)).toBe(
      "/Users/brain/Documents/memorybrain/Agent-Hermes/daily/2026-05-30-bill-trading-plan.md"
    );
  });
});

describe("SignalRouter network firewall", () => {
  it("does not call external APIs when the execution gate is blocked", async () => {
    const fetchSpy = vi.fn(async () => {
      throw new Error("fetch should not be called while execution gate is blocked");
    });
    globalThis.fetch = fetchSpy as unknown as typeof fetch;
    const warnSpy = vi.spyOn(console, "warn").mockImplementation(() => undefined);

    await new SignalRouter().route(signal);

    expect(fetchSpy).not.toHaveBeenCalled();
    expect(warnSpy).toHaveBeenCalledWith(expect.stringContaining("[SignalRouter] Shadow-only:"));
  });
});
