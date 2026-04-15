import type { Bar, LabConfig } from "../domain.js";
import type { NewsGate } from "../news/base.js";
import { buildAgenticFundReport } from "./agenticFund.js";
import type { StrategyCandidate } from "./expectedValueSurface.js";
import { buildExpectedValueSurface } from "./expectedValueSurface.js";
import type { SymbolRegimeAssessment } from "./regime.js";
import { classifyLatestSessionRegimes } from "./regime.js";
import { runWalkforwardResearch } from "./walkforward.js";
import { RESEARCH_PROFILES, mergeProfile } from "../research/profiles.js";
import { getMarketCategory } from "../utils/markets.js";

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

export async function buildDailyStrategyPlan(args: {
  bars: Bar[];
  baseConfig: LabConfig;
  newsGate: NewsGate;
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
    decisionFlow: string[];
    intradayExecutionRule: string[];
  };
}> {
  const research = await runWalkforwardResearch(args);
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
    bars: args.bars,
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
  const topCandidate = rankedCandidates[0] ?? null;
  const candidateIsTradable = Boolean(
    research.deployableWinner &&
    topCandidate &&
    topCandidate.directionalBias !== "flat" &&
    topCandidate.expectedValueScore > 0 &&
    topCandidate.regimeConfidence >= 0.5
  );
  const preferredSymbols = selected
    ? buildPreferredSymbols({
        allowedSymbols: selectedConfig.guardrails.allowedSymbols,
        activeFamilies: selectedBudget?.activeFamilies ?? [],
        symbolSummary: selected.testSummary.bySymbol
      })
    : [];

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
      selectedExecutionPlan: candidateIsTradable && topCandidate
        ? {
            action: "paper-trade",
            reason: `Deployable winner is live, and ${topCandidate.strategyId} on ${topCandidate.symbol} is the best regime-aligned candidate with EV ${topCandidate.expectedValueScore.toFixed(2)}.`,
            candidate: topCandidate
          }
        : {
            action: "stand-down",
            reason: research.deployableWinner
              ? (topCandidate
                ? `No candidate cleared the final tradability threshold. Best candidate was ${topCandidate.strategyId} on ${topCandidate.symbol} with EV ${topCandidate.expectedValueScore.toFixed(2)} and regime confidence ${topCandidate.regimeConfidence.toFixed(2)}.`
                : "No ranked candidates survived the regime and expected-value screen.")
              : "No profile cleared the promotion gate, so the engine remains research-only for the day.",
            candidate: null
          },
      decisionFlow: [
        "Run walk-forward research across every profile, including ICT-enabled profiles.",
        "Penalize sparse and unstable profiles so low-sample winners do not float to the top.",
        "Apply the promotion gate. If no profile passes, stay in research-only mode.",
        "Use the active family budget and positive symbol contribution to narrow the watchlist.",
        "Classify the latest session regime for each allowed symbol, then rank strategy-symbol pairs by expected value, regime fit, and family-budget alignment.",
        "During the session, let all enabled strategies propose signals, then take only the highest-confidence signal that survives hard guardrails and news checks."
      ],
      intradayExecutionRule: [
        "No strategy is allowed to trade outside the configured session and flat-cutoff windows.",
        "RR, contract size, daily loss, and consecutive-loss bounds are enforced before entry.",
        "If multiple strategies fire on the same bar, the ensemble prefers the candidate with the best expected-value and regime-fit ranking before using raw signal confidence as a tie-breaker.",
        "If no profile is deployable, the correct action for the day is to stand down and keep iterating."
      ]
    }
  };
}
