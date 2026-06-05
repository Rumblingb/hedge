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
  preferredFundedPath: "xfa-standard" | "xfa-consistency";
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
  activationStatus: "proposal-only-until-risk-policy-clears";
  activePolicyRule: string;
  allowedSymbols: Array<"NQ" | "MNQ">;
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

export function hasCurrentTopstep50KPolicy(plan: unknown): boolean {
  const candidate = plan as Partial<PropFirmPayoutPlan> | null | undefined;
  return candidate?.command === "prop-firm-payout-plan"
    && candidate.account?.xfaStandardMaxPayoutCap === TOPSTEP_50K_PARAMETERS.xfaStandardMaxPayoutCap
    && candidate.account?.xfaConsistencyMaxPayoutCap === TOPSTEP_50K_PARAMETERS.xfaConsistencyMaxPayoutCap
    && candidate.challengePath?.preferredFundedPath === "xfa-standard"
    && candidate.riskModes?.challenge?.executionInstrument === "MNQ"
    && candidate.riskModes?.challenge?.activationStatus === "proposal-only-until-risk-policy-clears"
    && candidate.riskModes?.funded?.executionInstrument === "MNQ"
    && candidate.riskModes?.funded?.activationStatus === "proposal-only-until-risk-policy-clears";
}

export function migratePropFirmPayoutPlanPolicy(
  legacy: unknown,
  now: () => string = () => new Date().toISOString(),
): PropFirmPayoutPlan {
  const candidate = legacy as Partial<PropFirmPayoutPlan> | null | undefined;
  const legacyTopCandidates = Array.isArray(candidate?.topCandidates)
    ? candidate.topCandidates
    : [];
  const topCandidates = legacyTopCandidates.map((score) => ({
    ...score,
    // Strategy score rows describe mini-equivalent exposure. The 50K live
    // policy is MNQ-first, so no scored lane may imply NQ escalation.
    maxContracts: 1,
  }));
  const payoutBuilders = topCandidates.filter((score) => score.laneRole === "payout-builder");
  const candidateCount = Math.max(Number(candidate?.candidateCount ?? 0), topCandidates.length);
  const blockers = [
    ...(candidateCount > 0 ? [] : ["no-strategy-candidates-provided"]),
    ...(payoutBuilders.length > 0 ? [] : ["no-payout-builder-candidate"])
  ];

  return {
    command: "prop-firm-payout-plan",
    generatedAt: now(),
    account: TOPSTEP_50K_PARAMETERS,
    posture: blockers.length === 0 ? "ready-to-demo" : "needs-evidence",
    candidateCount,
    topCandidates,
    blockers,
    operatingRules: CURRENT_TOPSTEP_50K_OPERATING_RULES,
    challengePath: CURRENT_TOPSTEP_50K_CHALLENGE_PATH(blockers.length === 0),
    riskModes: TOPSTEP_NQ_RISK_MODES
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
  xfaStandardMaxPayoutCap: 2000,
  xfaConsistencyTradingDays: 3,
  xfaConsistencyMaxLargestDayPct: 0.4,
  xfaConsistencyMaxPayoutCap: 3000,
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
    activationStatus: "proposal-only-until-risk-policy-clears",
    activePolicyRule: "Current env/risk-policy max contracts and daily plan approval override this proposed challenge sizing.",
    allowedSymbols: ["MNQ"],
    executionInstrument: "MNQ",
    maxTradesPerDay: 3,
    tradeMath: buildNqTradeMath({
      symbol: "MNQ",
      targetTicks: 80,
      stopTicks: 28,
      runnerTrailTicks: 20,
      contracts: 8,
      maxTradesPerDay: 3
    }),
    dailyProfitLock: 900,
    dailyLossLock: 350,
    rationale: [
      "50K live sizing is MNQ-first; the 100K demo can calibrate NQ behavior, but the live 50K account should not inherit 100K aggression.",
      "Eight MNQ keeps a 20-point target around $320 gross, so two to three clean wins can build a pass window while staying below the $1,500 50K best-day recommendation.",
      "A 7-point initial stop keeps one miss near $112 gross before fees; the day stops before loss recovery behavior starts."
    ],
    automationPrerequisites: [
      "Realtime bracket orders with server-side stop and target.",
      "Personal daily profit target must liquidate and block near the configured daily profit lock.",
      "Max-three-trades state machine with no manual override unless the kill switch is active.",
      "News and volatility lockouts around scheduled high-impact releases.",
      "Escalation to one NQ requires a separate green 50K broker-parity and daily-lock proof."
    ]
  },
  funded: {
    phase: "funded",
    posture: "payout-defense",
    activationStatus: "proposal-only-until-risk-policy-clears",
    activePolicyRule: "Current env/risk-policy max contracts, payout-window consistency, and daily plan approval override this proposed funded sizing.",
    allowedSymbols: ["MNQ"],
    executionInstrument: "MNQ",
    maxTradesPerDay: 3,
    tradeMath: buildNqTradeMath({
      symbol: "MNQ",
      targetTicks: 80,
      stopTicks: 24,
      runnerTrailTicks: 20,
      contracts: 5,
      maxTradesPerDay: 3
    }),
    dailyProfitLock: 300,
    dailyLossLock: 180,
    rationale: [
      "Funded accounts optimize for payout eligibility and review survival, not fastest gross PnL.",
      "MNQ keeps the same NQ signal geometry while reducing single-trade dollar variance.",
      "Five MNQ targets roughly $200 gross on a 20-point capture, giving room above the $150 winning-day threshold after normal fees/slippage."
    ],
    automationPrerequisites: [
      "Funded mode cannot reuse challenge sizing.",
      "The bot must stop after target, daily lock, two losses, or any scaling-plan conflict.",
      "Every funded entry needs a journaled setup tag, entry reason, initial risk, exit reason, and screenshot/reference id.",
      "Payout-window consistency metrics must be recomputed before every new order."
    ]
  }
};

const CURRENT_TOPSTEP_50K_OPERATING_RULES = [
  "Risk mode contract counts are proposals only; current env/risk-policy max contracts, daily plan approval, and broker reconciliation are binding.",
  "50K live sizing is MNQ-first; one NQ is escalation-only after separate broker-parity and daily-lock proof.",
  "Challenge daily profit lock stays near $900 and always below the $1,500 50K combine best-day recommendation.",
  "Funded/default daily target stays below $650; funded payout-defense mode starts near $300.",
  "Challenge daily loss lock stays near $350; funded payout-defense daily loss lock starts near $180.",
  "XFA Standard target is five $150+ winning days and is the default payout lane; XFA Consistency is optional only when the selected account path is explicitly consistency and largest day <=40% of payout-window net profit.",
  "Stop trading the account for the day after target, daily stop, two losses, or any platform risk lock."
];

const CURRENT_TOPSTEP_50K_CHALLENGE_PATH = (hasPayoutBuilder: boolean): PropFirmChallengePath => ({
  objective: hasPayoutBuilder ? "pass-combine" : "build-evidence",
  fastestResponsibleWindowDays: [6, 12],
  preferredFundedPath: "xfa-standard",
  dailyNetTargetRange: [300, 650],
  dailyHardLossStop: 350,
  tradePlan: [
    "Use one payout-builder lane per 50K account; keep MNQ contracts fixed through the challenge window.",
    "Aim for four to seven controlled green sessions instead of a one-day pass; a best day above 50% of target makes the pass and payout path harder.",
    "After funding, use XFA Standard by default and collect five $150+ days; choose XFA Consistency only when the account was explicitly activated on that path and Bill can keep the largest payout-window day <=40% of net profit.",
    "Treat the first funded payout as capital preservation, not a sizing unlock."
  ],
  promotionGate: [
    "At least one current payout-builder with positive expectancy, >=20 trades, resilience >=0.45, and no flat bias.",
    "No daily loss breach, platform risk lock, or synthetic fallback signal in the last 10 sampled sessions.",
    "A replayable journal exists for every entry, exit, skipped trade, and stop-after-target decision."
  ]
});

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
    operatingRules: CURRENT_TOPSTEP_50K_OPERATING_RULES,
    challengePath: CURRENT_TOPSTEP_50K_CHALLENGE_PATH(blockers.length === 0),
    riskModes: TOPSTEP_NQ_RISK_MODES
  };

  if (args.outputPath) {
    const outputPath = resolve(args.outputPath);
    await mkdir(dirname(outputPath), { recursive: true });
    await writeFile(outputPath, `${JSON.stringify(plan, null, 2)}\n`, "utf8");
  }
  return plan;
}
