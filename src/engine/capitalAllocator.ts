import { mkdir, readFile, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import type { CashflowBoardReport } from "./cashflowBoard.js";

export interface LaneBudget {
  lane: string;
  status: "locked" | "research" | "paper";
  budget: number;
  currency: string;
  maxDailyLoss: number;
  maxSingleTradeRisk: number;
  reason: string;
}

export interface CapitalAllocatorReport {
  command: "capital-allocator";
  generatedAt: string;
  status: "blocked" | "research-budget-only" | "paper-budget-ready";
  bankroll: number;
  currency: string;
  paths: {
    outputPath: string;
    cashflowBoardPath: string;
  };
  laneBudgets: LaneBudget[];
  lockedSpend: Array<{
    category: string;
    reason: string;
  }>;
  compoundingRules: string[];
  blockers: string[];
}

const DEFAULT_OUTPUT_PATH = ".rumbling-hedge/state/capital-allocator.latest.json";

async function readJsonSafe<T>(path: string): Promise<T | null> {
  try {
    return JSON.parse(await readFile(resolve(path), "utf8")) as T;
  } catch {
    return null;
  }
}

function readNumber(env: NodeJS.ProcessEnv, key: string, fallback: number): number {
  const parsed = Number(env[key]);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function round(value: number): number {
  return Number(value.toFixed(2));
}

function laneBudget(args: {
  lane: string;
  status: LaneBudget["status"];
  bankroll: number;
  currency: string;
  budgetPct: number;
  maxDailyLossPct: number;
  maxTradeRiskPct: number;
  reason: string;
}): LaneBudget {
  const budget = args.status === "locked" ? 0 : args.bankroll * args.budgetPct;
  return {
    lane: args.lane,
    status: args.status,
    budget: round(budget),
    currency: args.currency,
    maxDailyLoss: round(args.bankroll * args.maxDailyLossPct),
    maxSingleTradeRisk: round(args.bankroll * args.maxTradeRiskPct),
    reason: args.reason
  };
}

export async function buildCapitalAllocator(args: {
  env?: NodeJS.ProcessEnv;
  now?: () => string;
  outputPath?: string;
  cashflowBoardPath?: string;
  cashflowBoard?: CashflowBoardReport;
} = {}): Promise<CapitalAllocatorReport> {
  const env = args.env ?? process.env;
  const generatedAt = args.now?.() ?? new Date().toISOString();
  const outputPath = resolve(args.outputPath ?? env.BILL_CAPITAL_ALLOCATOR_PATH ?? DEFAULT_OUTPUT_PATH);
  const cashflowBoardPath = resolve(args.cashflowBoardPath ?? env.BILL_CASHFLOW_BOARD_PATH ?? ".rumbling-hedge/state/cashflow-board.latest.json");
  const board = args.cashflowBoard ?? await readJsonSafe<CashflowBoardReport>(cashflowBoardPath);
  const bankroll = Math.max(0, readNumber(env, "BILL_FUND_BANKROLL", 100));
  const currency = env.BILL_FUND_CURRENCY ?? env.BILL_PREDICTION_BANKROLL_CURRENCY ?? "GBP";
  const blockers = [
    ...(!board ? ["missing cashflow board"] : []),
    ...(board?.hardNoGo ?? [])
  ];
  const activeFirstLane = board?.firstLanes.find((lane) => lane.status === "active");
  const paperReady = Boolean(board && board.status === "ready-for-paper-candidate" && activeFirstLane && blockers.length === 0);
  const researchOnly = Boolean(board && board.status === "shadow-build" && blockers.every((blocker) => blocker === "no active first-lane paper candidate"));

  const laneBudgets: LaneBudget[] = [
    laneBudget({
      lane: "prediction-markets",
      status: paperReady && activeFirstLane?.lane === "prediction-markets" ? "paper" : "research",
      bankroll,
      currency,
      budgetPct: paperReady && activeFirstLane?.lane === "prediction-markets" ? 0.05 : 0,
      maxDailyLossPct: paperReady && activeFirstLane?.lane === "prediction-markets" ? 0.01 : 0,
      maxTradeRiskPct: paperReady && activeFirstLane?.lane === "prediction-markets" ? 0.005 : 0,
      reason: paperReady && activeFirstLane?.lane === "prediction-markets"
        ? "Prediction lane is the active first-lane paper candidate."
        : "Prediction lane remains collect/calibrate until review and resolved outcomes prove edge."
    }),
    laneBudget({
      lane: "futures-prop",
      status: paperReady && activeFirstLane?.lane === "futures-prop" ? "paper" : "research",
      bankroll,
      currency,
      budgetPct: paperReady && activeFirstLane?.lane === "futures-prop" ? 0.1 : 0,
      maxDailyLossPct: paperReady && activeFirstLane?.lane === "futures-prop" ? 0.01 : 0,
      maxTradeRiskPct: paperReady && activeFirstLane?.lane === "futures-prop" ? 0.005 : 0,
      reason: paperReady && activeFirstLane?.lane === "futures-prop"
        ? "Futures prop lane is the active first-lane paper/demo candidate."
        : "Futures prop lane needs OOS/live-readiness depth before funded challenge exposure."
    }),
    laneBudget({
      lane: "options-us",
      status: "locked",
      bankroll,
      currency,
      budgetPct: 0,
      maxDailyLossPct: 0,
      maxTradeRiskPct: 0,
      reason: "Locked until first-lane realized cashflow evidence survives costs and drawdown."
    }),
    laneBudget({
      lane: "crypto-liquid",
      status: "locked",
      bankroll,
      currency,
      budgetPct: 0,
      maxDailyLossPct: 0,
      maxTradeRiskPct: 0,
      reason: "Locked until prediction and futures-prop lanes both show durable paper/demo cashflow."
    })
  ];

  const report: CapitalAllocatorReport = {
    command: "capital-allocator",
    generatedAt,
    status: paperReady ? "paper-budget-ready" : researchOnly ? "research-budget-only" : "blocked",
    bankroll: round(bankroll),
    currency,
    paths: {
      outputPath,
      cashflowBoardPath
    },
    laneBudgets,
    lockedSpend: [
      {
        category: "paid-data",
        reason: "No paid data until a first lane has settlement/OOS-supported realized edge or founder approves research spend."
      },
      {
        category: "larger-compute",
        reason: "No compute scale-up until cashflow evidence funds it or founder explicitly funds a research budget."
      },
      {
        category: "prop-challenge-fees",
        reason: "No new challenge fees until futures-prop evidence survives OOS, hard stops, and rule compliance."
      }
    ],
    compoundingRules: [
      "Withdraw/preserve first payouts before increasing size.",
      "Reinvest only from realized net cashflow, not paper PnL.",
      "Any lane drawdown beyond its max daily loss returns it to research.",
      "New lanes unlock only through the cashflow board and signal-decay ledger."
    ],
    blockers
  };

  await mkdir(dirname(outputPath), { recursive: true });
  await writeFile(outputPath, `${JSON.stringify(report, null, 2)}\n`, "utf8");
  return report;
}
