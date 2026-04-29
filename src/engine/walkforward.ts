import type { Bar, FamilyBudgetRecommendation, LabConfig, SummaryReport } from "../domain.js";
import type { NewsGate } from "../news/base.js";
import { chicagoDateKey } from "../utils/time.js";
import { runBacktest } from "./backtest.js";
import { buildFamilyBudgetRecommendation, summarizeTrades } from "./report.js";
import { evaluateResearchPromotion, type PromotionGateResult } from "./promotionGate.js";
import { RESEARCH_PROFILES, mergeProfile, type ResearchProfile } from "../research/profiles.js";
import { buildDefaultEnsemble } from "../strategies/wctcEnsemble.js";

export interface WalkforwardProfileResult {
  profileId: string;
  description: string;
  trainSummary: SummaryReport;
  testSummary: SummaryReport;
  score: number;
  scoreStability: number;
  windowCount: number;
  splitScores: number[];
  familyBudget: FamilyBudgetRecommendation;
}

export interface WalkforwardResearchResult {
  profiles: WalkforwardProfileResult[];
  winner: WalkforwardProfileResult | null;
  recommendedFamilyBudget: FamilyBudgetRecommendation | null;
  promotionGate: PromotionGateResult | null;
  deployableWinner: WalkforwardProfileResult | null;
  deployableFamilyBudget: FamilyBudgetRecommendation | null;
  deployablePromotionGate: PromotionGateResult | null;
}

export interface WalkforwardWindow {
  train: Bar[];
  test: Bar[];
}

interface RankedWalkforwardCandidate {
  profile: WalkforwardProfileResult;
  gate: PromotionGateResult;
}

function splitBarsByDay(bars: Bar[]): { train: Bar[]; test: Bar[] } {
  const uniqueDays = Array.from(new Set(bars.map((bar) => chicagoDateKey(bar.ts))));
  const splitIndex = Math.max(1, Math.floor(uniqueDays.length * 0.6));
  const trainDays = new Set(uniqueDays.slice(0, splitIndex));
  const testDays = new Set(uniqueDays.slice(splitIndex));

  return {
    train: bars.filter((bar) => trainDays.has(chicagoDateKey(bar.ts))),
    test: bars.filter((bar) => testDays.has(chicagoDateKey(bar.ts)))
  };
}

function std(values: number[]): number {
  if (values.length < 2) {
    return 0;
  }

  const average = values.reduce((sum, value) => sum + value, 0) / values.length;
  const variance = values.reduce((sum, value) => sum + ((value - average) ** 2), 0) / (values.length - 1);
  return Math.sqrt(Math.max(0, variance));
}

function clamp01(value: number): number {
  return Math.max(0, Math.min(1, value));
}

function activityAdjustedScore(baseScore: number, testTrades: number): number {
  if (testTrades === 0) {
    return -9;
  }

  const targetTrades = 12;
  const activityFactor = clamp01(testTrades / targetTrades);
  const inactivityPenalty = (1 - activityFactor) * 1.25;
  const adjusted = (baseScore * (0.5 + (0.5 * activityFactor))) - inactivityPenalty;
  return Number(adjusted.toFixed(4));
}

export function buildWalkforwardWindows(bars: Bar[], options: { embargoDays?: number } = {}): WalkforwardWindow[] {
  const uniqueDays = Array.from(new Set(bars.map((bar) => chicagoDateKey(bar.ts))));
  if (uniqueDays.length < 5) {
    const single = splitBarsByDay(bars);
    return single.test.length === 0 ? [] : [single];
  }

  const maxWindows = 3;
  const embargoDays = Math.max(0, Math.floor(options.embargoDays ?? 1));
  const baseTrainDays = Math.max(2, Math.floor(uniqueDays.length * 0.5));
  const remainingDays = uniqueDays.length - baseTrainDays;
  const windowCount = Math.min(maxWindows, remainingDays);
  const testBlockDays = Math.max(1, Math.floor(remainingDays / Math.max(1, windowCount)));
  const windows: WalkforwardWindow[] = [];

  for (let index = 0; index < windowCount; index += 1) {
    const trainEnd = baseTrainDays + (index * testBlockDays);
    const testStart = trainEnd + embargoDays;
    const testEnd = Math.min(uniqueDays.length, testStart + testBlockDays);
    if (trainEnd <= 0 || testEnd <= testStart) {
      continue;
    }

    const trainDays = new Set(uniqueDays.slice(0, trainEnd));
    const testDays = new Set(uniqueDays.slice(testStart, testEnd));
    const train = bars.filter((bar) => trainDays.has(chicagoDateKey(bar.ts)));
    const test = bars.filter((bar) => testDays.has(chicagoDateKey(bar.ts)));
    if (train.length === 0 || test.length === 0) {
      continue;
    }

    windows.push({ train, test });
  }

  if (windows.length === 0) {
    const fallback = splitBarsByDay(bars);
    if (fallback.train.length > 0 && fallback.test.length > 0) {
      windows.push(fallback);
    }
  }

  return windows;
}

function scoreSummary(summary: SummaryReport): number {
  const quality = summary.tradeQuality;
  const convexity =
    (Math.max(0, quality.avgWinR - 2.2) * 0.55) +
    (Math.max(0, quality.payoffRatio - 1.1) * 0.7);
  const efficiency =
    (quality.expectancyR * 4) +
    (quality.sharpePerTrade * 0.9) +
    (quality.sortinoPerTrade * 0.65);
  const penalties =
    (summary.maxDrawdownR * 0.55) +
    (quality.riskOfRuinProb * 4.5) +
    (Math.max(0, Math.abs(Math.min(0, quality.cvar95TradeR)) - 1) * 0.75) +
    (summary.frictionR * 0.35);

  return Number(((summary.netTotalR * 0.75) + efficiency + convexity + (summary.winRate * 1.2) - penalties).toFixed(4));
}

function promotionFitClass(candidate: RankedWalkforwardCandidate): number {
  const activeFamilies = candidate.profile.familyBudget.activeFamilies.length;
  const netPositive = candidate.profile.testSummary.netTotalR > 0;
  const expectancyPositive = candidate.profile.testSummary.tradeQuality.expectancyR > 0;

  if (candidate.gate.ready) return 4;
  if (netPositive && expectancyPositive && activeFamilies > 0) return 3;
  if (netPositive && expectancyPositive) return 2;
  if (netPositive) return 1;
  return 0;
}

function passedCheckCount(gate: PromotionGateResult): number {
  return gate.checks.filter((check) => check.passed).length;
}

function compareRankedCandidates(left: RankedWalkforwardCandidate, right: RankedWalkforwardCandidate): number {
  return (
    promotionFitClass(right) - promotionFitClass(left)
    || passedCheckCount(right.gate) - passedCheckCount(left.gate)
    || right.profile.testSummary.netTotalR - left.profile.testSummary.netTotalR
    || right.profile.testSummary.tradeQuality.expectancyR - left.profile.testSummary.tradeQuality.expectancyR
    || left.profile.testSummary.maxDrawdownR - right.profile.testSummary.maxDrawdownR
    || left.profile.testSummary.tradeQuality.riskOfRuinProb - right.profile.testSummary.tradeQuality.riskOfRuinProb
    || right.profile.scoreStability - left.profile.scoreStability
    || right.profile.score - left.profile.score
  );
}

export function sortWalkforwardProfilesForSelection(args: {
  profiles: WalkforwardProfileResult[];
  phase: LabConfig["accountPhase"];
}): RankedWalkforwardCandidate[] {
  return args.profiles
    .map((profile) => ({
      profile,
      gate: evaluateResearchPromotion({
        winner: profile,
        recommendedFamilyBudget: profile.familyBudget,
        phase: args.phase
      })
    }))
    .sort(compareRankedCandidates);
}

async function evaluateProfile(args: {
  profile: ResearchProfile;
  baseConfig: LabConfig;
  windows: WalkforwardWindow[];
  newsGate: NewsGate;
}): Promise<WalkforwardProfileResult> {
  const { profile, baseConfig, windows, newsGate } = args;
  const config = mergeProfile(baseConfig, profile);
  const trainTrades = [];
  const testTrades = [];
  const splitScores: number[] = [];

  for (const window of windows) {
    const trainResult = await runBacktest({
      bars: window.train,
      strategy: buildDefaultEnsemble(config),
      config,
      newsGate
    });
    const testResult = await runBacktest({
      bars: window.test,
      strategy: buildDefaultEnsemble(config),
      config,
      newsGate
    });

    trainTrades.push(...trainResult.trades);
    testTrades.push(...testResult.trades);
    const trainSummary = summarizeTrades(trainResult.trades);
    const testSummary = summarizeTrades(testResult.trades);
    splitScores.push((scoreSummary(testSummary) * 0.7) + (scoreSummary(trainSummary) * 0.3));
  }

  const trainSummary = summarizeTrades(trainTrades);
  const testSummary = summarizeTrades(testTrades);
  const familyBudget = buildFamilyBudgetRecommendation({
    trainSummary,
    testSummary
  });
  const meanSplitScore = splitScores.length === 0
    ? (scoreSummary(testSummary) * 0.7) + (scoreSummary(trainSummary) * 0.3)
    : splitScores.reduce((sum, value) => sum + value, 0) / splitScores.length;
  const scoreStability = clamp01(1 - (std(splitScores) / (Math.abs(meanSplitScore) + 1)));
  const rawScore = meanSplitScore * (0.7 + (0.3 * scoreStability));
  const finalScore = activityAdjustedScore(rawScore, testSummary.totalTrades);

  return {
    profileId: profile.id,
    description: profile.description,
    trainSummary,
    testSummary,
    familyBudget,
    scoreStability: Number(scoreStability.toFixed(4)),
    windowCount: Math.max(1, windows.length),
    splitScores: splitScores.map((s) => Number(s.toFixed(4))),
    score: Number(finalScore.toFixed(4))
  };
}

export async function runWalkforwardResearch(args: {
  baseConfig: LabConfig;
  bars: Bar[];
  newsGate: NewsGate;
}): Promise<WalkforwardResearchResult> {
  const windows = buildWalkforwardWindows(args.bars);
  return runWalkforwardResearchOnWindows({
    baseConfig: args.baseConfig,
    windows,
    newsGate: args.newsGate
  });
}

export async function runWalkforwardResearchOnWindows(args: {
  baseConfig: LabConfig;
  windows: WalkforwardWindow[];
  newsGate: NewsGate;
}): Promise<WalkforwardResearchResult> {
  const { baseConfig, windows, newsGate } = args;
  const profiles = [];

  for (const profile of RESEARCH_PROFILES) {
    profiles.push(await evaluateProfile({ profile, baseConfig, windows, newsGate }));
  }

  const ranked = sortWalkforwardProfilesForSelection({
    profiles,
    phase: baseConfig.accountPhase
  });
  const winner = ranked[0]?.profile ?? null;
  const winnerPromotionGate = ranked[0]?.gate ?? null;
  profiles.splice(0, profiles.length, ...ranked.map((entry) => entry.profile));

  let deployableWinner: WalkforwardProfileResult | null = null;
  let deployablePromotionGate: PromotionGateResult | null = null;
  for (const entry of ranked) {
    const candidate = entry.profile;
    const candidateGate = entry.gate;
    if (candidateGate.ready) {
      deployableWinner = candidate;
      deployablePromotionGate = candidateGate;
      break;
    }
  }

  return {
    profiles,
    winner,
    recommendedFamilyBudget: winner?.familyBudget ?? null,
    promotionGate: winnerPromotionGate,
    deployableWinner,
    deployableFamilyBudget: deployableWinner?.familyBudget ?? null,
    deployablePromotionGate
  };
}
