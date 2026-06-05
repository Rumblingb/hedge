import { access, mkdir, readFile, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import type { CashflowBoardReport } from "./cashflowBoard.js";

export type IntegrationPriority = "merge-now" | "adapt-later" | "quarantine";
export type LiveMoneySeverity = "critical" | "high" | "medium";

export interface HermesIntegrationItem {
  source: "hermes" | "hedge";
  path: string;
  priority: IntegrationPriority;
  role: string;
  combineAs: string;
  reason: string;
}

export interface LiveMoneyHole {
  severity: LiveMoneySeverity;
  area: string;
  hole: string;
  requiredFix: string;
}

export interface HermesIntegrationAuditReport {
  command: "hermes-integration-audit";
  generatedAt: string;
  status: "research-control-plane" | "blocked-for-live-money";
  paths: {
    outputPath: string;
    hermesRoot: string;
    hedgeRoot: string;
    cashflowBoardPath: string;
  };
  observedArchitecture: {
    hermesRole: string;
    hedgeRole: string;
    llmBoundary: string;
    algoBoundary: string;
  };
  mergePlan: HermesIntegrationItem[];
  rejectedPatterns: string[];
  liveMoneyHoles: LiveMoneyHole[];
  firstLaneOperatingModel: string[];
  predictionMarketsUse: string[];
  propFirmUse: string[];
  capitalUnlockRules: string[];
  nextImplementationOrder: string[];
  currentBoardStatus: CashflowBoardReport["status"] | "missing";
}

const DEFAULT_OUTPUT_PATH = ".rumbling-hedge/state/hermes-integration-audit.latest.json";

async function exists(path: string): Promise<boolean> {
  try {
    await access(path);
    return true;
  } catch {
    return false;
  }
}

async function readJsonSafe<T>(path: string): Promise<T | null> {
  try {
    return JSON.parse(await readFile(path, "utf8")) as T;
  } catch {
    return null;
  }
}

function item(args: HermesIntegrationItem): HermesIntegrationItem {
  return args;
}

function liveHole(args: LiveMoneyHole): LiveMoneyHole {
  return args;
}

export async function buildHermesIntegrationAudit(args: {
  env?: NodeJS.ProcessEnv;
  now?: () => string;
  outputPath?: string;
  hermesRoot?: string;
  hedgeRoot?: string;
  cashflowBoardPath?: string;
} = {}): Promise<HermesIntegrationAuditReport> {
  const env = args.env ?? process.env;
  const generatedAt = args.now?.() ?? new Date().toISOString();
  const outputPath = resolve(args.outputPath ?? env.BILL_HERMES_INTEGRATION_AUDIT_PATH ?? DEFAULT_OUTPUT_PATH);
  const hermesRoot = resolve(args.hermesRoot ?? env.BILL_HERMES_ROOT ?? "/Users/brain/hermes");
  const hedgeRoot = resolve(args.hedgeRoot ?? env.BILL_HERMES_SOURCE_HEDGE_ROOT ?? "/Users/brain/hedge");
  const cashflowBoardPath = resolve(args.cashflowBoardPath ?? env.BILL_CASHFLOW_BOARD_PATH ?? ".rumbling-hedge/state/cashflow-board.latest.json");
  const board = await readJsonSafe<CashflowBoardReport>(cashflowBoardPath);

  const hermesDashboard = await exists(resolve(hermesRoot, "full_brain_dashboard.py"));
  const hermesLoop = await exists(resolve(hermesRoot, "loop_manager.sh"));
  const hedgeSignalDecay = await exists(resolve(hedgeRoot, "scripts/signal_decay_monitor.py"));
  const hedgeCorrelation = await exists(resolve(hedgeRoot, "src/engine/strategyCorrelation.ts"));
  const hedgeRanking = await exists(resolve(hedgeRoot, "src/engine/multiFactorRanking.ts"));
  const hedgeRamGuard = await exists(resolve(hedgeRoot, "src/engine/ramGuard.ts"));
  const hedgeMarketCycle = await exists(resolve(hedgeRoot, "src/engine/marketCycle.ts"));

  const mergePlan: HermesIntegrationItem[] = [
    item({
      source: "hermes",
      path: resolve(hermesRoot, "full_brain_dashboard.py"),
      priority: hermesDashboard ? "merge-now" : "adapt-later",
      role: "single operator view across Bill, Hermes, launchd, resource pressure, and prediction cycle",
      combineAs: "dashboard consumer of cashflow-board, signal-decay-ledger, and hermes-integration-audit artifacts",
      reason: "Useful as observability. It should read fund state; it should not decide trades."
    }),
    item({
      source: "hermes",
      path: resolve(hermesRoot, "loop_manager.sh"),
      priority: hermesLoop ? "adapt-later" : "quarantine",
      role: "coarse cycle runner",
      combineAs: "replace with repo-native launchd wrappers that call explicit npm scripts in order",
      reason: "The loop uses broad retries and stale script paths. For live money, each step needs idempotent artifacts, locks, and fail-closed exit codes."
    }),
    item({
      source: "hedge",
      path: resolve(hedgeRoot, "scripts/signal_decay_monitor.py"),
      priority: hedgeSignalDecay ? "adapt-later" : "quarantine",
      role: "sidecar signal decay monitor",
      combineAs: "fold the useful rolling decay thresholds into signal-decay-ledger as first-class promotion gates",
      reason: "Decay belongs in the deterministic permission system, not as an optional Python sidecar."
    }),
    item({
      source: "hedge",
      path: resolve(hedgeRoot, "src/engine/strategyCorrelation.ts"),
      priority: hedgeCorrelation ? "merge-now" : "adapt-later",
      role: "correlated strategy exposure cap",
      combineAs: "capital allocator input before futures or prediction paper execution",
      reason: "Compounding fails when several strategies are secretly the same trade. Correlation caps reduce clustered drawdown."
    }),
    item({
      source: "hedge",
      path: resolve(hedgeRoot, "src/engine/multiFactorRanking.ts"),
      priority: hedgeRanking ? "adapt-later" : "quarantine",
      role: "ElasticNet/BMA strategy weight learner",
      combineAs: "research-only ranker until feature rows have clean forward outcome labels and PBO/deflated Sharpe controls",
      reason: "This can teach trader intuition, but it is overfit-prone until the outcome ledger is clean."
    }),
    item({
      source: "hedge",
      path: resolve(hedgeRoot, "src/engine/ramGuard.ts"),
      priority: hedgeRamGuard ? "merge-now" : "adapt-later",
      role: "compute pressure kill flag",
      combineAs: "hard no-go in cashflow-board and launchd wrappers before heavy research or model jobs",
      reason: "A fund cannot rely on models when the local machine is swapping, timing out, or corrupting cycles."
    }),
    item({
      source: "hedge",
      path: resolve(hedgeRoot, "src/engine/marketCycle.ts"),
      priority: hedgeMarketCycle ? "adapt-later" : "quarantine",
      role: "macro/market phase classifier",
      combineAs: "pre-open context feature, not standalone trade permission",
      reason: "The idea is useful, but phase labels need validation against forward PnL before they can route capital."
    })
  ];

  const liveMoneyHoles: LiveMoneyHole[] = [
    liveHole({
      severity: "critical",
      area: "prediction settlement",
      hole: "Prediction market candidates are not live-money credible without resolved outcome calibration, settlement mismatch tracking, and realized edge after fees.",
      requiredFix: "Run collect -> scan -> review -> paper execute -> resolve -> calibration continuously; promote only candidates with positive realized edge and no settlement mismatch pattern."
    }),
    liveHole({
      severity: "critical",
      area: "futures OOS evidence",
      hole: "The futures lane still has thin deployability evidence. A few favorable paper trades cannot justify prop-firm execution.",
      requiredFix: "Require rolling OOS depth, stressed live-readiness, and regime-conditioned paper/demo observations before challenge capital is exposed."
    }),
    liveHole({
      severity: "critical",
      area: "execution authority",
      hole: "Hermes/LLM workers can summarize and propose, but must never directly arm live execution or widen risk limits.",
      requiredFix: "Add policy-versioned approval records and a diff guard that rejects risk widening without explicit operator approval."
    }),
    liveHole({
      severity: "high",
      area: "capital allocator",
      hole: "There is not yet one canonical bankroll allocator across prediction markets, prop-firm challenges, research spend, compute, and locked future lanes.",
      requiredFix: "Implement a deterministic allocator with first-lane caps, drawdown cuts, payout reinvestment rules, and lane unlock thresholds."
    }),
    liveHole({
      severity: "high",
      area: "cost and liquidity",
      hole: "Prediction edges can vanish through fees, spread, fill probability, withdrawal friction, venue limits, and thin books.",
      requiredFix: "Attach liquidity/impact/slippage estimates to every prediction candidate and decay candidates whose displayed size or fill quality deteriorates."
    }),
    liveHole({
      severity: "high",
      area: "model hallucination",
      hole: "LLMs can hallucinate causal explanations, overstate edge, and rationalize recent lucky trades.",
      requiredFix: "Keep LLM outputs non-authoritative; require every claim to attach artifact paths, numerical support, and falsification criteria."
    }),
    liveHole({
      severity: "medium",
      area: "resource reliability",
      hole: "Hermes evidence shows disk/RAM pressure and stale boards can interrupt heavy research and model lanes.",
      requiredFix: "Use RAM guard, cold archive, lock files, and stale-artifact no-go checks before pre-open decisions."
    })
  ];

  const report: HermesIntegrationAuditReport = {
    command: "hermes-integration-audit",
    generatedAt,
    status: "blocked-for-live-money",
    paths: {
      outputPath,
      hermesRoot,
      hedgeRoot,
      cashflowBoardPath
    },
    observedArchitecture: {
      hermesRole: "watchdog, dashboard, launchd supervisor, cron/research worker, memory-system bridge",
      hedgeRole: "trading engine, prediction-market scanner, futures research/backtest engine, risk gate, execution adapter boundary",
      llmBoundary: "LLMs may observe, summarize, propose experiments, and flag contradictions; they do not size, route, promote, or override stops.",
      algoBoundary: "Algorithms own promotion, decay, sizing, execution permission, settlement calibration, kill switches, and lane unlocks."
    },
    mergePlan,
    rejectedPatterns: [
      "Do not merge the dirty hedge tree wholesale.",
      "Do not let Hermes cron prompts place trades, promote stages, widen risk, or spend money.",
      "Do not treat prediction-market implied odds as truth without settlement calibration.",
      "Do not treat prop-firm demo profitability as payout proof until funded constraints and payout receipts exist.",
      "Do not add dozens of strategies to live routing; first prove one or two leaves under strict context gates."
    ],
    liveMoneyHoles,
    firstLaneOperatingModel: [
      "Pre-open: refresh macro context, resource health, kill switch, prediction venue health, and cashflow board.",
      "Prediction markets: scan for cross-venue, resolution, and recurring exact-match edges; paper execute only when review and calibration pass.",
      "Futures prop firms: select one macro-conditioned policy leaf before the open; one contract, one trade/day, one loss hard stop.",
      "During session: algos monitor failure conditions; LLMs can comment but cannot override hard stops.",
      "Post-session: resolve prediction outcomes, mark fills, update OOS/paper evidence, decay losers, and write next-day board."
    ],
    predictionMarketsUse: [
      "Cashflow lane: small bounded paper/live-after-approval trades only after realized settlement edge is positive.",
      "Information lane: probability shifts become context features for futures, not direct futures orders.",
      "Decay lane: candidates lose status when edge, match score, venue health, fill quality, or settlement accuracy deteriorates."
    ],
    propFirmUse: [
      "Treat prop firms as a payout wedge, not as unlimited leverage.",
      "Trade the smallest challenge-compatible size until consistency proof exists.",
      "Stop the day after one loss or policy violation.",
      "Do not recycle challenge fees aggressively until paper/demo expectancy and rule compliance are boring."
    ],
    capitalUnlockRules: [
      "No new lane unlock until a first lane has 20+ observations, positive realized edge after costs, and no hard safety blockers.",
      "No compute spend increase until cashflow evidence pays for it or a founder explicitly funds research budget.",
      "No live futures until prop-demo evidence survives rolling OOS and the execution adapter is reviewed.",
      "No live prediction execution until paper fills and resolved outcomes show positive realized edge."
    ],
    nextImplementationOrder: [
      "Schedule the cashflow board sequence as the canonical 30-minute pre-open run.",
      "Import ramGuard and strategyCorrelation concepts into this branch as hard no-go and allocator inputs.",
      "Add prediction liquidity/impact scoring to the review and signal-decay-ledger.",
      "Add a policy diff guard for any risk-widening env or config change.",
      "Build the capital allocator that controls lane budgets, payout reinvestment, and unlocks."
    ],
    currentBoardStatus: board?.status ?? "missing"
  };

  await mkdir(dirname(outputPath), { recursive: true });
  await writeFile(outputPath, `${JSON.stringify(report, null, 2)}\n`, "utf8");
  return report;
}
