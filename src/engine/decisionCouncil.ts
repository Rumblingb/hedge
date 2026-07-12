import type { AgenticFundReport } from "../domain.js";
import type { SupportedStrategyId } from "../domain.js";
import type { FuturesResearchStrategyFeed } from "../research/strategyFeed.js";
import type { StrategyCandidate } from "./expectedValueSurface.js";

export type CouncilRating = "Buy" | "Overweight" | "Hold" | "Underweight" | "Sell";
export type CouncilAction = "paper-trade" | "shadow-observe" | "stand-down";

export interface StrategyCouncilDecision {
  analystTeam: {
    technical: string;
    research: string;
    risk: string;
  };
  bullCase: {
    score: number;
    arguments: string[];
  };
  bearCase: {
    score: number;
    arguments: string[];
  };
  riskReview: {
    hardVeto: boolean;
    vetoReasons: string[];
  };
  portfolioManager: {
    rating: CouncilRating;
    action: CouncilAction;
    rationale: string;
  };
}

function roundScore(value: number): number {
  return Number(value.toFixed(4));
}

function candidateQualityScore(candidate: StrategyCandidate | null): number {
  if (!candidate || candidate.directionalBias === "flat") {
    return 0;
  }
  const ev = Math.max(0, Math.min(1.2, candidate.expectedValueScore / 2));
  const regime = Math.max(0, Math.min(1, candidate.regimeConfidence));
  const resilience = Math.max(0, Math.min(1, candidate.resilienceScore));
  const convexity = Math.max(0, Math.min(1, candidate.convexityScore));
  const sample = Math.max(0, Math.min(1, candidate.strategyTrades / 12));
  return roundScore((ev * 0.32) + (regime * 0.22) + (resilience * 0.22) + (convexity * 0.14) + (sample * 0.1));
}

function researchSupportScore(feed: FuturesResearchStrategyFeed | null | undefined, candidate: StrategyCandidate | null): number {
  if (!feed || !candidate) {
    return 0;
  }
  const strategyId = candidate.strategyId as SupportedStrategyId;
  const strategyHit = feed.preferredStrategies.includes(strategyId) ? 0.22 : 0;
  const symbolHit = feed.preferredSymbols.includes(candidate.symbol) ? 0.18 : 0;
  const directiveHit = feed.directives.some((directive) =>
    directive.strategyId === candidate.strategyId && directive.symbols.includes(candidate.symbol)
  ) ? 0.2 : 0;
  return roundScore(Math.min(0.45, strategyHit + symbolHit + directiveHit));
}

function failedCheckPenalty(check: string): number {
  switch (check) {
    case "testNetR":
    case "testExpectancyR":
    case "maxDrawdownR":
    case "riskOfRuinProb":
      return 0.24;
    case "cvar95TradeR":
    case "scoreStability":
      return 0.16;
    case "testTradeCount":
    case "activeFamilies":
      return 0.1;
    default:
      return 0.08;
  }
}

function ratingFromNetScore(netScore: number, hardVeto: boolean): CouncilRating {
  if (hardVeto) return "Sell";
  if (netScore >= 0.55) return "Buy";
  if (netScore >= 0.3) return "Overweight";
  if (netScore >= 0.05) return "Hold";
  if (netScore >= -0.2) return "Underweight";
  return "Sell";
}

export function buildStrategyCouncilDecision(args: {
  report: AgenticFundReport;
  candidate: StrategyCandidate | null;
  researchStrategyFeed?: FuturesResearchStrategyFeed | null;
  selectedExecutionAction: "paper-trade" | "stand-down";
  selectedExecutionReason: string;
}): StrategyCouncilDecision {
  const candidateScore = candidateQualityScore(args.candidate);
  const researchScore = researchSupportScore(args.researchStrategyFeed, args.candidate);
  const deployableScore = args.report.deployableNow ? 0.25 : 0;
  const bullScore = roundScore(Math.min(1, candidateScore + researchScore + deployableScore));

  const failedCheckScore = roundScore(Math.min(1, args.report.failedChecks.reduce((sum, check) => sum + failedCheckPenalty(check), 0)));
  const sparseSamplePenalty = args.candidate && args.candidate.strategyTrades < 5 ? 0.12 : 0;
  const weakResiliencePenalty = args.candidate && args.candidate.resilienceScore < 0.55 ? 0.12 : 0;
  const missingCandidatePenalty = args.candidate ? 0 : 0.25;
  const bearScore = roundScore(Math.min(1, failedCheckScore + sparseSamplePenalty + weakResiliencePenalty + missingCandidatePenalty));

  const hardVetoReasons = [
    ...(!args.report.deployableNow ? ["promotion gate is not deployable"] : []),
    ...(args.selectedExecutionAction !== "paper-trade" ? [args.selectedExecutionReason] : []),
    ...(!args.candidate ? ["no candidate survived expected-value and regime screens"] : []),
    ...(args.candidate && args.candidate.directionalBias === "flat" ? ["candidate directional bias is flat"] : []),
    ...(args.candidate && args.candidate.expectedValueScore <= 0 ? ["candidate expected value is non-positive"] : []),
    ...args.report.failedChecks
      .filter((check) => ["testNetR", "testExpectancyR", "maxDrawdownR", "riskOfRuinProb"].includes(check))
      .map((check) => `hard promotion check failed: ${check}`)
  ];
  const hardVeto = hardVetoReasons.length > 0;
  const netScore = roundScore(bullScore - bearScore);
  const rating = ratingFromNetScore(netScore, hardVeto);
  const action: CouncilAction = hardVeto
    ? (args.candidate && candidateScore > 0.45 ? "shadow-observe" : "stand-down")
    : "paper-trade";

  return {
    analystTeam: {
      technical: args.candidate
        ? `${args.candidate.strategyId} on ${args.candidate.symbol}: EV ${args.candidate.expectedValueScore.toFixed(2)}, regime ${args.candidate.regime} (${args.candidate.regimeConfidence.toFixed(2)} confidence).`
        : "No technical candidate survived the current surface.",
      research: args.researchStrategyFeed
        ? `Fresh researcher feed supports ${args.researchStrategyFeed.preferredStrategies.join(", ") || "no specific strategy"} across ${args.researchStrategyFeed.preferredSymbols.join(", ") || "no specific symbol"}.`
        : "No fresh same-run researcher strategy feed is available.",
      risk: args.report.failedChecks.length > 0
        ? `Failed promotion checks: ${args.report.failedChecks.join(", ")}.`
        : "Promotion checks are clean under current policy."
    },
    bullCase: {
      score: bullScore,
      arguments: [
        ...(args.candidate ? [`Candidate quality score ${candidateScore.toFixed(2)} from EV, regime confidence, resilience, convexity, and sample depth.`] : []),
        ...(researchScore > 0 ? [`Fresh research adds ${researchScore.toFixed(2)} support to the same strategy/symbol lane.`] : []),
        ...(args.report.deployableNow ? ["Promotion gate is deployable under current guardrails."] : [])
      ]
    },
    bearCase: {
      score: bearScore,
      arguments: [
        ...(args.report.failedChecks.length > 0 ? [`Promotion failures carry ${failedCheckScore.toFixed(2)} total penalty.`] : []),
        ...(sparseSamplePenalty > 0 ? ["Candidate sample is still thin for live confidence."] : []),
        ...(weakResiliencePenalty > 0 ? ["Candidate resilience is below preferred live threshold."] : []),
        ...(missingCandidatePenalty > 0 ? ["No candidate exists, so opportunity cost beats execution risk."] : [])
      ]
    },
    riskReview: {
      hardVeto,
      vetoReasons: hardVetoReasons
    },
    portfolioManager: {
      rating,
      action,
      rationale: hardVeto
        ? `Council vetoes execution: ${hardVetoReasons[0] ?? "risk gate failed"}.`
        : `Council allows paper/demo routing with ${rating} rating and net score ${netScore.toFixed(2)}.`
    }
  };
}
