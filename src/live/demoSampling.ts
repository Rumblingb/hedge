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
  sampleSequence: number;
}): string {
  const pool = args.preferredSymbols.length > 0 ? args.preferredSymbols : args.allowedSymbols;
  if (pool.length === 0) {
    return "NQ";
  }

  const index = (args.sampleSequence + args.lane.slot - 1) % pool.length;
  return pool[index] ?? pool[0] ?? "NQ";
}

export function buildDemoStrategySampleSnapshot(args: {
  ts: string;
  sampleSequence: number;
  lanes: DemoAccountStrategyLane[];
  candidates: StrategyCandidate[];
  preferredSymbols: string[];
  allowedSymbols: string[];
  deployableNow: boolean;
  whyNotTrading: string[];
}): DemoStrategySampleSnapshot {
  const strategyCandidates = args.candidates.reduce<Record<string, StrategyCandidate[]>>((acc, candidate) => {
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
    const selected = group.length > 0
      ? group[(args.sampleSequence + occurrence) % group.length] ?? group[0]
      : null;
    const focusSymbol = selected?.symbol ?? pickFallbackSymbol({
      lane,
      preferredSymbols: args.preferredSymbols,
      allowedSymbols: args.allowedSymbols,
      sampleSequence: args.sampleSequence
    });
    const action = selected && selected.directionalBias !== "flat" && selected.expectedValueScore > 0
      ? "shadow-observe"
      : "standby";
    const rationale = selected
      ? `${selected.strategyId} sampled on ${selected.symbol} (${selected.regime}, EV ${selected.expectedValueScore.toFixed(2)}, confidence ${selected.regimeConfidence.toFixed(2)}). ${args.deployableNow ? "Promotion gate is green, but Topstep remains read-only so this stays shadow-only." : `Promotion gate still failing: ${(args.whyNotTrading[0] ?? "keep iterating")}`}`
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
    sampledStrategies: Array.from(new Set(lanes.map((lane) => lane.primaryStrategy).filter(Boolean))) as string[],
    lanes
  };
}
