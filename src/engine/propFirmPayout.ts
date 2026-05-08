import { mkdir, readFile, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import type { StrategyCandidate } from "./expectedValueSurface.js";

export interface TopstepAccountParameters {
  accountSize: "50K";
  combineProfitTarget: number;
  combineBestDayRecommendation: number;
  dailyLossLimit: number;
  maximumLossLimit: number;
  maxContracts: number;
  maxMicros: number;
  xfaStandardWinningDays: number;
  xfaStandardMinWinningDay: number;
  xfaConsistencyTradingDays: number;
  xfaConsistencyMaxLargestDayPct: number;
}

export interface PropFirmCandidateScore {
  symbol: string;
  strategyId: string;
  score: number;
  laneRole: "payout-builder" | "evidence-build" | "reject";
  maxDailyTargetDollars: number;
  maxDailyLossDollars: number;
  maxContracts: number;
  reasons: string[];
  blockers: string[];
}

export interface PropFirmPayoutPlan {
  command: "prop-firm-payout-plan";
  generatedAt: string;
  account: TopstepAccountParameters;
  posture: "ready-to-demo" | "needs-evidence";
  candidateCount: number;
  topCandidates: PropFirmCandidateScore[];
  blockers: string[];
  operatingRules: string[];
}

export const TOPSTEP_50K_PARAMETERS: TopstepAccountParameters = {
  accountSize: "50K",
  combineProfitTarget: 3000,
  combineBestDayRecommendation: 1500,
  dailyLossLimit: 1000,
  maximumLossLimit: 2000,
  maxContracts: 5,
  maxMicros: 50,
  xfaStandardWinningDays: 5,
  xfaStandardMinWinningDay: 150,
  xfaConsistencyTradingDays: 3,
  xfaConsistencyMaxLargestDayPct: 0.4
};

function clamp01(value: number): number {
  return Math.max(0, Math.min(1, value));
}

export function scorePropFirmCandidate(candidate: StrategyCandidate): PropFirmCandidateScore {
  const support = clamp01(candidate.strategyTrades / 20);
  const positiveExpectancy = clamp01(candidate.strategyAverageR / 0.35);
  const ev = clamp01((candidate.expectedValueScore + 0.15) / 0.75);
  const resilience = clamp01(candidate.resilienceScore);
  const confidence = clamp01(candidate.regimeConfidence);
  const convexityPenalty = Math.max(0, candidate.convexityScore - 0.72) * 0.18;
  const sparsePenalty = candidate.strategyTrades < 8 ? 0.22 : candidate.strategyTrades < 15 ? 0.1 : 0;
  const negativePenalty = candidate.strategyAverageR <= 0 ? 0.28 : 0;
  const score = Number(clamp01(
    support * 0.22
    + positiveExpectancy * 0.24
    + ev * 0.18
    + resilience * 0.24
    + confidence * 0.12
    - convexityPenalty
    - sparsePenalty
    - negativePenalty
  ).toFixed(4));
  const blockers = [
    ...(candidate.strategyAverageR <= 0 ? ["non-positive-strategy-expectancy"] : []),
    ...(candidate.strategyTrades < 8 ? ["thin-trade-sample"] : []),
    ...(candidate.resilienceScore < 0.45 ? ["low-resilience"] : []),
    ...(candidate.directionalBias === "flat" ? ["flat-directional-bias"] : [])
  ];
  const laneRole = blockers.length === 0 && score >= 0.62
    ? "payout-builder"
    : blockers.length <= 1 && score >= 0.45
      ? "evidence-build"
      : "reject";
  const targetBase = TOPSTEP_50K_PARAMETERS.xfaStandardMinWinningDay;
  const maxDailyTargetDollars = laneRole === "payout-builder"
    ? Math.min(650, Math.max(targetBase, TOPSTEP_50K_PARAMETERS.combineBestDayRecommendation * 0.35))
    : Math.min(300, Math.max(targetBase, TOPSTEP_50K_PARAMETERS.combineBestDayRecommendation * 0.18));
  const maxDailyLossDollars = laneRole === "payout-builder" ? 350 : 200;

  return {
    symbol: candidate.symbol,
    strategyId: candidate.strategyId,
    score,
    laneRole,
    maxDailyTargetDollars: Number(maxDailyTargetDollars.toFixed(2)),
    maxDailyLossDollars,
    maxContracts: 1,
    reasons: [
      `expectancy=${candidate.strategyAverageR.toFixed(4)}R`,
      `trades=${candidate.strategyTrades}`,
      `resilience=${candidate.resilienceScore.toFixed(2)}`,
      `regimeConfidence=${candidate.regimeConfidence.toFixed(2)}`,
      "scored for Topstep payout consistency, not max gross PnL"
    ],
    blockers
  };
}

async function readJsonSafe<T>(path: string): Promise<T | null> {
  try {
    return JSON.parse(await readFile(path, "utf8")) as T;
  } catch {
    return null;
  }
}

export async function buildPropFirmPayoutPlan(args: {
  candidates?: StrategyCandidate[];
  candidatePath?: string;
  outputPath?: string;
  now?: () => string;
} = {}): Promise<PropFirmPayoutPlan> {
  const rawCandidates = args.candidates
    ?? (args.candidatePath ? await readJsonSafe<{ candidates?: StrategyCandidate[] }>(resolve(args.candidatePath)) : null)?.candidates
    ?? [];
  const topCandidates = rawCandidates
    .map(scorePropFirmCandidate)
    .sort((left, right) => right.score - left.score)
    .slice(0, 20);
  const payoutBuilders = topCandidates.filter((candidate) => candidate.laneRole === "payout-builder");
  const blockers = [
    ...(rawCandidates.length > 0 ? [] : ["no-strategy-candidates-provided"]),
    ...(payoutBuilders.length > 0 ? [] : ["no-payout-builder-candidate"])
  ];
  const plan: PropFirmPayoutPlan = {
    command: "prop-firm-payout-plan",
    generatedAt: args.now?.() ?? new Date().toISOString(),
    account: TOPSTEP_50K_PARAMETERS,
    posture: blockers.length === 0 ? "ready-to-demo" : "needs-evidence",
    candidateCount: rawCandidates.length,
    topCandidates,
    blockers,
    operatingRules: [
      "One contract per 50K demo account until payout-builder evidence is durable.",
      "Daily target stays below $650 and always below the $1,500 50K combine best-day recommendation.",
      "Daily loss stop stays at or below $350, well inside the $1,000 50K daily loss limit.",
      "XFA Standard target is five $150+ winning days; XFA Consistency target is three trading days with largest day <=40% of payout-window net profit.",
      "Stop trading the account for the day after target, daily stop, two losses, or any platform risk lock."
    ]
  };

  if (args.outputPath) {
    const outputPath = resolve(args.outputPath);
    await mkdir(dirname(outputPath), { recursive: true });
    await writeFile(outputPath, `${JSON.stringify(plan, null, 2)}\n`, "utf8");
  }
  return plan;
}
