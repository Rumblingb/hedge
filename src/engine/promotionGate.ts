import type { FamilyBudgetRecommendation, SummaryReport } from "../domain.js";
import type { WalkforwardProfileResult } from "./walkforward.js";
import type { AccountPhase } from "../domain.js";

export interface PromotionGateCheck {
  name: string;
  passed: boolean;
  observed: number;
  threshold: number;
  direction: "min" | "max";
  reason: string;
}

export interface PromotionGateResult {
  ready: boolean;
  checks: PromotionGateCheck[];
  reasons: string[];
}

function buildCheck(args: {
  name: string;
  observed: number;
  threshold: number;
  direction: "min" | "max";
  passReason: string;
  failReason: string;
}): PromotionGateCheck {
  const { name, observed, threshold, direction, passReason, failReason } = args;
  const passed = direction === "min" ? observed >= threshold : observed <= threshold;

  return {
    name,
    passed,
    observed: Number(observed.toFixed(4)),
    threshold: Number(threshold.toFixed(4)),
    direction,
    reason: passed ? passReason : failReason
  };
}

function gateChecks(args: {
  testSummary: SummaryReport;
  familyBudget: FamilyBudgetRecommendation;
  scoreStability: number;
  phase: AccountPhase;
}): PromotionGateCheck[] {
  const { testSummary, familyBudget, scoreStability, phase } = args;
  const isFunded = phase === "funded";

  return [
    buildCheck({
      name: "testTradeCount",
      observed: testSummary.totalTrades,
      threshold: isFunded ? 12 : 8,
      direction: "min",
      passReason: "Out-of-sample sample size is sufficient.",
      failReason: "Out-of-sample sample size is too small."
    }),
    buildCheck({
      name: "testNetR",
      observed: testSummary.netTotalR,
      threshold: 0,
      direction: "min",
      passReason: "Test net R is positive.",
      failReason: "Test net R is not positive."
    }),
    buildCheck({
      name: "testExpectancyR",
      observed: testSummary.tradeQuality.expectancyR,
      threshold: 0,
      direction: "min",
      passReason: "Per-trade expectancy is positive.",
      failReason: "Per-trade expectancy is not positive."
    }),
    buildCheck({
      name: "maxDrawdownR",
      observed: testSummary.maxDrawdownR,
      threshold: isFunded ? 3 : 4,
      direction: "max",
      passReason: "Drawdown is inside acceptable bound.",
      failReason: "Drawdown exceeds acceptable bound."
    }),
    buildCheck({
      name: "cvar95TradeR",
      observed: testSummary.tradeQuality.cvar95TradeR,
      threshold: isFunded ? -1 : -1.25,
      direction: "min",
      passReason: "CVaR95 tail loss is controlled.",
      failReason: "CVaR95 tail loss is too deep."
    }),
    buildCheck({
      name: "riskOfRuinProb",
      observed: testSummary.tradeQuality.riskOfRuinProb,
      threshold: isFunded ? 0.25 : 0.35,
      direction: "max",
      passReason: "Estimated risk of ruin is acceptable.",
      failReason: "Estimated risk of ruin is too high."
    }),
    buildCheck({
      name: "scoreStability",
      observed: scoreStability,
      threshold: isFunded ? 0.65 : 0.55,
      direction: "min",
      passReason: "Walk-forward profile score is sufficiently stable.",
      failReason: "Walk-forward profile score is unstable across windows."
    }),
    buildCheck({
      name: "activeFamilies",
      observed: familyBudget.activeFamilies.length,
      threshold: 1,
      direction: "min",
      passReason: "At least one market family remains active.",
      failReason: "No market families are active after risk budgeting."
    })
  ];
}

export function evaluateResearchPromotion(args: {
  winner: WalkforwardProfileResult;
  recommendedFamilyBudget: FamilyBudgetRecommendation;
  phase: AccountPhase;
}): PromotionGateResult {
  const { winner, recommendedFamilyBudget, phase } = args;
  const checks = gateChecks({
    testSummary: winner.testSummary,
    familyBudget: recommendedFamilyBudget,
    scoreStability: winner.scoreStability,
    phase
  });

  return {
    ready: checks.every((check) => check.passed),
    checks,
    reasons: checks.filter((check) => !check.passed).map((check) => check.reason)
  };
}
