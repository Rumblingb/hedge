import type { Bar, LabConfig } from "../domain.js";
import type { NewsGate } from "../news/base.js";
import { buildAgenticFundReport } from "./agenticFund.js";
import type { StrategyCandidate } from "./expectedValueSurface.js";
import { buildExpectedValueSurface } from "./expectedValueSurface.js";
import { buildStrategyCouncilDecision, type StrategyCouncilDecision } from "./decisionCouncil.js";
import type { SymbolRegimeAssessment } from "./regime.js";
import { classifyLatestSessionRegimes } from "./regime.js";
import { runWalkforwardResearch } from "./walkforward.js";
import { RESEARCH_PROFILES, mergeProfile } from "../research/profiles.js";
import type { FuturesResearchStrategyFeed } from "../research/strategyFeed.js";
import { getMarketCategory } from "../utils/markets.js";

function filterBarsToAllowedSymbols(args: {
  bars: Bar[];
  allowedSymbols: string[];
}): Bar[] {
  const allowed = new Set(args.allowedSymbols);
  return args.bars.filter((bar) => allowed.has(bar.symbol));
}

function strategyRole(strategyId: string): string {
  switch (strategyId) {
    case "session-momentum":
      return "Trend continuation after session expansion and volume confirmation.";
    case "opening-range-reversal":
      return "Fade opening auction sweeps that reclaim the range.";
    case "liquidity-reversion":
      return "Short-hold mean reversion after a sweep-and-close-back-inside move.";
    case "ict-displacement":
      return "ICT-style liquidity sweep, displacement, and fair value gap continuation.";
    default:
      return "Strategy role not documented yet.";
  }
}

function buildPreferredSymbols(args: {
  allowedSymbols: string[];
  activeFamilies: string[];
  symbolSummary: Record<string, { netTotalR: number; winRate: number; trades: number }>;
}): string[] {
  const { allowedSymbols, activeFamilies, symbolSummary } = args;
  const ranked = Object.entries(symbolSummary)
    .filter(([symbol, summary]) => allowedSymbols.includes(symbol) && summary.trades > 0)
    .filter(([symbol, summary]) => summary.netTotalR > 0 || activeFamilies.includes(getMarketCategory(symbol)))
    .sort((left, right) => {
      if (right[1].netTotalR !== left[1].netTotalR) {
        return right[1].netTotalR - left[1].netTotalR;
      }

      return right[1].winRate - left[1].winRate;
    })
    .map(([symbol]) => symbol);

  if (ranked.length > 0) {
    return ranked.slice(0, 4);
  }

  return allowedSymbols.slice(0, 4);
}

function mergePriorityList(values: string[], fallback: string[]): string[] {
  return Array.from(new Set([...values, ...fallback]));
}

function applyResearchFeedToEvidencePlan(args: {
  evidencePlan: {
    mode: "promotion-ready" | "evidence-build" | "repair";
    laneDirective: "paper-trade" | "concentrate-best-edge" | "keep-mixed" | "standby";
    shortfallTrades: number;
    focusStrategies: string[];
    focusSymbols: string[];
    rationale: string;
    strongestCandidate: {
      strategyId: string;
      symbol: string;
      expectedValueScore: number;
      resilienceScore: number;
      convexityScore: number;
    } | null;
  };
  researchStrategyFeed?: FuturesResearchStrategyFeed | null;
  availableStrategies: string[];
  availableSymbols: string[];
}) {
  const feed = args.researchStrategyFeed;
  if (!feed) {
    return args.evidencePlan;
  }

  const hintedStrategies = feed.preferredStrategies.filter((strategyId) => args.availableStrategies.includes(strategyId));
  const hintedSymbols = feed.preferredSymbols.filter((symbol) => args.availableSymbols.includes(symbol));
  if (hintedStrategies.length === 0 && hintedSymbols.length === 0) {
    return args.evidencePlan;
  }

  const strategyPhrase = hintedStrategies.length > 0 ? `strategies ${hintedStrategies.join(", ")}` : null;
  const symbolPhrase = hintedSymbols.length > 0 ? `symbols ${hintedSymbols.join(", ")}` : null;

  return {
    ...args.evidencePlan,
    focusStrategies: mergePriorityList(hintedStrategies, args.evidencePlan.focusStrategies),
    focusSymbols: mergePriorityList(hintedSymbols, args.evidencePlan.focusSymbols),
    rationale: [
      `Transcript research bias favors ${[strategyPhrase, symbolPhrase].filter(Boolean).join(" on ")}.`,
      args.evidencePlan.rationale
    ].join(" ")
  };
}

function candidateClearsTradabilityThreshold(candidate: StrategyCandidate): boolean {
  if (candidate.directionalBias === "flat") {
    return false;
  }

  if (candidate.expectedValueScore <= 0 || candidate.regimeConfidence < 0.5) {
    return false;
  }

  if (candidate.resilienceScore < 0.45) {
    return false;
  }

  return candidate.strategyTrades >= 3 || candidate.convexityScore >= 0.72;
}

function requiredPromotionTrades(phase: LabConfig["accountPhase"]): number {
  return phase === "funded" ? 12 : 8;
}

function buildEvidencePlan(args: {
  phase: LabConfig["accountPhase"];
  deployableNow: boolean;
  selectedProfileId: string | null;
  selectedProfileDescription: string | null;
  selectedTestTrades: number;
  failedChecks: string[];
  rankedCandidates: StrategyCandidate[];
}): {
  mode: "promotion-ready" | "evidence-build" | "repair";
  laneDirective: "paper-trade" | "concentrate-best-edge" | "keep-mixed" | "standby";
  shortfallTrades: number;
  focusStrategies: string[];
  focusSymbols: string[];
  rationale: string;
  strongestCandidate: {
    strategyId: string;
    symbol: string;
    expectedValueScore: number;
    resilienceScore: number;
    convexityScore: number;
  } | null;
} {
  const positiveCandidates = args.rankedCandidates.filter((candidate) =>
    candidate.directionalBias !== "flat"
    && candidate.expectedValueScore > 0
    && candidate.resilienceScore >= 0.45
  );
  const strongestCandidate = positiveCandidates[0] ?? null;
  const requiredTrades = requiredPromotionTrades(args.phase);
  const shortfallTrades = Math.max(0, requiredTrades - args.selectedTestTrades);
  const repairChecks = args.failedChecks.filter((check) => check !== "testTradeCount" && check !== "scoreStability");

  if (args.deployableNow && strongestCandidate) {
    return {
      mode: "promotion-ready",
      laneDirective: "paper-trade",
      shortfallTrades: 0,
      focusStrategies: [strongestCandidate.strategyId],
      focusSymbols: [strongestCandidate.symbol],
      rationale: `Promotion is live. Route founder attention to ${strongestCandidate.strategyId} on ${strongestCandidate.symbol}.`,
      strongestCandidate: {
        strategyId: strongestCandidate.strategyId,
        symbol: strongestCandidate.symbol,
        expectedValueScore: strongestCandidate.expectedValueScore,
        resilienceScore: strongestCandidate.resilienceScore,
        convexityScore: strongestCandidate.convexityScore
      }
    };
  }

  if (strongestCandidate && repairChecks.length === 0) {
    const focusStrategies = Array.from(new Set(positiveCandidates.slice(0, 3).map((candidate) => candidate.strategyId)));
    const focusSymbols = Array.from(new Set(positiveCandidates.slice(0, 3).map((candidate) => candidate.symbol)));

    return {
      mode: "evidence-build",
      laneDirective: "concentrate-best-edge",
      shortfallTrades,
      focusStrategies,
      focusSymbols,
      rationale: `${args.selectedProfileId ?? args.selectedProfileDescription ?? "Selected profile"} has a positive resilient edge, but promotion is still blocked by thin evidence. Concentrate shadow observation on ${focusStrategies.join(", ")} across ${focusSymbols.join(", ")} until the trade-count shortfall closes.`,
      strongestCandidate: {
        strategyId: strongestCandidate.strategyId,
        symbol: strongestCandidate.symbol,
        expectedValueScore: strongestCandidate.expectedValueScore,
        resilienceScore: strongestCandidate.resilienceScore,
        convexityScore: strongestCandidate.convexityScore
      }
    };
  }

  return {
    mode: "repair",
    laneDirective: positiveCandidates.length > 1 ? "keep-mixed" : "standby",
    shortfallTrades,
    focusStrategies: Array.from(new Set(positiveCandidates.slice(0, 2).map((candidate) => candidate.strategyId))),
    focusSymbols: Array.from(new Set(positiveCandidates.slice(0, 2).map((candidate) => candidate.symbol))),
    rationale: positiveCandidates.length > 0
      ? "A few candidates remain interesting, but the machine still has material failures beyond evidence depth. Keep the mix narrow until the repair checks clear."
      : "No resilient positive edge is active. Keep all lanes in guarded standby while the strategy stack is repaired.",
    strongestCandidate: strongestCandidate
      ? {
          strategyId: strongestCandidate.strategyId,
          symbol: strongestCandidate.symbol,
          expectedValueScore: strongestCandidate.expectedValueScore,
          resilienceScore: strongestCandidate.resilienceScore,
          convexityScore: strongestCandidate.convexityScore
        }
      : null
  };
}

export async function buildDailyStrategyPlan(args: {
  bars: Bar[];
  baseConfig: LabConfig;
  newsGate: NewsGate;
  researchStrategyFeed?: FuturesResearchStrategyFeed | null;
}): Promise<{
  report: ReturnType<typeof buildAgenticFundReport>;
  selection: {
    mode: "demo-paper-ready" | "research-only";
    selectedProfileId: string | null;
    selectedProfileDescription: string | null;
    enabledStrategies: string[];
    configuredStrategyCandidates: StrategyCandidate[];
    strategyRoles: Array<{ strategyId: string; role: string }>;
    preferredSymbols: string[];
    activeFamilies: string[];
    whyThisProfile: {
      score?: number;
      scoreStability?: number;
      testNetR?: number;
      testTrades?: number;
      deployable: boolean;
    };
    whyNotTrading: string[];
    regimeAssessments: SymbolRegimeAssessment[];
    rankedCandidates: StrategyCandidate[];
    selectedExecutionPlan: {
      action: "paper-trade" | "stand-down";
      reason: string;
      candidate: StrategyCandidate | null;
    };
    councilDecision: StrategyCouncilDecision;
    decisionFlow: string[];
    intradayExecutionRule: string[];
    evidencePlan: {
      mode: "promotion-ready" | "evidence-build" | "repair";
      laneDirective: "paper-trade" | "concentrate-best-edge" | "keep-mixed" | "standby";
      shortfallTrades: number;
      focusStrategies: string[];
      focusSymbols: string[];
      rationale: string;
      strongestCandidate: {
        strategyId: string;
        symbol: string;
        expectedValueScore: number;
        resilienceScore: number;
        convexityScore: number;
      } | null;
    };
    researchStrategyFeed: {
      preferredStrategies: string[];
      preferredSymbols: string[];
      preferredSessions: string[];
      topStrategyTitles: string[];
    } | null;
  };
}> {
  const scopedBars = filterBarsToAllowedSymbols({
    bars: args.bars,
    allowedSymbols: args.baseConfig.guardrails.allowedSymbols
  });
  const research = await runWalkforwardResearch({
    ...args,
    bars: scopedBars
  });
  const report = buildAgenticFundReport({
    research,
    config: args.baseConfig
  });

  const selected = research.deployableWinner ?? research.winner;
  const selectedProfile = selected
    ? RESEARCH_PROFILES.find((profile) => profile.id === selected.profileId)
    : null;
  const selectedConfig = selectedProfile ? mergeProfile(args.baseConfig, selectedProfile) : args.baseConfig;
  const selectedBudget = research.deployableFamilyBudget ?? research.recommendedFamilyBudget;
  const regimeAssessments = classifyLatestSessionRegimes({
    bars: scopedBars,
    config: selectedConfig,
    allowedSymbols: selectedConfig.guardrails.allowedSymbols
  });
  const rankedCandidates = selected
    ? buildExpectedValueSurface({
        summary: selected.testSummary,
        enabledStrategies: selectedConfig.enabledStrategies,
        allowedSymbols: selectedConfig.guardrails.allowedSymbols,
        activeFamilies: selectedBudget?.activeFamilies ?? [],
        regimeAssessments
      }).slice(0, 8)
    : [];
  const configuredStrategyCandidates = selected
    ? buildExpectedValueSurface({
        summary: selected.testSummary,
        enabledStrategies: args.baseConfig.enabledStrategies,
        allowedSymbols: args.baseConfig.guardrails.allowedSymbols,
        activeFamilies: selectedBudget?.activeFamilies ?? [],
        regimeAssessments
      }).slice(0, 16)
    : [];
  const tradableCandidate = rankedCandidates.find(candidateClearsTradabilityThreshold) ?? null;
  const topCandidate = tradableCandidate ?? rankedCandidates[0] ?? null;
  const candidateIsTradable = Boolean(
    research.deployableWinner &&
    topCandidate &&
    candidateClearsTradabilityThreshold(topCandidate)
  );
  const baseSelectedExecutionPlan = candidateIsTradable && topCandidate
    ? {
        action: "paper-trade" as const,
        reason: `Deployable winner is live, and ${topCandidate.strategyId} on ${topCandidate.symbol} is the best regime-aligned candidate with EV ${topCandidate.expectedValueScore.toFixed(2)}.`,
        candidate: topCandidate
      }
    : {
        action: "stand-down" as const,
        reason: research.deployableWinner
          ? (topCandidate
            ? `No candidate cleared the final tradability threshold. Best candidate was ${topCandidate.strategyId} on ${topCandidate.symbol} with EV ${topCandidate.expectedValueScore.toFixed(2)}, resilience ${topCandidate.resilienceScore.toFixed(2)}, convexity ${topCandidate.convexityScore.toFixed(2)}, and regime confidence ${topCandidate.regimeConfidence.toFixed(2)}.`
            : "No ranked candidates survived the regime and expected-value screen.")
          : "No profile cleared the promotion gate, so the engine remains research-only for the day.",
        candidate: null
      };
  const councilDecision = buildStrategyCouncilDecision({
    report,
    candidate: topCandidate,
    researchStrategyFeed: args.researchStrategyFeed,
    selectedExecutionAction: baseSelectedExecutionPlan.action,
    selectedExecutionReason: baseSelectedExecutionPlan.reason
  });
  const selectedExecutionPlan = councilDecision.portfolioManager.action === "paper-trade"
    ? baseSelectedExecutionPlan
    : {
        action: "stand-down" as const,
        reason: councilDecision.portfolioManager.rationale,
        candidate: null
      };
  const baseEvidencePlan = buildEvidencePlan({
    phase: args.baseConfig.accountPhase,
    deployableNow: report.deployableNow,
    selectedProfileId: selected?.profileId ?? null,
    selectedProfileDescription: selected?.description ?? null,
    selectedTestTrades: selected?.testSummary.totalTrades ?? 0,
    failedChecks: report.failedChecks,
    rankedCandidates
  });
  const evidencePlan = applyResearchFeedToEvidencePlan({
    evidencePlan: baseEvidencePlan,
    researchStrategyFeed: args.researchStrategyFeed,
    availableStrategies: selectedConfig.enabledStrategies,
    availableSymbols: selectedConfig.guardrails.allowedSymbols
  });
  const preferredSymbols = mergePriorityList(
    (args.researchStrategyFeed?.preferredSymbols ?? []).filter((symbol) => selectedConfig.guardrails.allowedSymbols.includes(symbol)),
    selected
      ? buildPreferredSymbols({
          allowedSymbols: selectedConfig.guardrails.allowedSymbols,
          activeFamilies: selectedBudget?.activeFamilies ?? [],
          symbolSummary: selected.testSummary.bySymbol
        })
      : []
  );

  return {
    report,
    selection: {
      mode: research.deployableWinner ? "demo-paper-ready" : "research-only",
      selectedProfileId: selected?.profileId ?? null,
      selectedProfileDescription: selected?.description ?? null,
      enabledStrategies: selectedConfig.enabledStrategies,
      configuredStrategyCandidates,
      strategyRoles: selectedConfig.enabledStrategies.map((strategyId) => ({
        strategyId,
        role: strategyRole(strategyId)
      })),
      preferredSymbols,
      activeFamilies: selectedBudget?.activeFamilies ?? [],
      whyThisProfile: {
        score: selected?.score,
        scoreStability: selected?.scoreStability,
        testNetR: selected?.testSummary.netTotalR,
        testTrades: selected?.testSummary.totalTrades,
        deployable: research.deployableWinner !== null
      },
      whyNotTrading: research.deployableWinner ? [] : report.issues.map((issue) => issue.summary),
      regimeAssessments,
      rankedCandidates,
      selectedExecutionPlan,
      councilDecision,
      decisionFlow: [
        "Run walk-forward research across every profile, including ICT-enabled profiles.",
        "Penalize sparse and unstable profiles so low-sample winners do not float to the top.",
        "Apply the promotion gate. If no profile passes, stay in research-only mode.",
        "Run a structured bull/bear/risk/portfolio council. A risk veto downgrades execution to shadow observation or standby.",
        "Use the active family budget and positive symbol contribution to narrow the watchlist.",
        ...(args.researchStrategyFeed
          ? [`Blend the latest transcript-derived strategy feed into lane focus using ${args.researchStrategyFeed.preferredStrategies.join(", ") || "current"} hints.`]
          : []),
        "Classify the latest session regime for each allowed symbol, then rank strategy-symbol pairs by expected value, regime fit, and family-budget alignment.",
        "During the session, let all enabled strategies propose signals, then take only the highest-confidence signal that survives hard guardrails and news checks."
      ],
      intradayExecutionRule: [
        "No strategy is allowed to trade outside the configured session and flat-cutoff windows.",
        "RR, contract size, daily loss, and consecutive-loss bounds are enforced before entry.",
        "If multiple strategies fire on the same bar, the ensemble prefers the candidate with the best expected-value and regime-fit ranking before using raw signal confidence as a tie-breaker.",
        "If no profile is deployable, the correct action for the day is to stand down and keep iterating."
      ],
      evidencePlan,
      researchStrategyFeed: args.researchStrategyFeed
        ? {
            preferredStrategies: args.researchStrategyFeed.preferredStrategies,
            preferredSymbols: args.researchStrategyFeed.preferredSymbols,
            preferredSessions: args.researchStrategyFeed.preferredSessions,
            topStrategyTitles: args.researchStrategyFeed.topStrategyTitles
          }
        : null
    }
  };
}
