import { mkdir, readFile, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import type { PredictionCycleReview } from "../prediction/types.js";
import { readKillSwitch, type KillSwitchState } from "./killSwitch.js";
import type { MacroConditionedPolicyReport } from "./macroConditionedPolicy.js";
import { defaultRamGuardFlagPath, isMemoryPressureActive } from "./ramGuard.js";
import { evaluateRiskPolicyGuard } from "./riskPolicyGuard.js";
import { buildSignalDecayLedger, type SignalDecayLedgerReport } from "./signalDecayLedger.js";

export interface CashflowBoardReport {
  command: "cashflow-board";
  generatedAt: string;
  mode: "paper-first";
  status: "ready-for-paper-candidate" | "shadow-build" | "blocked";
  paths: {
    outputPath: string;
    ledgerPath: string;
    futuresPolicyPath: string;
    predictionReviewPath: string;
    killSwitchPath: string;
    ramGuardFlagPath: string;
  };
  killSwitch: KillSwitchState;
  firstLanes: Array<{
    lane: string;
    status: string;
    key: string;
    confidence: number;
    recommendedStage: string;
    nextAction: string;
    blockers: string[];
  }>;
  futures: {
    selected: MacroConditionedPolicyReport["selected"] | null;
    policyPatch: MacroConditionedPolicyReport["policyPatch"] | null;
    status: MacroConditionedPolicyReport["status"] | "missing";
  };
  prediction: {
    readyForPaper: boolean;
    topCandidate: PredictionCycleReview["topCandidate"] | null;
    blockers: string[];
    recommendation: string | null;
  };
  unlockPlan: SignalDecayLedgerReport["unlockPlan"];
  hardNoGo: string[];
  preOpenRunbook: string[];
  doctrine: string[];
}

const DEFAULT_OUTPUT_PATH = ".rumbling-hedge/state/cashflow-board.latest.json";

function isApprovedFuturesDemoTransport(env: NodeJS.ProcessEnv): boolean {
  return env.BILL_ENABLE_FUTURES_DEMO_EXECUTION === "true"
    && env.RH_TOPSTEP_DEMO_ONLY !== "false"
    && Boolean(env.BILL_FUTURES_DEMO_APPROVAL_ID?.trim());
}

async function readJsonSafe<T>(path: string): Promise<T | null> {
  try {
    return JSON.parse(await readFile(resolve(path), "utf8")) as T;
  } catch {
    return null;
  }
}

function boardStatus(args: {
  killSwitch: KillSwitchState;
  ledger: SignalDecayLedgerReport;
}): CashflowBoardReport["status"] {
  if (args.killSwitch.active) return "blocked";
  if (args.ledger.entries.some((entry) => entry.status === "active")) return "ready-for-paper-candidate";
  if (args.ledger.entries.some((entry) => entry.status === "shadow")) return "shadow-build";
  return "blocked";
}

export async function buildCashflowBoard(args: {
  env?: NodeJS.ProcessEnv;
  now?: () => string;
  outputPath?: string;
  ledgerOutputPath?: string;
  futuresPolicyPath?: string;
  predictionReviewPath?: string;
  killSwitchPath?: string;
  ramGuardFlagPath?: string;
} = {}): Promise<CashflowBoardReport> {
  const env = args.env ?? process.env;
  const generatedAt = args.now?.() ?? new Date().toISOString();
  const outputPath = resolve(args.outputPath ?? env.BILL_CASHFLOW_BOARD_PATH ?? DEFAULT_OUTPUT_PATH);
  const futuresPolicyPath = resolve(args.futuresPolicyPath ?? env.BILL_MACRO_CONDITIONED_POLICY_PATH ?? ".rumbling-hedge/state/macro-conditioned-policy.latest.json");
  const predictionReviewPath = resolve(args.predictionReviewPath ?? env.BILL_PREDICTION_REVIEW_PATH ?? ".rumbling-hedge/state/prediction-review.latest.json");
  const killSwitchPath = resolve(args.killSwitchPath ?? env.RH_KILL_SWITCH_PATH ?? ".rumbling-hedge/kill-switch.json");
  const ramGuardFlagPath = resolve(args.ramGuardFlagPath ?? defaultRamGuardFlagPath(env));
  const ledger = await buildSignalDecayLedger({
    env,
    now: () => generatedAt,
    outputPath: args.ledgerOutputPath
  });
  const [futuresPolicy, predictionReview, killSwitch, memoryPressureActive] = await Promise.all([
    readJsonSafe<MacroConditionedPolicyReport>(futuresPolicyPath),
    readJsonSafe<PredictionCycleReview>(predictionReviewPath),
    readKillSwitch(killSwitchPath),
    isMemoryPressureActive(ramGuardFlagPath)
  ]);
  const riskPolicy = evaluateRiskPolicyGuard({ env, now: () => generatedAt });
  const approvedFuturesDemoTransport = isApprovedFuturesDemoTransport(env);
  const hardNoGo = [
    ...(killSwitch.active ? [`kill switch active: ${killSwitch.reason ?? "no reason"}`] : []),
    ...(memoryPressureActive ? [`memory pressure flag active: ${ramGuardFlagPath}`] : []),
    ...riskPolicy.blockers,
    ...(env.RH_LIVE_EXECUTION_ENABLED === "true" && !approvedFuturesDemoTransport ? ["futures live execution is armed"] : []),
    ...(env.BILL_PREDICTION_EXECUTION_MODE === "live" || env.BILL_PREDICTION_LIVE_EXECUTION_ENABLED === "true" ? ["prediction live execution is armed"] : []),
    ...(ledger.entries.every((entry) => entry.status !== "active") ? ["no active first-lane paper candidate"] : [])
  ];

  const report: CashflowBoardReport = {
    command: "cashflow-board",
    generatedAt,
    mode: "paper-first",
    status: hardNoGo.length > 0 ? (ledger.status === "shadow-build" && !killSwitch.active ? "shadow-build" : "blocked") : boardStatus({ killSwitch, ledger }),
    paths: {
      outputPath,
      ledgerPath: ledger.paths.outputPath,
      futuresPolicyPath,
      predictionReviewPath,
      killSwitchPath,
      ramGuardFlagPath
    },
    killSwitch,
    firstLanes: ledger.entries.map((entry) => ({
      lane: entry.lane,
      status: entry.status,
      key: entry.key,
      confidence: entry.confidence,
      recommendedStage: entry.recommendedStage,
      nextAction: entry.nextAction,
      blockers: entry.blockers
    })),
    futures: {
      selected: futuresPolicy?.selected ?? null,
      policyPatch: futuresPolicy?.policyPatch ?? null,
      status: futuresPolicy?.status ?? "missing"
    },
    prediction: {
      readyForPaper: predictionReview?.readyForPaper ?? false,
      topCandidate: predictionReview?.topCandidate ?? null,
      blockers: predictionReview?.blockers ?? ["missing prediction review"],
      recommendation: predictionReview?.recommendation ?? null
    },
    unlockPlan: ledger.unlockPlan,
    hardNoGo,
    preOpenRunbook: [
      "Refresh macro-context-free.",
      "Run prediction collect -> scan -> review -> resolve/calibration if eligible markets have settled.",
      "Run macro-conditioned-policy.",
      "Run signal-decay-ledger and this cashflow board.",
      "If status is ready-for-paper-candidate, route only the active first-lane paper candidate under its hard limits.",
      "If status is shadow-build or blocked, collect and observe only."
    ],
    doctrine: [
      "Start path is prediction markets plus futures prop firms.",
      "Prediction markets can be both a cashflow lane and an information/context lane for futures.",
      "LLMs are the analyst/observer layer; deterministic algorithms own trade permission, promotion, decay, sizing, and stops.",
      "New lanes unlock only after first-lane cashflow evidence survives costs, settlement, and drawdown controls."
    ]
  };

  await mkdir(dirname(outputPath), { recursive: true });
  await writeFile(outputPath, `${JSON.stringify(report, null, 2)}\n`, "utf8");
  return report;
}
