/**
 * Multi-Factor Strategy Ranking
 *
 * Combines two lightweight statistical engines:
 *
 * 1. ElasticNet regression for feature selection
 *    - L1+L2 regularisation picks which strategy signals carry weight.
 *    - Coordinate descent solver — no external ML dependencies.
 *
 * 2. Bayesian Model Averaging (BMA) for dynamic weight updates
 *    - Maintains a small ensemble of candidate models.
 *    - Posterior model probabilities updated each cycle via BIC.
 *    - Weights the ranked output by model probability.
 *
 * Input:  strategy signal features + historical PnL
 * Output: ranked strategy weights, updated every N bars.
 */

import { SUPPORTED_STRATEGY_IDS, type SupportedStrategyId } from "../domain.js";
import { readFile, mkdir, writeFile } from "node:fs/promises";
import { dirname } from "node:path";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type StrategyId = SupportedStrategyId;

/** A single row of feature data for one bar/timestamp. */
export interface FeatureRow {
  /** Timestamp or bar index for alignment. */
  ts: string;
  /** Per-strategy signal confidence [0, 1]. */
  signals: Record<StrategyId, number>;
  /** Realised forward R-multiple over the outcome horizon. */
  forwardR: number;
}

/** Ranked strategy weight output. */
export interface StrategyWeight {
  strategyId: StrategyId;
  weight: number; // normalised so positive weights sum to 1
  rawCoefficient: number; // before normalisation
  selected: boolean; // feature survived ElasticNet selection
}

/** Aggregate ranking result. */
export interface MultiFactorRanking {
  timestamp: string;
  barIndex: number;
  weights: StrategyWeight[];
  elastiNetLambda: number;
  bmaModelCount: number;
  dominantModelWeight: number;
}

// ---------------------------------------------------------------------------
// Configuration
// ---------------------------------------------------------------------------

const DEFAULT_LAMBDA = 0.15; // L1/L2 trade-off (0 = pure ridge, 1 = pure lasso)
const DEFAULT_ALPHA = 0.5; // elastic net mixing: 0.5 = equal L1+L2
const MAX_ITER = 2000; // coordinate-descent max iterations
const TOLERANCE = 1e-6; // convergence tolerance
const BMA_WINDOW = 5; // how many recent ElasticNet fits to keep in the ensemble
const UPDATE_EVERY_N_BARS = 10; // recalculate every N bars

// ---------------------------------------------------------------------------
// EliteNet: coordinate-descent solver
// ---------------------------------------------------------------------------

/**
 * Standardise a matrix column-wise (zero-mean, unit-variance).
 * Returns [standardised matrix, means, stddevs].
 */
function standardise(
  X: number[][]
): { Xs: number[][]; means: number[]; stds: number[] } {
  const nRows = X.length;
  if (nRows === 0) return { Xs: [], means: [], stds: [] };
  const nCols = X[0].length;

  const means = new Array<number>(nCols).fill(0);
  const stds = new Array<number>(nCols).fill(0);

  for (let i = 0; i < nRows; i++) {
    for (let j = 0; j < nCols; j++) {
      means[j] += X[i][j];
    }
  }
  for (let j = 0; j < nCols; j++) means[j] /= nRows;

  for (let i = 0; i < nRows; i++) {
    for (let j = 0; j < nCols; j++) {
      const d = X[i][j] - means[j];
      stds[j] += d * d;
    }
  }
  for (let j = 0; j < nCols; j++) {
    stds[j] = Math.sqrt(stds[j] / (nRows - 1)) || 1e-12;
  }

  const Xs: number[][] = [];
  for (let i = 0; i < nRows; i++) {
    const row = new Array<number>(nCols);
    for (let j = 0; j < nCols; j++) {
      row[j] = (X[i][j] - means[j]) / stds[j];
    }
    Xs.push(row);
  }

  return { Xs, means, stds };
}

/**
 * Soft-thresholding operator for L1 regularisation.
 */
function softThreshold(z: number, gamma: number): number {
  if (z > gamma) return z - gamma;
  if (z < -gamma) return z + gamma;
  return 0;
}

/**
 * Coordinate-descent ElasticNet.
 *
 * Minimises:  (1/(2n)) * ||y - Xβ||² + λ * (α||β||₁ + (1-α)/2 * ||β||₂²)
 *
 * Returns unscaled coefficients (applied on standardised features).
 */
function elasticNet(
  X: number[][],
  y: number[],
  lambda: number,
  alpha: number,
  maxIter: number = MAX_ITER,
  tol: number = TOLERANCE
): number[] {
  const n = X.length;
  const p = X[0]?.length ?? 0;
  if (n === 0 || p === 0) return new Array(p).fill(0);

  // Pre-compute column norms
  const colNorms = new Array<number>(p).fill(0);
  for (let j = 0; j < p; j++) {
    for (let i = 0; i < n; i++) {
      colNorms[j] += X[i][j] * X[i][j];
    }
  }

  // Residuals
  let beta = new Array<number>(p).fill(0);
  const residuals = [...y];

  const ridgePenalty = lambda * (1 - alpha);
  const lassoPenalty = lambda * alpha;

  for (let iter = 0; iter < maxIter; iter++) {
    let maxDelta = 0;

    for (let j = 0; j < p; j++) {
      // Compute partial residual for column j
      let rho = 0;
      for (let i = 0; i < n; i++) {
        rho += X[i][j] * residuals[i];
      }
      rho = rho / n + beta[j] * (colNorms[j] / n);

      // Update
      const denominator = colNorms[j] / n + ridgePenalty;
      const newBeta = softThreshold(rho, lassoPenalty) / denominator;

      if (Math.abs(newBeta - beta[j]) > maxDelta) {
        maxDelta = Math.abs(newBeta - beta[j]);
      }

      // Update residuals
      if (newBeta !== beta[j]) {
        const delta = newBeta - beta[j];
        for (let i = 0; i < n; i++) {
          residuals[i] -= delta * X[i][j];
        }
        beta[j] = newBeta;
      }
    }

    if (maxDelta < tol) break;
  }

  return beta;
}

// ---------------------------------------------------------------------------
// ElasticNet fit: returns ranked coefficients for strategy features.
// ---------------------------------------------------------------------------

export interface ElasticNetResult {
  coefficients: Record<StrategyId, number>;
  selectedFeatures: StrategyId[];
  intercept: number;
  lambda: number;
  alpha: number;
}

export function fitElasticNet(
  features: FeatureRow[],
  lambda: number = DEFAULT_LAMBDA,
  alpha: number = DEFAULT_ALPHA
): ElasticNetResult {
  const strategyIds = [...SUPPORTED_STRATEGY_IDS];
  const n = features.length;
  if (n < 10) {
    // Not enough data; return zeros.
    return {
      coefficients: Object.fromEntries(strategyIds.map((id) => [id, 0])) as Record<StrategyId, number>,
      selectedFeatures: [],
      intercept: 0,
      lambda,
      alpha
    };
  }

  // Build design matrix X and target vector y
  const X: number[][] = [];
  const y: number[] = [];
  for (const row of features) {
    X.push(strategyIds.map((id) => row.signals[id] ?? 0));
    y.push(row.forwardR);
  }

  // Standardise
  const { Xs, means, stds: xStd } = standardise(X);
  const yMean = y.reduce((a, b) => a + b, 0) / n;
  const yStd = Math.sqrt(y.reduce((s, v) => s + (v - yMean) ** 2, 0) / (n - 1)) || 1e-12;
  const ys = y.map((v) => (v - yMean) / yStd);

  // Fit
  const betaScaled = elasticNet(Xs, ys, lambda, alpha);

  // Un-scale coefficients
  const beta = betaScaled.map((bj, j) => (bj * yStd) / (xStd[j] || 1e-12));
  const intercept = yMean - beta.reduce((s, bj, j) => s + bj * means[j], 0);

  // Build output
  const coefficients: Record<StrategyId, number> = {} as Record<StrategyId, number>;
  const selectedFeatures: StrategyId[] = [];
  for (let j = 0; j < strategyIds.length; j++) {
    const coef = Math.abs(betaScaled[j]) > 1e-8 ? beta[j] : 0;
    coefficients[strategyIds[j]] = coef;
    if (coef !== 0) selectedFeatures.push(strategyIds[j]);
  }

  return { coefficients, selectedFeatures, intercept, lambda, alpha };
}

// ---------------------------------------------------------------------------
// Bayesian Model Averaging
// ---------------------------------------------------------------------------

interface BmaModel {
  /** ElasticNet result for this model. */
  elasticNet: ElasticNetResult;
  /** BIC (lower is better). */
  bic: number;
  /** Posterior model probability (sums to 1 across ensemble). */
  posteriorProbability: number;
  /** Fit timestamp / bar index. */
  barIndex: number;
}

const bmaEnsemble: BmaModel[] = [];

/**
 * Compute the Bayesian Information Criterion for an ElasticNet fit.
 * BIC = n * ln(RSS/n) + k * ln(n)
 */
function computeBIC(features: FeatureRow[], result: ElasticNetResult): number {
  const n = features.length;
  const strategyIds = [...SUPPORTED_STRATEGY_IDS];

  let rss = 0;
  for (const row of features) {
    let pred = result.intercept;
    for (const id of strategyIds) {
      pred += (result.coefficients[id] ?? 0) * (row.signals[id] ?? 0);
    }
    const err = row.forwardR - pred;
    rss += err * err;
  }

  const k = result.selectedFeatures.length + 1; // +1 for intercept
  if (n <= k) return Infinity;

  const sigma2Hat = rss / n;
  if (sigma2Hat <= 0) return -Infinity;

  return n * Math.log(sigma2Hat) + k * Math.log(n);
}

/**
 * Update the BMA ensemble with a new ElasticNet fit.
 * Prunes old models beyond BMA_WINDOW and recomputes posteriors.
 */
function updateBmaEnsemble(
  features: FeatureRow[],
  newFit: ElasticNetResult,
  barIndex: number
): void {
  const bic = computeBIC(features, newFit);

  bmaEnsemble.push({
    elasticNet: newFit,
    bic,
    posteriorProbability: 0,
    barIndex
  });

  // Keep only the most recent BMA_WINDOW models
  while (bmaEnsemble.length > BMA_WINDOW) {
    bmaEnsemble.shift();
  }

  // Compute posterior probabilities from BIC weights
  // p(M|D) ∝ exp(-0.5 * ΔBIC), where ΔBIC = BIC - min(BIC)
  const minBic = Math.min(...bmaEnsemble.map((m) => m.bic));
  const weights = bmaEnsemble.map((m) => Math.exp(-0.5 * (m.bic - minBic)));
  const sumW = weights.reduce((a, b) => a + b, 0) || 1;

  for (let i = 0; i < bmaEnsemble.length; i++) {
    bmaEnsemble[i].posteriorProbability = weights[i] / sumW;
  }
}

// ---------------------------------------------------------------------------
// Ranked weights – combine ElasticNet + BMA
// ---------------------------------------------------------------------------

let lastBarIndex = -Infinity;

/**
 * Compute strategy weights via ElasticNet feature selection,
 * averaged across the BMA ensemble by posterior probability.
 */
export function rankStrategies(
  features: FeatureRow[],
  barIndex: number,
  options: {
    lambda?: number;
    alpha?: number;
  } = {}
): MultiFactorRanking {
  const lambda = options.lambda ?? DEFAULT_LAMBDA;
  const alpha = options.alpha ?? DEFAULT_ALPHA;
  const strategyIds = [...SUPPORTED_STRATEGY_IDS];

  // Fit a new ElasticNet model
  const newFit = fitElasticNet(features, lambda, alpha);
  updateBmaEnsemble(features, newFit, barIndex);
  lastBarIndex = barIndex;

  // BMA-weighted average of coefficients across the ensemble
  const weightedCoefficients = new Map<StrategyId, number>();
  const selectedCount = new Map<StrategyId, number>();

  for (const id of strategyIds) {
    weightedCoefficients.set(id, 0);
    selectedCount.set(id, 0);
  }

  for (const model of bmaEnsemble) {
    const p = model.posteriorProbability;
    for (const id of strategyIds) {
      const coef = model.elasticNet.coefficients[id] ?? 0;
      weightedCoefficients.set(id, (weightedCoefficients.get(id) ?? 0) + p * coef);
      if (coef !== 0) {
        selectedCount.set(id, (selectedCount.get(id) ?? 0) + 1);
      }
    }
  }

  // Build ranked list
  const raw: Array<{ id: StrategyId; coeff: number; selectedCount: number }> = [];
  for (const id of strategyIds) {
    raw.push({
      id,
      coeff: weightedCoefficients.get(id) ?? 0,
      selectedCount: selectedCount.get(id) ?? 0
    });
  }

  // Normalise positive weights so they sum to 1
  const positiveSum = raw
    .filter((r) => r.coeff > 0)
    .reduce((s, r) => s + r.coeff, 0);

  const dominantModelWeight =
    bmaEnsemble.length > 0
      ? Math.max(...bmaEnsemble.map((m) => m.posteriorProbability))
      : 0;

  const weights: StrategyWeight[] = raw.map((r) => ({
    strategyId: r.id,
    weight: positiveSum > 0 && r.coeff > 0 ? r.coeff / positiveSum : 0,
    rawCoefficient: r.coeff,
    // Selected if it appeared in more than half of ensemble models
    selected: r.selectedCount >= Math.ceil(bmaEnsemble.length / 2)
  }));

  // Sort by weight descending
  weights.sort((a, b) => b.weight - a.weight);

  return {
    timestamp: new Date().toISOString(),
    barIndex,
    weights,
    elastiNetLambda: lambda,
    bmaModelCount: bmaEnsemble.length,
    dominantModelWeight
  };
}

// ---------------------------------------------------------------------------
// Live ranking feedback: read trade journal, update weights, persist
// ---------------------------------------------------------------------------

const RANKING_STATE_PATH = ".rumbling-hedge/state/strategy-rankings.latest.json";

/** Half-life in number of trades for exponential performance decay. */
const PERFORMANCE_HALF_LIFE = 20;

interface StrategyPerformance {
  strategyId: string;
  totalTrades: number;
  netR: number;
  winRate: number;
  avgRR: number;
  /** Decay-weighted net R from most recent N trades. */
  decayWeightedNetR: number;
  /** Computed ranking weight in [0.5, 2.0]. */
  rankingWeight: number;
  lastUpdated: string;
}

interface RankingState {
  updated: string;
  journalPath: string;
  totalTradesScanned: number;
  strategies: Record<string, StrategyPerformance>;
}

/** Current in-memory ranking state (loaded from disk on first access). */
let cachedRankingState: RankingState | null = null;

function decayWeight(tradeIndex: number, totalTrades: number): number {
  // tradeIndex 0 = most recent trade, tradeIndex (totalTrades-1) = oldest
  const ageInTrades = totalTrades - 1 - tradeIndex;
  return Math.exp(-Math.LN2 * ageInTrades / PERFORMANCE_HALF_LIFE);
}

/** Strip ensemble prefix like "wctc-ensemble:" to get the base strategy id. */
function baseStrategyId(strategyId: string): string {
  const colonIdx = strategyId.indexOf(":");
  return colonIdx >= 0 ? strategyId.slice(colonIdx + 1) : strategyId;
}

/**
 * Read the trade journal, compute per-strategy performance metrics,
 * apply exponential decay weighting, and write updated rankings to disk.
 *
 * Safe to run repeatedly — idempotent as long as the journal hasn't changed.
 */
export async function updateRankingsFromJournal(journalPath: string): Promise<RankingState> {
  const trades = await readTradeJournal(journalPath);
  if (trades.length === 0) {
    // Return whatever we already have, or a neutral empty state.
    const neutral: RankingState = {
      updated: new Date().toISOString(),
      journalPath,
      totalTradesScanned: 0,
      strategies: {}
    };
    await writeRankingState(neutral);
    cachedRankingState = neutral;
    return neutral;
  }

  // Group trades by base strategy id
  const byStrategy = new Map<string, Array<{ netR: number; idx: number }>>();
  for (let i = 0; i < trades.length; i++) {
    const trade = trades[i];
    const base = baseStrategyId(trade.strategyId);
    const group = byStrategy.get(base) ?? [];
    group.push({ netR: trade.netRMultiple, idx: i });
    byStrategy.set(base, group);
  }

  const strategies: Record<string, StrategyPerformance> = {};

  for (const [strategyId, tradeList] of byStrategy) {
    const n = tradeList.length;
    let totalNetR = 0;
    let wins = 0;
    let totalDecayWeight = 0;
    let weightedNetR = 0;

    for (const t of tradeList) {
      totalNetR += t.netR;
      if (t.netR > 0) wins++;
      const dw = decayWeight(t.idx, trades.length);
      totalDecayWeight += dw;
      weightedNetR += dw * t.netR;
    }

    const winRate = n > 0 ? wins / n : 0;
    const avgRR = n > 0 ? totalNetR / n : 0;
    const decayWeightedNetR = totalDecayWeight > 0 ? weightedNetR / totalDecayWeight : 0;

    strategies[strategyId] = {
      strategyId,
      totalTrades: n,
      netR: totalNetR,
      winRate,
      avgRR,
      decayWeightedNetR,
      rankingWeight: 1.0, // will be computed below
      lastUpdated: new Date().toISOString()
    };
  }

  // Compute ranking weights relative across all strategies.
  // Map decayWeightedNetR to [0.5, 2.0] range.
  const entries = Object.values(strategies);
  if (entries.length > 0) {
    const values = entries.map((s) => s.decayWeightedNetR);
    const minVal = Math.min(...values);
    const maxVal = Math.max(...values);

    for (const s of entries) {
      if (maxVal === minVal) {
        // All strategies have identical performance — neutral weight.
        s.rankingWeight = 1.0;
      } else {
        // Scale normalized [0, 1] to [0.5, 2.0]
        const normalized = (s.decayWeightedNetR - minVal) / (maxVal - minVal);
        s.rankingWeight = clampRank(0.5 + normalized * 1.5);
      }
    }
  }

  const state: RankingState = {
    updated: new Date().toISOString(),
    journalPath,
    totalTradesScanned: trades.length,
    strategies
  };

  await writeRankingState(state);
  cachedRankingState = state;
  return state;
}

async function readTradeJournal(path: string): Promise<Array<{ strategyId: string; netRMultiple: number }>> {
  try {
    const raw = await readFile(path, "utf8");
    return raw
      .split(/\r?\n/)
      .map((line: string) => line.trim())
      .filter(Boolean)
      .map((line: string) => {
        const obj = JSON.parse(line) as Record<string, unknown>;
        return {
          strategyId: String(obj.strategyId ?? ""),
          netRMultiple: Number(obj.netRMultiple ?? 0)
        };
      });
  } catch {
    return [];
  }
}

function clampRank(value: number): number {
  if (value < 0.5) return 0.5;
  if (value > 2.0) return 2.0;
  return Math.round(value * 10000) / 10000; // 4 decimal places
}

async function writeRankingState(state: RankingState): Promise<void> {
  await mkdir(dirname(RANKING_STATE_PATH), { recursive: true });
  await writeFile(RANKING_STATE_PATH, JSON.stringify(state, null, 2), "utf8");
}

/**
 * Load ranking state from disk (or return a neutral default if not yet computed).
 */
export async function loadRankingState(): Promise<RankingState> {
  if (cachedRankingState) return cachedRankingState;
  try {
    const raw = await readFile(RANKING_STATE_PATH, "utf8");
    cachedRankingState = JSON.parse(raw) as RankingState;
    return cachedRankingState;
  } catch {
    const neutral: RankingState = {
      updated: new Date().toISOString(),
      journalPath: "",
      totalTradesScanned: 0,
      strategies: {}
    };
    cachedRankingState = neutral;
    return neutral;
  }
}

/**
 * Returns a ranking weight in [0.5, 2.0] for a given strategy ID.
 * Higher weight = strategy gets more capital / larger position.
 *
 * Loads the on-disk ranking state if not already in memory.
 * Returns the neutral weight (1.0) if no ranking data exists.
 */
export async function getRankingWeight(strategyId: string): Promise<number> {
  const state = await loadRankingState();
  const base = baseStrategyId(strategyId);
  const perf = state.strategies[base];
  if (!perf) return 1.0; // neutral weight for strategies with no data
  return perf.rankingWeight;
}

/**
 * Synchronous variant that uses cached ranking state.
 * Returns 1.0 if no state has been loaded yet.
 */
export function getRankingWeightSync(strategyId: string): number {
  if (!cachedRankingState) return 1.0;
  const base = baseStrategyId(strategyId);
  const perf = cachedRankingState.strategies[base];
  return perf?.rankingWeight ?? 1.0;
}

// ---------------------------------------------------------------------------
// Convenience: check if it's time to update
// ---------------------------------------------------------------------------

export function shouldUpdateRanking(barIndex: number): boolean {
  return barIndex - lastBarIndex >= UPDATE_EVERY_N_BARS;
}

// ---------------------------------------------------------------------------
// Convenience: get a single weight for a strategy
// ---------------------------------------------------------------------------

export function getStrategyWeight(
  rankings: MultiFactorRanking,
  strategyId: StrategyId
): number {
  const entry = rankings.weights.find((w) => w.strategyId === strategyId);
  return entry?.weight ?? 0;
}

// ---------------------------------------------------------------------------
// Reset state (for backtests)
// ---------------------------------------------------------------------------

export function resetRankingState(): void {
  bmaEnsemble.length = 0;
  lastBarIndex = -Infinity;
}
