/**
 * Strategy Correlation Matrix
 *
 * Tracks rolling 20-day Pearson correlation between all 8 strategies'
 * daily PnL streams. When pairwise correlation exceeds 0.7, the
 * correlated group gets an exposure cap via a penalty multiplier.
 *
 * Lifecycle:
 * - pushDailyPnl(strategyId, pnlR): called after each trading day to
 *   advance the rolling window.
 * - getCorrelationPenalty(strategyId, activePositions): returns a
 *   penalty multiplier in [0, 1] for the given strategy, considering
 *   which other strategies are currently positioned.
 */

import { SUPPORTED_STRATEGY_IDS, type SupportedStrategyId } from "../domain.js";

// ---------------------------------------------------------------------------
// Configuration
// ---------------------------------------------------------------------------

const CORRELATION_WINDOW = 20; // rolling days
const CORRELATION_THRESHOLD = 0.7; // above this, capping kicks in
const MAX_GROUP_EXPOSURE = 2; // at most N strategies can be active in a correlated group
const FLOOR_PENALTY = 0.35; // worst-case penalty multiplier

// ---------------------------------------------------------------------------
// State – single rolling ring-buffer per strategy
// ---------------------------------------------------------------------------

type StrategyId = SupportedStrategyId;

interface PnlRing {
  buffer: number[];
  pos: number;
  filled: number;
}

const pnlRings = new Map<StrategyId, PnlRing>();

function getRing(id: StrategyId): PnlRing {
  let ring = pnlRings.get(id);
  if (!ring) {
    ring = { buffer: new Array(CORRELATION_WINDOW).fill(0), pos: 0, filled: 0 };
    pnlRings.set(id, ring);
  }
  return ring;
}

function ringValues(ring: PnlRing): number[] {
  if (ring.filled < CORRELATION_WINDOW) {
    return ring.buffer.slice(0, ring.filled);
  }
  // unwrap: from pos to end, then start to pos
  const out = new Array<number>(CORRELATION_WINDOW);
  for (let i = 0; i < CORRELATION_WINDOW; i++) {
    out[i] = ring.buffer[(ring.pos + i) % CORRELATION_WINDOW];
  }
  return out;
}

// ---------------------------------------------------------------------------
// Public: push daily PnL
// ---------------------------------------------------------------------------

export function recordDailyPnl(strategyId: StrategyId, pnlR: number): void {
  const ring = getRing(strategyId);
  ring.buffer[ring.pos] = pnlR;
  ring.pos = (ring.pos + 1) % CORRELATION_WINDOW;
  if (ring.filled < CORRELATION_WINDOW) ring.filled++;
}

// ---------------------------------------------------------------------------
// Pearson correlation between two arrays of equal length
// ---------------------------------------------------------------------------

function pearsonR(a: number[], b: number[]): number {
  const n = a.length;
  if (n < 3) return 0;

  let sumA = 0, sumB = 0;
  for (let i = 0; i < n; i++) {
    sumA += a[i];
    sumB += b[i];
  }
  const meanA = sumA / n;
  const meanB = sumB / n;

  let cov = 0, varA = 0, varB = 0;
  for (let i = 0; i < n; i++) {
    const da = a[i] - meanA;
    const db = b[i] - meanB;
    cov += da * db;
    varA += da * da;
    varB += db * db;
  }

  const denom = Math.sqrt(varA * varB);
  if (denom < 1e-12) return 0;
  return cov / denom;
}

// ---------------------------------------------------------------------------
// Single pairwise correlation lookup (cached via the full matrix)
// ---------------------------------------------------------------------------

export function getPairwiseCorrelation(
  strategyA: StrategyId,
  strategyB: StrategyId
): number {
  if (strategyA === strategyB) return 1;
  const ringA = getRing(strategyA);
  const ringB = getRing(strategyB);
  const valsA = ringValues(ringA);
  const valsB = ringValues(ringB);
  if (valsA.length < 3 || valsB.length < 3) return 0;
  const len = Math.min(valsA.length, valsB.length);
  return pearsonR(valsA.slice(-len), valsB.slice(-len));
}

// ---------------------------------------------------------------------------
// Active-signal correlation penalty for position sizing
// ---------------------------------------------------------------------------

/**
 * Compute a penalty factor based on pairwise correlations among currently
 * active signals. Only same-symbol signal pairs are considered.
 *
 * @returns penalty in [0.3, 1.0] — 1.0 means no correlation penalty,
 *          0.3 is the floor for highly correlated simultaneous signals.
 */
export function getActiveCorrelationPenalty(
  activeSignals: Array<{ strategyId: string; symbol: string }>
): number {
  if (activeSignals.length < 2) return 1;

  let penalty = 1;
  const n = activeSignals.length;

  for (let i = 0; i < n; i++) {
    for (let j = i + 1; j < n; j++) {
      const sigA = activeSignals[i];
      const sigB = activeSignals[j];

      // Only penalize same-symbol pairs
      if (sigA.symbol !== sigB.symbol) continue;

      const corr = getPairwiseCorrelation(
        sigA.strategyId as StrategyId,
        sigB.strategyId as StrategyId
      );

      if (corr > 0.5) {
        penalty *= 1 - (corr - 0.5);
      }
    }
  }

  return Math.max(penalty, 0.3);
}

// ---------------------------------------------------------------------------
// Pairwise correlation matrix (lazy-computed from ring buffers)
// ---------------------------------------------------------------------------

function pairwiseCorrelation(): Map<StrategyId, Map<StrategyId, number>> {
  const ids = [...SUPPORTED_STRATEGY_IDS];
  const matrix = new Map<StrategyId, Map<StrategyId, number>>();

  for (const idA of ids) {
    const ringA = getRing(idA);
    const valsA = ringValues(ringA);
    if (valsA.length < 3) continue;

    const row = new Map<StrategyId, number>();
    matrix.set(idA, row);

    for (const idB of ids) {
      if (idA === idB) {
        row.set(idB, 1);
        continue;
      }
      const ringB = getRing(idB);
      const valsB = ringValues(ringB);
      if (valsB.length < 3) {
        row.set(idB, 0);
        continue;
      }
      // align to the minimum length
      const len = Math.min(valsA.length, valsB.length);
      row.set(idB, pearsonR(valsA.slice(-len), valsB.slice(-len)));
    }
  }

  return matrix;
}

// ---------------------------------------------------------------------------
// Find the correlated "neighbourhood" of a strategy (including itself)
// ---------------------------------------------------------------------------

function correlatedGroup(
  strategyId: StrategyId,
  matrix: Map<StrategyId, Map<StrategyId, number>>
): Set<StrategyId> {
  const group = new Set<StrategyId>();
  const stack: StrategyId[] = [strategyId];

  while (stack.length > 0) {
    const current = stack.pop()!;
    if (group.has(current)) continue;
    group.add(current);

    const row = matrix.get(current);
    if (!row) continue;

    for (const [other, r] of row) {
      if (!group.has(other) && r > CORRELATION_THRESHOLD) {
        stack.push(other);
      }
    }
  }

  return group;
}

// ---------------------------------------------------------------------------
// Exposure cap: count how many strategies in the correlated group already
// have active positions, and compute the penalty.
// ---------------------------------------------------------------------------

export function getCorrelationPenalty(
  strategyId: StrategyId,
  activePositionStrategyIds: StrategyId[]
): number {
  const matrix = pairwiseCorrelation();
  const group = correlatedGroup(strategyId, matrix);

  // How many group members already have active positions?
  const alreadyActive = activePositionStrategyIds.filter((id) => group.has(id)).length;

  // If we'd add this strategy, how many would that be?
  const wouldBe = alreadyActive + (activePositionStrategyIds.includes(strategyId) ? 0 : 1);

  if (wouldBe <= MAX_GROUP_EXPOSURE) return 1;

  // Penalty scales with how far over the cap we are
  const excess = wouldBe - MAX_GROUP_EXPOSURE;
  const penalty = Math.max(FLOOR_PENALTY, 1 - excess * (1 - FLOOR_PENALTY) / MAX_GROUP_EXPOSURE);
  return penalty;
}

// ---------------------------------------------------------------------------
// Full correlation matrix snapshot for diagnostics
// ---------------------------------------------------------------------------

export interface CorrelationSnapshot {
  timestamp: string;
  matrix: Record<StrategyId, Record<StrategyId, number>>;
  threshold: number;
  groups: Array<{ members: StrategyId[]; avgCorrelation: number }>;
}

export function getCorrelationSnapshot(): CorrelationSnapshot {
  const matrix = pairwiseCorrelation();
  const ids = [...SUPPORTED_STRATEGY_IDS];

  // Build JSON-safe matrix
  const mat: Record<string, Record<string, number>> = {};
  for (const idA of ids) {
    const row: Record<string, number> = {};
    const inner = matrix.get(idA);
    for (const idB of ids) {
      row[idB] = inner?.get(idB) ?? 0;
    }
    mat[idA] = row;
  }

  // Identify correlated groups (connected components above threshold)
  const visited = new Set<string>();
  const groups: Array<{ members: StrategyId[]; avgCorrelation: number }> = [];

  for (const id of ids) {
    if (visited.has(id)) continue;
    const group = correlatedGroup(id, matrix);
    if (group.size <= 1) {
      visited.add(id);
      continue;
    }

    const members = [...group] as StrategyId[];
    for (const m of members) visited.add(m);

    // Average correlation within the group
    let sumR = 0, count = 0;
    for (const a of members) {
      const row = matrix.get(a);
      for (const b of members) {
        if (a !== b) {
          sumR += row?.get(b) ?? 0;
          count++;
        }
      }
    }
    groups.push({
      members,
      avgCorrelation: count > 0 ? sumR / count : 0
    });
  }

  return {
    timestamp: new Date().toISOString(),
    matrix: mat as Record<StrategyId, Record<StrategyId, number>>,
    threshold: CORRELATION_THRESHOLD,
    groups
  };
}

// ---------------------------------------------------------------------------
// Reset state (for backtests / fresh runs)
// ---------------------------------------------------------------------------

export function resetCorrelationState(): void {
  pnlRings.clear();
}
