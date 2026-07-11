import type { StrategyCandidate } from "../engine/expectedValueSurface.js";
import type { DemoAccountStrategyLane } from "./demoAccounts.js";

export interface DemoStrategySampleLane {
  accountId: string;
  label: string | null;
  slot: number;
  primaryStrategy: string | null;
  strategies: string[];
  focusSymbol: string;
  action: "shadow-observe" | "standby";
  rationale: string;
  candidate: {
    symbol: string;
    strategyId: string;
    regime: string;
    directionalBias: string;
    expectedValueScore: number;
    regimeConfidence: number;
  } | null;
  alternatives: Array<{
    symbol: string;
    strategyId: string;
    expectedValueScore: number;
  }>;
}

export interface DemoStrategySampleSnapshot {
  ts: string;
  sampleSequence: number;
  laneCount: number;
  sampledStrategies: string[];
  lanes: DemoStrategySampleLane[];
}

function pickFallbackSymbol(args: {
  lane: DemoAccountStrategyLane;
  preferredSymbols: string[];
  allowedSymbols: string[];
  availableSymbols?: string[];
  sampleSequence: number;
  deployableNow: boolean;
}): string {
  const availableSet = args.availableSymbols && args.availableSymbols.length > 0
    ? new Set(args.availableSymbols)
    : null;
  const eligiblePreferred = availableSet
    ? args.preferredSymbols.filter((symbol) => availableSet.has(symbol))
    : args.preferredSymbols;
  const eligibleAllowed = availableSet
    ? args.allowedSymbols.filter((symbol) => availableSet.has(symbol))
    : args.allowedSymbols;
  const pool = args.deployableNow && eligiblePreferred.length > 0
    ? eligiblePreferred
    : (eligibleAllowed.length > 0 ? eligibleAllowed : args.allowedSymbols);
  if (pool.length === 0) {
    return "NQ";
  }

  const index = (args.sampleSequence + args.lane.slot - 1) % pool.length;
  return pool[index] ?? pool[0] ?? "NQ";
}

function chooseCandidateForLane(args: {
  group: StrategyCandidate[];
  occurrence: number;
  rotationSymbol: string;
  sampleSequence: number;
  deployableNow: boolean;
}): StrategyCandidate | null {
  const sorted = [...args.group].sort((left, right) =>
    right.expectedValueScore - left.expectedValueScore
    || right.resilienceScore - left.resilienceScore
    || right.convexityScore - left.convexityScore
  );
  if (sorted.length === 0) {
    return null;
  }

  if (!args.deployableNow) {
    const positive = sorted.filter((candidate) =>
      candidate.expectedValueScore > 0 && candidate.resilienceScore >= 0.45
    );
    if (positive.length > 0) {
      const anchored = positive.find((candidate) => candidate.symbol === args.rotationSymbol);
      return anchored ?? positive[Math.min(args.occurrence, positive.length - 1)] ?? positive[0] ?? null;
    }
  }

  return (
    (!args.deployableNow
      ? sorted.find((candidate) => candidate.symbol === args.rotationSymbol)
      : null)
    ?? sorted[(args.sampleSequence + args.occurrence) % sorted.length]
    ?? sorted[0]
    ?? null
  );
}

function chooseEvidenceCandidate(args: {
  group: StrategyCandidate[];
  occurrence: number;
  focusStrategies: string[];
  focusSymbols: string[];
}): StrategyCandidate | null {
  const positive = args.group
    .filter((candidate) => candidate.expectedValueScore > 0 && candidate.resilienceScore >= 0.45)
    .sort((left, right) =>
      right.expectedValueScore - left.expectedValueScore
      || right.resilienceScore - left.resilienceScore
      || right.convexityScore - left.convexityScore
    );
  if (positive.length === 0) {
    return null;
  }

  const focused = positive.filter((candidate) =>
    (args.focusStrategies.length === 0 || args.focusStrategies.includes(candidate.strategyId))
    && (args.focusSymbols.length === 0 || args.focusSymbols.includes(candidate.symbol))
  );
  const pool = focused.length > 0 ? focused : positive.slice(0, Math.min(3, positive.length));
  return pool[args.occurrence % pool.length] ?? pool[0] ?? null;
}

export function buildDemoStrategySampleSnapshot(args: {
  ts: string;
  sampleSequence: number;
  lanes: DemoAccountStrategyLane[];
  candidates: StrategyCandidate[];
  preferredSymbols: string[];
  allowedSymbols: string[];
  availableSymbols?: string[];
  deployableNow: boolean;
  whyNotTrading: string[];
  evidencePlan?: {
    mode: "promotion-ready" | "evidence-build" | "repair";
    focusStrategies: string[];
    focusSymbols: string[];
  };
}): DemoStrategySampleSnapshot {
  const availableSet = args.availableSymbols && args.availableSymbols.length > 0
    ? new Set(args.availableSymbols)
    : null;
  const strategyCandidates = args.candidates.reduce<Record<string, StrategyCandidate[]>>((acc, candidate) => {
    if (availableSet && !availableSet.has(candidate.symbol)) {
      return acc;
    }
    const existing = acc[candidate.strategyId] ?? [];
    existing.push(candidate);
    acc[candidate.strategyId] = existing;
    return acc;
  }, {});
  const strategyOccurrences = new Map<string, number>();

  const lanes = args.lanes.map((lane) => {
    const primaryStrategy = lane.primaryStrategy;
    const group = primaryStrategy ? (strategyCandidates[primaryStrategy] ?? []) : [];
    const occurrence = primaryStrategy
      ? (strategyOccurrences.get(primaryStrategy) ?? 0)
      : 0;
    if (primaryStrategy) {
      strategyOccurrences.set(primaryStrategy, occurrence + 1);
    }
    const rotationSymbol = pickFallbackSymbol({
      lane,
      preferredSymbols: args.preferredSymbols,
      allowedSymbols: args.allowedSymbols,
      availableSymbols: args.availableSymbols,
      sampleSequence: args.sampleSequence,
      deployableNow: args.deployableNow
    });
    const selectedPrimary = chooseCandidateForLane({
      group,
      occurrence,
      rotationSymbol,
      sampleSequence: args.sampleSequence,
      deployableNow: args.deployableNow
    });
    const shouldBorrowForEvidence = Boolean(
      !args.deployableNow
      && args.evidencePlan?.mode === "evidence-build"
      && (
        !selectedPrimary
        || selectedPrimary.expectedValueScore <= 0
        || selectedPrimary.resilienceScore < 0.45
      )
    );
    const selected = shouldBorrowForEvidence
      ? chooseEvidenceCandidate({
          group: args.candidates.filter((candidate) =>
            (!availableSet || availableSet.has(candidate.symbol))
            && candidate.directionalBias !== "flat"
          ),
          occurrence,
          focusStrategies: args.evidencePlan?.focusStrategies ?? [],
          focusSymbols: args.evidencePlan?.focusSymbols ?? []
        }) ?? selectedPrimary
      : selectedPrimary;
    const focusSymbol = selected?.symbol ?? rotationSymbol;
    const action = selected && selected.directionalBias !== "flat" && selected.expectedValueScore > 0
      ? "shadow-observe"
      : "standby";
    const rationale = selected
      ? `${selected.strategyId} sampled on ${selected.symbol} (${selected.regime}, EV ${selected.expectedValueScore.toFixed(2)}, confidence ${selected.regimeConfidence.toFixed(2)}). ${shouldBorrowForEvidence && selected.strategyId !== primaryStrategy ? `Primary lane ${primaryStrategy ?? "standby"} has no resilient edge today, so this slot is temporarily reassigned to the strongest evidence-building candidate.` : !args.deployableNow && selected.expectedValueScore > 0 && selected.resilienceScore >= 0.45 ? "Lane concentration stays on the strongest resilient setup while promotion remains gated." : args.deployableNow ? "Promotion gate is green, but Topstep remains read-only so this stays shadow-only." : `Promotion gate still failing: ${(args.whyNotTrading[0] ?? "keep iterating")}`}`
      : `${primaryStrategy ?? "standby"} has no ranked candidate on this cycle. Fallback focus stays on ${focusSymbol} while the lane remains shadow-only.`;

    return {
      accountId: lane.accountId,
      label: lane.label,
      slot: lane.slot,
      primaryStrategy,
      strategies: lane.strategies,
      focusSymbol,
      action,
      rationale,
      candidate: selected
        ? {
            symbol: selected.symbol,
            strategyId: selected.strategyId,
            regime: selected.regime,
            directionalBias: selected.directionalBias,
            expectedValueScore: selected.expectedValueScore,
            regimeConfidence: selected.regimeConfidence
          }
        : null,
      alternatives: group
        .filter((candidate) => candidate !== selected)
        .slice(0, 2)
        .map((candidate) => ({
          symbol: candidate.symbol,
          strategyId: candidate.strategyId,
          expectedValueScore: candidate.expectedValueScore
        }))
    } satisfies DemoStrategySampleLane;
  });

  return {
    ts: args.ts,
    sampleSequence: args.sampleSequence,
    laneCount: lanes.length,
    sampledStrategies: Array.from(new Set(lanes.map((lane) => lane.candidate?.strategyId ?? lane.primaryStrategy).filter(Boolean))) as string[],
    lanes
  };
}
