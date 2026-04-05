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

interface WalkforwardWindow {
  train: Bar[];
  test: Bar[];
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

function buildWalkforwardWindows(bars: Bar[]): WalkforwardWindow[] {
  const uniqueDays = Array.from(new Set(bars.map((bar) => chicagoDateKey(bar.ts))));
  if (uniqueDays.length < 5) {
    const single = splitBarsByDay(bars);
    return single.test.length === 0 ? [] : [single];
  }

  const maxWindows = 3;
  const baseTrainDays = Math.max(2, Math.floor(uniqueDays.length * 0.5));
  const remainingDays = uniqueDays.length - baseTrainDays;
  const windowCount = Math.min(maxWindows, remainingDays);
  const testBlockDays = Math.max(1, Math.floor(remainingDays / Math.max(1, windowCount)));
  const windows: WalkforwardWindow[] = [];

  for (let index = 0; index < windowCount; index += 1) {
    const trainEnd = baseTrainDays + (index * testBlockDays);
    const testEnd = Math.min(uniqueDays.length, trainEnd + testBlockDays);
    if (trainEnd <= 0 || testEnd <= trainEnd) {
      continue;
    }

    const trainDays = new Set(uniqueDays.slice(0, trainEnd));
    const testDays = new Set(uniqueDays.slice(trainEnd, testEnd));
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
  return Number((summary.totalR - (summary.maxDrawdownR * 0.5) + (summary.winRate * 2)).toFixed(4));
}

async function evaluateProfile(args: {
  profile: ResearchProfile;
  baseConfig: LabConfig;
  bars: Bar[];
  newsGate: NewsGate;
}): Promise<WalkforwardProfileResult> {
  const { profile, baseConfig, bars, newsGate } = args;
  const config = mergeProfile(baseConfig, profile);
  const windows = buildWalkforwardWindows(bars);
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
    score: Number(finalScore.toFixed(4))
  };
}

export async function runWalkforwardResearch(args: {
  baseConfig: LabConfig;
  bars: Bar[];
  newsGate: NewsGate;
}): Promise<WalkforwardResearchResult> {
  const { baseConfig, bars, newsGate } = args;
  const profiles = [];

  for (const profile of RESEARCH_PROFILES) {
    profiles.push(await evaluateProfile({ profile, baseConfig, bars, newsGate }));
  }

  profiles.sort((left, right) => right.score - left.score);

  const winner = profiles[0] ?? null;
  const winnerPromotionGate = winner
    ? evaluateResearchPromotion({
        winner,
        recommendedFamilyBudget: winner.familyBudget,
        phase: baseConfig.accountPhase
      })
    : null;

  let deployableWinner: WalkforwardProfileResult | null = null;
  let deployablePromotionGate: PromotionGateResult | null = null;
  for (const candidate of profiles) {
    const candidateGate = evaluateResearchPromotion({
      winner: candidate,
      recommendedFamilyBudget: candidate.familyBudget,
      phase: baseConfig.accountPhase
    });
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
