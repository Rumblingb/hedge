import type { Bar, FamilyBudgetRecommendation, LabConfig, SummaryReport } from "../domain.js";
import type { NewsGate } from "../news/base.js";
import { chicagoDateKey } from "../utils/time.js";
import { runBacktest } from "./backtest.js";
import { buildFamilyBudgetRecommendation, summarizeTrades } from "./report.js";
import { RESEARCH_PROFILES, mergeProfile, type ResearchProfile } from "../research/profiles.js";
import { buildDefaultEnsemble } from "../strategies/wctcEnsemble.js";

export interface WalkforwardProfileResult {
  profileId: string;
  description: string;
  trainSummary: SummaryReport;
  testSummary: SummaryReport;
  score: number;
  familyBudget: FamilyBudgetRecommendation;
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
  const { train, test } = splitBarsByDay(bars);
  const trainResult = await runBacktest({
    bars: train,
    strategy: buildDefaultEnsemble(config),
    config,
    newsGate
  });
  const testResult = await runBacktest({
    bars: test,
    strategy: buildDefaultEnsemble(config),
    config,
    newsGate
  });

  const trainSummary = summarizeTrades(trainResult.trades);
  const testSummary = summarizeTrades(testResult.trades);
  const familyBudget = buildFamilyBudgetRecommendation({
    trainSummary,
    testSummary
  });

  return {
    profileId: profile.id,
    description: profile.description,
    trainSummary,
    testSummary,
    familyBudget,
    score: Number(((scoreSummary(testSummary) * 0.7) + (scoreSummary(trainSummary) * 0.3)).toFixed(4))
  };
}

export async function runWalkforwardResearch(args: {
  baseConfig: LabConfig;
  bars: Bar[];
  newsGate: NewsGate;
}): Promise<{
  profiles: WalkforwardProfileResult[];
  winner: WalkforwardProfileResult | null;
  recommendedFamilyBudget: FamilyBudgetRecommendation | null;
}> {
  const { baseConfig, bars, newsGate } = args;
  const profiles = [];

  for (const profile of RESEARCH_PROFILES) {
    profiles.push(await evaluateProfile({ profile, baseConfig, bars, newsGate }));
  }

  profiles.sort((left, right) => right.score - left.score);

  return {
    profiles,
    winner: profiles[0] ?? null,
    recommendedFamilyBudget: profiles[0]?.familyBudget ?? null
  };
}
