import { appendFile, mkdir, readFile, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import type { BillPromotionStage, PredictionCycleReview, PredictionTrainingState } from "../prediction/types.js";
import type { PaperFill } from "../prediction/execution/types.js";
import { buildCalibrationReportFromJsonl, type CalibrationReport } from "../prediction/resolver.js";
import type { MacroConditionedPolicyReport } from "./macroConditionedPolicy.js";
import type { StrategyFactoryReport } from "./strategyFactory.js";

export type CashflowLane = "prediction-markets" | "futures-prop" | "options-us" | "crypto-liquid";
export type SignalDecayStatus = "active" | "shadow" | "decaying" | "disabled";

export interface SignalDecayLedgerEntry {
  lane: CashflowLane;
  key: string;
  status: SignalDecayStatus;
  recommendedStage: BillPromotionStage;
  confidence: number;
  score: number;
  evidence: {
    observations: number;
    paperSignals: number;
    paperFills: number;
    netR?: number;
    averageR?: number;
    topEdgePct?: number;
    matchScore?: number;
    resolvedOutcomes?: number;
    hitRatePct?: number;
    meanRealizedEdgePct?: number;
    settlementMismatches?: number;
    riskOfRuinProb?: number;
    maxConsecutiveLosses?: number;
  };
  blockers: string[];
  nextAction: string;
  hardLimits: string[];
  llmRole: "observer-only";
}

export interface SignalDecayLedgerReport {
  command: "signal-decay-ledger";
  generatedAt: string;
  status: "cashflow-candidate" | "shadow-build" | "blocked";
  paths: {
    outputPath: string;
    historyPath: string;
    futuresPolicyPath: string;
    strategyFactoryPath: string;
    predictionReviewPath: string;
    predictionTrainingPath: string;
    predictionFillsPath: string;
    predictionResolvedPath: string;
  };
  entries: SignalDecayLedgerEntry[];
  firstCashflowLanes: CashflowLane[];
  unlockPlan: Array<{
    lane: CashflowLane;
    status: "locked" | "eligible-next";
    unlockCondition: string;
  }>;
  blockers: string[];
  operatingDoctrine: string[];
}

const DEFAULT_OUTPUT_PATH = ".rumbling-hedge/state/signal-decay-ledger.latest.json";
const DEFAULT_HISTORY_PATH = ".rumbling-hedge/logs/signal-decay-ledger-history.jsonl";

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

async function readJsonlSafe<T>(path: string): Promise<T[]> {
  try {
    return (await readFile(resolve(path), "utf8"))
      .split(/\r?\n/)
      .map((line) => line.trim())
      .filter(Boolean)
      .map((line) => JSON.parse(line) as T);
  } catch {
    return [];
  }
}

function clamp01(value: number): number {
  return Math.max(0, Math.min(1, value));
}

function round(value: number): number {
  return Number(value.toFixed(4));
}

function statusFromScore(args: {
  score: number;
  blockers: string[];
  observations: number;
  minObservations: number;
  liveArmed: boolean;
}): SignalDecayStatus {
  if (args.liveArmed || args.blockers.some((blocker) => /unsafe|live.*armed|negative|ruin|disabled/i.test(blocker))) {
    return "disabled";
  }
  if (args.score < 0.15 || args.blockers.some((blocker) => /worsening|decay|loss/i.test(blocker))) {
    return "decaying";
  }
  if (args.observations < args.minObservations || args.score < 0.55 || args.blockers.length > 0) {
    return "shadow";
  }
  return "active";
}

function stageFromStatus(status: SignalDecayStatus): BillPromotionStage {
  if (status === "active") return "paper";
  if (status === "shadow") return "research";
  return "research";
}

function buildFuturesEntry(args: {
  policy: MacroConditionedPolicyReport | null;
  strategyFactory: StrategyFactoryReport | null;
  env: NodeJS.ProcessEnv;
}): SignalDecayLedgerEntry {
  const selected = args.policy?.selected ?? null;
  const key = selected ? `${selected.symbol}:${selected.strategyId}` : "futures-prop:none";
  const unsafeFuturesLiveArmed = args.env.RH_LIVE_EXECUTION_ENABLED === "true" && !isApprovedFuturesDemoTransport(args.env);
  const blockers = [
    ...(args.policy?.blockers ?? []),
    ...(args.strategyFactory?.blockers ?? []).slice(0, 3),
    ...(!selected ? ["no macro-conditioned futures candidate"] : []),
    ...(selected && selected.averageR <= 0 ? ["negative futures expectancy"] : []),
    ...(selected && selected.maxConsecutiveLosses > 1 ? ["futures losing streak exceeds hard starter limit"] : []),
    ...(unsafeFuturesLiveArmed ? ["unsafe futures live execution armed"] : [])
  ];
  const observations = selected?.trades ?? 0;
  const score = selected ? clamp01((selected.score + 0.2) / 1.1) : 0;
  const status = statusFromScore({
    score,
    blockers,
    observations,
    minObservations: 8,
    liveArmed: unsafeFuturesLiveArmed
  });

  return {
    lane: "futures-prop",
    key,
    status,
    recommendedStage: stageFromStatus(status),
    confidence: round(score),
    score: selected?.score ?? 0,
    evidence: {
      observations,
      paperSignals: observations,
      paperFills: 0,
      netR: selected?.netTotalR,
      averageR: selected?.averageR,
      riskOfRuinProb: selected?.riskOfRuinProb,
      maxConsecutiveLosses: selected?.maxConsecutiveLosses
    },
    blockers,
    nextAction: status === "active"
      ? "Run this as the single pre-open paper/demo futures policy; keep one loss as the hard stop."
      : status === "shadow"
        ? "Keep collecting macro-conditioned paper evidence until trade count and OOS depth improve."
        : "Disable this futures leaf until the next macro-conditioned policy run repairs expectancy and tail behavior.",
    hardLimits: [
      "1 contract max",
      "1 trade/day starter cap",
      "1R daily hard stop",
      "1 loss stops the session",
      "no live futures without OOS deployability and operator approval"
    ],
    llmRole: "observer-only"
  };
}

function buildPredictionEntry(args: {
  review: PredictionCycleReview | null;
  training: PredictionTrainingState | null;
  fills: PaperFill[];
  calibration: CalibrationReport | null;
  env: NodeJS.ProcessEnv;
}): SignalDecayLedgerEntry {
  const top = args.review?.topCandidate ?? null;
  const key = top?.candidateId ?? "prediction-markets:none";
  const realFills = args.fills.filter((fill) => !fill.demo);
  const fillsForTop = top ? realFills.filter((fill) => fill.candidateId === top.candidateId) : [];
  const history = top?.history ?? null;
  const observations = history?.observations ?? (top ? 1 : 0);
  const paperSignals = history?.paperCycles ?? (top?.verdict === "paper-trade" ? 1 : 0);
  const topEdgePct = top?.netEdgePct ?? args.training?.selectedEvaluation.topPaperEdgePct ?? 0;
  const matchScore = top?.matchScore ?? args.training?.selectedEvaluation.avgPaperMatchScore ?? 0;
  const edgeScore = clamp01(topEdgePct / 6);
  const matchComponent = clamp01((matchScore - 0.65) / 0.3);
  const recurrence = clamp01(observations / 8);
  const fillSupport = clamp01(fillsForTop.length / 3);
  const resolvedOutcomes = args.calibration?.totalResolved ?? 0;
  const calibrationSupport = clamp01(resolvedOutcomes / 20);
  const meanRealizedEdgePct = args.calibration?.meanRealizedEdgePct ?? 0;
  const realizedEdgeComponent = resolvedOutcomes > 0 ? clamp01((meanRealizedEdgePct + 1) / 5) : 0;
  const mismatchPenalty = resolvedOutcomes > 0
    ? clamp01((args.calibration?.settlementMismatches ?? 0) / Math.max(1, resolvedOutcomes)) * 0.25
    : 0;
  const worseningPenalty = history?.trend === "worsening" ? 0.25 : 0;
  const score = round(
    (edgeScore * 0.26) +
    (matchComponent * 0.2) +
    (recurrence * 0.16) +
    (fillSupport * 0.14) +
    (calibrationSupport * 0.12) +
    (realizedEdgeComponent * 0.12) -
    worseningPenalty -
    mismatchPenalty
  );
  const blockers = [
    ...(args.review?.blockers ?? []),
    ...(!top ? ["no prediction top candidate"] : []),
    ...(top && top.verdict !== "paper-trade" ? ["lead prediction candidate is not paper-trade"] : []),
    ...(history?.trend === "worsening" ? ["prediction edge shortfall is worsening"] : []),
    ...(resolvedOutcomes === 0 ? ["no resolved prediction outcomes for calibration"] : []),
    ...(resolvedOutcomes > 0 && meanRealizedEdgePct <= 0 ? ["prediction resolved edge is not positive"] : []),
    ...((args.calibration?.settlementMismatches ?? 0) > 0 ? ["prediction settlement mismatches observed"] : []),
    ...(args.env.BILL_PREDICTION_EXECUTION_MODE === "live" || args.env.BILL_PREDICTION_LIVE_EXECUTION_ENABLED === "true"
      ? ["unsafe prediction live execution armed"]
      : [])
  ];
  const status = statusFromScore({
    score,
    blockers,
    observations,
    minObservations: 3,
    liveArmed: args.env.BILL_PREDICTION_EXECUTION_MODE === "live" || args.env.BILL_PREDICTION_LIVE_EXECUTION_ENABLED === "true"
  });

  return {
    lane: "prediction-markets",
    key,
    status,
    recommendedStage: stageFromStatus(status),
    confidence: score,
    score,
    evidence: {
      observations,
      paperSignals,
      paperFills: fillsForTop.length,
      topEdgePct,
      matchScore,
      resolvedOutcomes,
      hitRatePct: args.calibration?.hitRatePct ?? 0,
      meanRealizedEdgePct,
      settlementMismatches: args.calibration?.settlementMismatches ?? 0
    },
    blockers,
    nextAction: status === "active"
      ? "Allow bounded paper execution for recurring exact-match candidates; keep live disabled until settlement review proves realized edge."
      : status === "shadow"
        ? "Keep scanning and paper-reviewing; use candidate recurrence and fills to prove the edge is not a one-off."
        : "Keep prediction markets in collect/watch mode until normalization, venue health, and economic edge repair.",
    hardLimits: [
      "paper mode first",
      "no live prediction execution without settlement-calibrated paper fills",
      "stake and max-loss caps remain mechanical",
      "thin liquidity candidates stay watch-only",
      "LLM narratives cannot override contract matching"
    ],
    llmRole: "observer-only"
  };
}

export async function buildSignalDecayLedger(args: {
  env?: NodeJS.ProcessEnv;
  now?: () => string;
  outputPath?: string;
  historyPath?: string;
  futuresPolicyPath?: string;
  strategyFactoryPath?: string;
  predictionReviewPath?: string;
  predictionTrainingPath?: string;
  predictionFillsPath?: string;
  predictionResolvedPath?: string;
} = {}): Promise<SignalDecayLedgerReport> {
  const env = args.env ?? process.env;
  const generatedAt = args.now?.() ?? new Date().toISOString();
  const outputPath = resolve(args.outputPath ?? env.BILL_SIGNAL_DECAY_LEDGER_PATH ?? DEFAULT_OUTPUT_PATH);
  const historyPath = resolve(args.historyPath ?? env.BILL_SIGNAL_DECAY_LEDGER_HISTORY_PATH ?? DEFAULT_HISTORY_PATH);
  const futuresPolicyPath = resolve(args.futuresPolicyPath ?? env.BILL_MACRO_CONDITIONED_POLICY_PATH ?? ".rumbling-hedge/state/macro-conditioned-policy.latest.json");
  const strategyFactoryPath = resolve(args.strategyFactoryPath ?? env.BILL_STRATEGY_FACTORY_OUTPUT_PATH ?? ".rumbling-hedge/state/strategy-factory.latest.json");
  const predictionReviewPath = resolve(args.predictionReviewPath ?? env.BILL_PREDICTION_REVIEW_PATH ?? ".rumbling-hedge/state/prediction-review.latest.json");
  const predictionTrainingPath = resolve(args.predictionTrainingPath ?? env.BILL_PREDICTION_LEARNING_STATE_PATH ?? ".rumbling-hedge/state/prediction-learning.latest.json");
  const predictionFillsPath = resolve(args.predictionFillsPath ?? env.BILL_PREDICTION_FILLS_JOURNAL_PATH ?? ".rumbling-hedge/runtime/prediction/fills.jsonl");
  const predictionResolvedPath = resolve(args.predictionResolvedPath ?? env.BILL_PREDICTION_RESOLVED_PATH ?? ".rumbling-hedge/runtime/prediction/resolved.jsonl");

  const [policy, strategyFactory, review, training, fills, calibration] = await Promise.all([
    readJsonSafe<MacroConditionedPolicyReport>(futuresPolicyPath),
    readJsonSafe<StrategyFactoryReport>(strategyFactoryPath),
    readJsonSafe<PredictionCycleReview>(predictionReviewPath),
    readJsonSafe<PredictionTrainingState>(predictionTrainingPath),
    readJsonlSafe<PaperFill>(predictionFillsPath),
    buildCalibrationReportFromJsonl(predictionResolvedPath).catch(() => null)
  ]);

  const entries = [
    buildPredictionEntry({ review, training, fills, calibration, env }),
    buildFuturesEntry({ policy, strategyFactory, env })
  ].sort((left, right) =>
    (right.status === "active" ? 1 : 0) - (left.status === "active" ? 1 : 0)
    || right.confidence - left.confidence
  );
  const activeFirstLanes = entries.filter((entry) => entry.status === "active");
  const blockers = [
    ...(policy ? [] : ["missing futures macro-conditioned policy report"]),
    ...(review ? [] : ["missing prediction review report"]),
    ...(entries.every((entry) => entry.status !== "active") ? ["no first cashflow lane is active"] : [])
  ];

  const report: SignalDecayLedgerReport = {
    command: "signal-decay-ledger",
    generatedAt,
    status: activeFirstLanes.length > 0
      ? "cashflow-candidate"
      : entries.some((entry) => entry.status === "shadow")
        ? "shadow-build"
        : "blocked",
    paths: {
      outputPath,
      historyPath,
      futuresPolicyPath,
      strategyFactoryPath,
      predictionReviewPath,
      predictionTrainingPath,
      predictionFillsPath,
      predictionResolvedPath
    },
    entries,
    firstCashflowLanes: ["prediction-markets", "futures-prop"],
    unlockPlan: [
      {
        lane: "options-us",
        status: activeFirstLanes.length >= 1 ? "eligible-next" : "locked",
        unlockCondition: "At least one first cashflow lane has 20+ paper/demo observations, positive realized expectancy after costs, and no live safety blockers."
      },
      {
        lane: "crypto-liquid",
        status: activeFirstLanes.length >= 2 ? "eligible-next" : "locked",
        unlockCondition: "Prediction and futures-prop lanes both show durable paper/demo cashflow; crypto starts as data/paper only with funding/OI context."
      }
    ],
    blockers,
    operatingDoctrine: [
      "Prediction markets and futures prop firms are the first cashflow lanes.",
      "LLMs observe, summarize, critique, and propose experiments; deterministic algorithms own promotion, sizing, risk, and execution permission.",
      "A lane can decay or disable automatically, but live promotion remains approval-gated.",
      "Cashflow unlocks new lanes only after the first lanes prove durable paper/demo edge after costs and hard stops."
    ]
  };

  await mkdir(dirname(outputPath), { recursive: true });
  await mkdir(dirname(historyPath), { recursive: true });
  await writeFile(outputPath, `${JSON.stringify(report, null, 2)}\n`, "utf8");
  await appendFile(historyPath, `${JSON.stringify(report)}\n`, "utf8");
  return report;
}
