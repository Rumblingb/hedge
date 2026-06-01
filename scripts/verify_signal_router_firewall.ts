#!/usr/bin/env tsx
import SignalRouter, {
  billTradingDateKey,
  evaluateSignalRouterExecutionGate,
  todayDailyPlanPath,
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

function assert(condition: unknown, message: string): asserts condition {
  if (!condition) throw new Error(message);
}

function assertBlocker(blockers: string[], expected: string) {
  assert(blockers.includes(expected), `expected blocker ${JSON.stringify(expected)}; got ${JSON.stringify(blockers)}`);
}

async function main() {
  const checked: string[] = [];

  assert(
    billTradingDateKey(new Date("2026-05-29T23:30:00.000Z"), "Europe/London") === "2026-05-30",
    "SignalRouter daily plan date does not use Bill trading timezone"
  );
  assert(
    todayDailyPlanPath({} as NodeJS.ProcessEnv, new Date("2026-05-29T23:30:00.000Z")).endsWith("2026-05-30-bill-trading-plan.md"),
    "SignalRouter daily plan path does not use Bill trading timezone"
  );
  checked.push("use_bill_trading_timezone_daily_plan");

  const approvedEnv = {
    BILL_SIGNAL_ROUTER_ENABLED: "true",
    BILL_SIGNAL_ROUTER_LEGACY_FANOUT_ENABLED: "true",
    BILL_ENABLE_FUTURES_DEMO_EXECUTION: "true",
    RH_TOPSTEP_READ_ONLY: "false",
    RH_LIVE_EXECUTION_ENABLED: "false"
  } as NodeJS.ProcessEnv;
  const monitor = { status: "OK", hard_blockers: [], warnings: [] };
  const liveReadinessGate = { readyForDemoExpansion: true };

  const disabled = evaluateSignalRouterExecutionGate(signal, {
    env: {
      BILL_SIGNAL_ROUTER_ENABLED: "false",
      BILL_SIGNAL_ROUTER_LEGACY_FANOUT_ENABLED: "false",
      BILL_ENABLE_FUTURES_DEMO_EXECUTION: "false",
      RH_TOPSTEP_READ_ONLY: "true",
      RH_LIVE_EXECUTION_ENABLED: "false"
    } as NodeJS.ProcessEnv,
    monitor,
    liveReadinessGate,
    dailyPlanText: ""
  });
  assert(!disabled.ok, "SignalRouter allowed missing daily plan and disabled env");
  assertBlocker(disabled.blockers, "BILL_SIGNAL_ROUTER_ENABLED is not true");
  assertBlocker(disabled.blockers, "BILL_SIGNAL_ROUTER_LEGACY_FANOUT_ENABLED is not true");
  assertBlocker(disabled.blockers, "BILL_ENABLE_FUTURES_DEMO_EXECUTION is not true");
  assertBlocker(disabled.blockers, "RH_TOPSTEP_READ_ONLY is true");
  assertBlocker(disabled.blockers, "daily plan missing or unreadable");
  checked.push("fail_closed_missing_daily_or_disabled_env");

  const prose = evaluateSignalRouterExecutionGate(signal, {
    env: approvedEnv,
    monitor,
    liveReadinessGate,
    dailyPlanText: [
      "No new Bill/Hermes orders approved.",
      "- `BILL_ROUTE_APPROVAL: APPROVED`",
      "BROKER_RECONCILIATION: GREEN"
    ].join("\n")
  });
  assert(!prose.ok, "SignalRouter accepted markdown/prose approval token");
  assertBlocker(prose.blockers, "daily plan explicitly says no new Bill/Hermes orders approved");
  assertBlocker(prose.blockers, "daily plan lacks BILL_ROUTE_APPROVAL: APPROVED");
  checked.push("reject_markdown_or_prose_approval_tokens");

  const green = evaluateSignalRouterExecutionGate(signal, {
    env: approvedEnv,
    monitor,
    liveReadinessGate,
    dailyPlanText: [
      "BILL_ROUTE_APPROVAL: APPROVED",
      "BROKER_RECONCILIATION: GREEN"
    ].join("\n")
  });
  assert(green.ok, `SignalRouter blocked fully approved temp state: ${JSON.stringify(green.blockers)}`);
  checked.push("allow_only_exact_standalone_controls_with_green_artifacts");

  const monitorWarning = evaluateSignalRouterExecutionGate(signal, {
    env: approvedEnv,
    monitor: { status: "OK", hard_blockers: [], warnings: ["needs review"] },
    liveReadinessGate,
    dailyPlanText: [
      "BILL_ROUTE_APPROVAL: APPROVED",
      "BROKER_RECONCILIATION: GREEN"
    ].join("\n")
  });
  assert(!monitorWarning.ok, "SignalRouter allowed execution with monitor warning");
  assertBlocker(monitorWarning.blockers, "Topstep monitor warnings require reconciliation");
  checked.push("block_topstep_monitor_warnings");

  const liveReadinessRed = evaluateSignalRouterExecutionGate(signal, {
    env: approvedEnv,
    monitor,
    liveReadinessGate: { readyForDemoExpansion: false },
    dailyPlanText: [
      "BILL_ROUTE_APPROVAL: APPROVED",
      "BROKER_RECONCILIATION: GREEN"
    ].join("\n")
  });
  assert(!liveReadinessRed.ok, "SignalRouter allowed execution with live-readiness red");
  assertBlocker(liveReadinessRed.blockers, "live-readiness gate does not allow demo expansion");
  checked.push("block_live_readiness_red");

  const largeSignal = { ...signal, quantity: 2 };
  const sizeCap = evaluateSignalRouterExecutionGate(largeSignal, {
    env: approvedEnv,
    monitor,
    liveReadinessGate,
    maxContracts: 1,
    dailyPlanText: [
      "BILL_ROUTE_APPROVAL: APPROVED",
      "BROKER_RECONCILIATION: GREEN"
    ].join("\n")
  });
  assert(!sizeCap.ok, "SignalRouter allowed quantity above router cap");
  assertBlocker(sizeCap.blockers, "signal quantity 2 outside router cap 1");
  checked.push("block_quantity_above_router_cap");

  const originalFetch = globalThis.fetch;
  const originalWarn = console.warn;
  const calls: unknown[] = [];
  globalThis.fetch = (async (...args: unknown[]) => {
    calls.push(args);
    throw new Error("fetch should not be called while execution gate is blocked");
  }) as typeof fetch;
  console.warn = () => undefined;
  try {
    await new SignalRouter().route(signal);
  } finally {
    globalThis.fetch = originalFetch;
    console.warn = originalWarn;
  }
  assert(calls.length === 0, "SignalRouter made an external fetch while execution gate was blocked");
  checked.push("route_returns_before_network_when_blocked");

  console.log(JSON.stringify({
    ok: true,
    checked,
    script: "src/live/signalRouter.ts"
  }, null, 2));
}

main().catch((error) => {
  console.error(error instanceof Error ? error.message : String(error));
  process.exitCode = 1;
});
