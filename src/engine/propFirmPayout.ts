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
  xfaStandardMaxPayoutCap: number;
  xfaConsistencyTradingDays: number;
  xfaConsistencyMaxLargestDayPct: number;
  xfaConsistencyMaxPayoutCap: number;
  traderProfitSplitPct: number;
}

export interface PropFirmChallengePath {
  objective: "build-evidence" | "pass-combine";
  fastestResponsibleWindowDays: [number, number];
  preferredFundedPath: "xfa-consistency";
  dailyNetTargetRange: [number, number];
  dailyHardLossStop: number;
  tradePlan: string[];
  promotionGate: string[];
}

export interface PropFirmNqTradeMath {
  symbol: "NQ" | "MNQ";
  tickSizePoints: number;
  tickValueDollars: number;
  targetTicks: number;
  stopTicks: number;
  runnerTrailTicks: number;
  contracts: number;
  maxTradesPerDay: number;
  grossWinPerTrade: number;
  grossLossPerTrade: number;
  maxGrossDailyWin: number;
  maxGrossDailyLoss: number;
  rr: number;
}

export interface PropFirmRiskMode {
  phase: "challenge" | "funded";
  posture: "aggressive-controlled" | "payout-defense";
  allowedSymbols: ["NQ"];
  executionInstrument: "NQ" | "MNQ";
  maxTradesPerDay: number;
  tradeMath: PropFirmNqTradeMath;
  dailyProfitLock: number;
  dailyLossLock: number;
  rationale: string[];
  automationPrerequisites: string[];
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
  challengePath: PropFirmChallengePath;
  riskModes: {
    challenge: PropFirmRiskMode;
    funded: PropFirmRiskMode;
  };
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
  xfaStandardMaxPayoutCap: 5000,
  xfaConsistencyTradingDays: 3,
  xfaConsistencyMaxLargestDayPct: 0.4,
  xfaConsistencyMaxPayoutCap: 6000,
  traderProfitSplitPct: 0.9
};

function buildNqTradeMath(args: {
  symbol: "NQ" | "MNQ";
  targetTicks: number;
  stopTicks: number;
  runnerTrailTicks: number;
  contracts: number;
  maxTradesPerDay: number;
}): PropFirmNqTradeMath {
  const tickValueDollars = args.symbol === "NQ" ? 5 : 0.5;
  const grossWinPerTrade = args.targetTicks * tickValueDollars * args.contracts;
  const grossLossPerTrade = args.stopTicks * tickValueDollars * args.contracts;
  return {
    symbol: args.symbol,
    tickSizePoints: 0.25,
    tickValueDollars,
    targetTicks: args.targetTicks,
    stopTicks: args.stopTicks,
    runnerTrailTicks: args.runnerTrailTicks,
    contracts: args.contracts,
    maxTradesPerDay: args.maxTradesPerDay,
    grossWinPerTrade,
    grossLossPerTrade,
    maxGrossDailyWin: grossWinPerTrade * args.maxTradesPerDay,
    maxGrossDailyLoss: grossLossPerTrade * args.maxTradesPerDay,
    rr: Number((grossWinPerTrade / grossLossPerTrade).toFixed(2))
  };
}

export const TOPSTEP_NQ_RISK_MODES: PropFirmPayoutPlan["riskModes"] = {
  challenge: {
    phase: "challenge",
    posture: "aggressive-controlled",
    allowedSymbols: ["NQ"],
    executionInstrument: "NQ",
    maxTradesPerDay: 3,
    tradeMath: buildNqTradeMath({
      symbol: "NQ",
      targetTicks: 80,
      stopTicks: 28,
      runnerTrailTicks: 20,
      contracts: 1,
      maxTradesPerDay: 3
    }),
    dailyProfitLock: 1_200,
    dailyLossLock: 450,
    rationale: [
      "NQ gives enough intraday range to seek 20-point captures without needing many trades.",
      "One NQ contract keeps a 20-point target around $400 gross, so three clean wins can build a fast combine day while staying below the $1,500 50K best-day recommendation.",
      "A 7-point initial stop keeps one full-size miss near $140 gross before fees; the day stops before loss recovery behavior starts."
    ],
    automationPrerequisites: [
      "Realtime bracket orders with server-side stop and target.",
      "Personal daily profit target must liquidate and block near the configured daily profit lock.",
      "Max-three-trades state machine with no manual override unless the kill switch is active.",
      "News and volatility lockouts around scheduled high-impact releases."
    ]
  },
  funded: {
    phase: "funded",
    posture: "payout-defense",
    allowedSymbols: ["NQ"],
    executionInstrument: "MNQ",
    maxTradesPerDay: 3,
    tradeMath: buildNqTradeMath({
      symbol: "MNQ",
      targetTicks: 80,
      stopTicks: 24,
      runnerTrailTicks: 20,
      contracts: 3,
      maxTradesPerDay: 3
    }),
    dailyProfitLock: 300,
    dailyLossLock: 180,
    rationale: [
      "Funded accounts optimize for payout eligibility and review survival, not fastest gross PnL.",
      "MNQ keeps the same NQ signal geometry while reducing single-trade dollar variance.",
      "Daily profit locks are sized to accumulate payout days without creating a large-day consistency problem."
    ],
    automationPrerequisites: [
      "Funded mode cannot reuse challenge sizing.",
      "The bot must stop after target, daily lock, two losses, or any scaling-plan conflict.",
      "Every funded entry needs a journaled setup tag, entry reason, initial risk, exit reason, and screenshot/reference id.",
      "Payout-window consistency metrics must be recomputed before every new order."
    ]
  }
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
      "Challenge mode may use one NQ contract only when the setup, bracket order, and daily lock are all active.",
      "Challenge daily profit lock stays near $1,200 and always below the $1,500 50K combine best-day recommendation.",
      "Funded/default daily target stays below $650; funded payout-defense mode starts near $300.",
      "Challenge daily loss lock stays near $450; funded payout-defense daily loss lock starts near $180.",
      "XFA Standard target is five $150+ winning days; XFA Consistency target is three trading days with largest day <=40% of payout-window net profit.",
      "Stop trading the account for the day after target, daily stop, two losses, or any platform risk lock."
    ],
    challengePath: {
      objective: blockers.length === 0 ? "pass-combine" : "build-evidence",
      fastestResponsibleWindowDays: [6, 12],
      preferredFundedPath: "xfa-consistency",
      dailyNetTargetRange: [350, 650],
      dailyHardLossStop: 350,
      tradePlan: [
        "Use one payout-builder lane per 50K account; keep micros/contracts fixed through the challenge window.",
        "Aim for four to seven controlled green sessions instead of a one-day pass; a best day above 50% of target makes the pass and payout path harder.",
        "After funding, choose XFA Consistency only when Bill can keep the largest payout-window day <=40% of net profit; otherwise use Standard and collect five $150+ days.",
        "Treat the first funded payout as capital preservation, not a sizing unlock."
      ],
      promotionGate: [
        "At least one current payout-builder with positive expectancy, >=20 trades, resilience >=0.45, and no flat bias.",
        "No daily loss breach, platform risk lock, or synthetic fallback signal in the last 10 sampled sessions.",
        "A replayable journal exists for every entry, exit, skipped trade, and stop-after-target decision."
      ]
    },
    riskModes: TOPSTEP_NQ_RISK_MODES
  };

  if (args.outputPath) {
    const outputPath = resolve(args.outputPath);
    await mkdir(dirname(outputPath), { recursive: true });
    await writeFile(outputPath, `${JSON.stringify(plan, null, 2)}\n`, "utf8");
  }
  return plan;
}
