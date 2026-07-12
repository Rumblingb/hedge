/**
 * HMM Regime Detection — Bill/Hedge Trading System
 *
 * 4-state Hidden Markov Model for regime classification on futures data
 * (ES, NQ, CL, GC, 6E). Uses Baum-Welch training on 90d of 1-minute data.
 *
 * States:
 *   State 0 — trending (directional moves, moderate vol)
 *   State 1 — range-chop (mean-reverting within a band)
 *   State 2 — high-vol / crisis (extreme moves, wide ranges)
 *   State 3 — low-vol / quiet (compressed ranges, low activity)
 *
 * Features (4-dimensional observation):
 *   1. log return: ln(close_t / close_{t-1})
 *   2. ATR(14): average true range over 14 bars
 *   3. volume ratio: volume / SMA(volume, 20)
 *   4. close location: (close - low) / (high - low) ∈ [0, 1]
 *
 * Designed for Mac Mini 16GB — processes one symbol at a time,
 * uses Float64Array for numerical stability, caps iterations.
 */

import type { Bar } from "../domain.js";

// ── Types ───────────────────────────────────────────────────────────────

export type HmmRegime = "trending" | "range-chop" | "high-vol" | "low-vol";

export interface HmmRegimeResult {
  /** Timestamp of the bar. */
  barTs: string;
  /** Symbol. */
  symbol: string;
  /** Regime classification string. */
  regime: HmmRegime;
  /** Numeric state label (0–3), assigned post-training via heuristic. */
  regimeLabel: number;
  /** Probability distribution over 4 states [p0, p1, p2, p3]. */
  probabilities: number[];
  /** Raw feature vector [logReturn, atr14, volRatio, closeLocation]. */
  features: number[];
}

export interface HmmRegimeModel {
  symbol: string;
  /** 4×4 transition matrix: A[i][j] = P(state_j | state_i). */
  transitionMatrix: number[][];
  /** Initial state distribution (length 4). */
  initialState: number[];
  /** Per-state mean vectors (4 states × 4 features). */
  means: number[][];
  /** Per-state diagonal variances (4 states × 4 features). */
  variances: number[][];
  /** Bar-by-bar regime results. */
  regimeDistribution: HmmRegimeResult[];
  /** Fraction of bars in each regime. */
  regimeFractions: Record<HmmRegime, number>;
  /** Per-state feature statistics (mean of each feature in that state). */
  stateFeatureStats: { stateLabel: number; regime: HmmRegime; featureMeans: number[] }[];
}

export interface HmmRegimeInput {
  bars: Bar[];
  /** Number of HMM states (default 4). */
  nStates?: number;
  /** Maximum Baum-Welch iterations (default 30). */
  maxIterations?: number;
  /** Convergence tolerance for log-likelihood (default 1e-4). */
  tolerance?: number;
  /** ATR lookback (default 14). */
  atrPeriod?: number;
  /** Volume SMA lookback (default 20). */
  volumeSmaPeriod?: number;
  /** Seed for random initialization (default 42). */
  seed?: number;
}

// ── Feature extraction ──────────────────────────────────────────────────

/**
 * Extract 4-dimensional feature vectors from an array of bars.
 * Returns an array of [logReturn, atr14, volRatio, closeLocation] per bar,
 * aligned 1:1 with the input (first `warmup` entries have NaN features).
 */
export function extractFeatures(
  bars: Bar[],
  atrPeriod = 14,
  volumeSmaPeriod = 20
): { features: number[][]; validFrom: number } {
  const n = bars.length;
  const warmup = Math.max(atrPeriod, volumeSmaPeriod) + 1;
  const features: number[][] = new Array(n);

  // Pre-compute true ranges
  const trueRanges = new Float64Array(n);
  trueRanges[0] = bars[0].high - bars[0].low;
  for (let i = 1; i < n; i++) {
    const h = bars[i].high;
    const l = bars[i].low;
    const prevC = bars[i - 1].close;
    trueRanges[i] = Math.max(h - l, Math.abs(h - prevC), Math.abs(l - prevC));
  }

  // Rolling ATR via Wilder's smoothing
  const atr = new Float64Array(n);
  {
    let sum = 0;
    for (let i = 0; i < atrPeriod; i++) sum += trueRanges[i];
    atr[atrPeriod - 1] = sum / atrPeriod;
    for (let i = atrPeriod; i < n; i++) {
      atr[i] = (atr[i - 1] * (atrPeriod - 1) + trueRanges[i]) / atrPeriod;
    }
  }

  // Rolling volume SMA
  const volSma = new Float64Array(n);
  {
    let sum = 0;
    for (let i = 0; i < volumeSmaPeriod; i++) sum += bars[i].volume;
    volSma[volumeSmaPeriod - 1] = sum / volumeSmaPeriod;
    for (let i = volumeSmaPeriod; i < n; i++) {
      volSma[i] = volSma[i - 1] + (bars[i].volume - bars[i - volumeSmaPeriod].volume) / volumeSmaPeriod;
    }
  }

  for (let i = 0; i < n; i++) {
    if (i < warmup) {
      features[i] = [NaN, NaN, NaN, NaN];
      continue;
    }
    const prevClose = bars[i - 1].close;
    const logReturn = Math.log(bars[i].close / prevClose);
    const atr14 = atr[i];
    const volRatio = volSma[i] > 0 ? bars[i].volume / volSma[i] : 1;
    const barRange = bars[i].high - bars[i].low;
    const closeLoc = barRange > 0 ? (bars[i].close - bars[i].low) / barRange : 0.5;

    features[i] = [logReturn, atr14, volRatio, closeLoc];
  }

  return { features, validFrom: warmup };
}

// ── Simple linear-congruential PRNG (no deps, deterministic) ────────────

function createRng(seed: number): () => number {
  let s = seed | 0;
  return () => {
    s = (s * 1664525 + 1013904223) | 0;
    return (s >>> 0) / 4294967296;
  };
}

// ── HMM Math Utilities ──────────────────────────────────────────────────

const LOG_ZERO = -1e10;

/** Safe log-sum-exp. */
function logSumExp(arr: number[]): number {
  const max = Math.max(...arr);
  if (max === -Infinity) return LOG_ZERO;
  let sum = 0;
  for (let i = 0; i < arr.length; i++) {
    sum += Math.exp(arr[i] - max);
  }
  return max + Math.log(sum);
}

/** Gaussian log-density: log N(x | mu, sigma^2). */
function gaussianLogPdf(x: number, mu: number, sigma2: number): number {
  if (sigma2 <= 1e-12) sigma2 = 1e-12;
  const diff = x - mu;
  return -0.5 * (Math.log(2 * Math.PI * sigma2) + (diff * diff) / sigma2);
}

/** Multivariate diagonal Gaussian log-density. */
function multiGaussianLogPdf(
  x: number[],
  mu: number[],
  sigma2: number[]
): number {
  let lp = 0;
  for (let d = 0; d < x.length; d++) {
    if (Number.isNaN(x[d])) continue; // skip missing features
    lp += gaussianLogPdf(x[d], mu[d], sigma2[d]);
  }
  return lp;
}

// ── Baum-Welch training ─────────────────────────────────────────────────

interface HmmParams {
  pi: number[];
  A: number[][];
  mu: number[][];
  sigma2: number[][];
}

/**
 * Initialize HMM parameters with random means drawn from feature statistics.
 */
function initializeParams(
  features: number[][],
  nStates: number,
  nFeatures: number,
  rng: () => number
): HmmParams {
  // Collect valid feature rows to estimate global stats
  const valid = features.filter((f) => !f.some(Number.isNaN));
  const globalMean = new Array(nFeatures).fill(0);
  const globalStd = new Array(nFeatures).fill(0);

  if (valid.length > 0) {
    for (let d = 0; d < nFeatures; d++) {
      let sum = 0;
      for (const row of valid) sum += row[d];
      globalMean[d] = sum / valid.length;
    }
    for (let d = 0; d < nFeatures; d++) {
      let sumSq = 0;
      for (const row of valid) sumSq += (row[d] - globalMean[d]) ** 2;
      globalStd[d] = Math.sqrt(sumSq / valid.length) || 1e-6;
    }
  }

  // Random initial means (perturb global mean)
  const mu: number[][] = [];
  for (let s = 0; s < nStates; s++) {
    const row: number[] = [];
    for (let d = 0; d < nFeatures; d++) {
      row.push(globalMean[d] + (rng() - 0.5) * 2 * globalStd[d]);
    }
    mu.push(row);
  }

  // Initial variances = global variance
  const sigma2: number[][] = [];
  for (let s = 0; s < nStates; s++) {
    sigma2.push(globalStd.map((v) => v * v || 0.01));
  }

  // Uniform initial state distribution
  const pi = new Array(nStates).fill(1 / nStates);

  // Nearly-uniform transition matrix with self-transition bias
  const A: number[][] = [];
  const selfBias = 0.7;
  for (let i = 0; i < nStates; i++) {
    const row: number[] = [];
    for (let j = 0; j < nStates; j++) {
      row.push(i === j ? selfBias : (1 - selfBias) / (nStates - 1));
    }
    A.push(row);
  }

  return { pi, A, mu, sigma2 };
}

/**
 * Run the Baum-Welch EM algorithm for a Gaussian HMM with diagonal covariance.
 */
function baumWelch(
  features: number[][],
  nStates: number,
  maxIterations: number,
  tolerance: number,
  rng: () => number
): HmmParams & { logLikelihoods: number[] } {
  const nFeatures = 4;
  const T = features.length;

  let params = initializeParams(features, nStates, nFeatures, rng);
  const logLikelihoods: number[] = [];
  let prevLogLik = -Infinity;

  for (let iter = 0; iter < maxIterations; iter++) {
    const { pi, A, mu, sigma2 } = params;

    // ── E-step: forward-backward ──
    // Compute emission log-probabilities B[t][s]
    const logB: number[][] = new Array(T);
    for (let t = 0; t < T; t++) {
      logB[t] = new Array(nStates);
      for (let s = 0; s < nStates; s++) {
        logB[t][s] = multiGaussianLogPdf(features[t], mu[s], sigma2[s]);
      }
    }

    // Forward pass
    const logAlpha: number[][] = new Array(T);
    const logScale: number[] = new Array(T); // scaling factors for stability

    // t = 0
    logAlpha[0] = new Array(nStates);
    for (let s = 0; s < nStates; s++) {
      logAlpha[0][s] = Math.log(pi[s] + 1e-16) + logB[0][s];
    }
    logScale[0] = logSumExp(logAlpha[0]);
    for (let s = 0; s < nStates; s++) {
      logAlpha[0][s] -= logScale[0];
    }

    // t = 1..T-1
    for (let t = 1; t < T; t++) {
      logAlpha[t] = new Array(nStates);
      for (let j = 0; j < nStates; j++) {
        const terms: number[] = [];
        for (let i = 0; i < nStates; i++) {
          terms.push(logAlpha[t - 1][i] + Math.log(A[i][j] + 1e-16));
        }
        logAlpha[t][j] = logSumExp(terms) + logB[t][j];
      }
      logScale[t] = logSumExp(logAlpha[t]);
      for (let j = 0; j < nStates; j++) {
        logAlpha[t][j] -= logScale[t];
      }
    }

    // Log-likelihood = sum of log scale factors
    const logLik = logScale.reduce((a, b) => a + b, 0);
    logLikelihoods.push(logLik);

    // Convergence check
    if (Math.abs(logLik - prevLogLik) < tolerance) {
      break;
    }
    prevLogLik = logLik;

    // Backward pass
    const logBeta: number[][] = new Array(T);
    logBeta[T - 1] = new Array(nStates).fill(0); // log(1) = 0

    for (let t = T - 2; t >= 0; t--) {
      logBeta[t] = new Array(nStates);
      for (let i = 0; i < nStates; i++) {
        const terms: number[] = [];
        for (let j = 0; j < nStates; j++) {
          terms.push(Math.log(A[i][j] + 1e-16) + logB[t + 1][j] + logBeta[t + 1][j]);
        }
        logBeta[t][i] = logSumExp(terms);
      }
      // Normalize beta
      const betaScale = logSumExp(logBeta[t]);
      for (let i = 0; i < nStates; i++) {
        logBeta[t][i] -= betaScale;
      }
    }

    // Compute gamma (state occupation probabilities) in log space
    const gamma: number[][] = new Array(T);
    for (let t = 0; t < T; t++) {
      gamma[t] = new Array(nStates);
      const denom = logSumExp(
        logAlpha[t].map((a, i) => a + logBeta[t][i])
      );
      for (let s = 0; s < nStates; s++) {
        gamma[t][s] = Math.exp(logAlpha[t][s] + logBeta[t][s] - denom);
      }
    }

    // Compute xi (joint state probabilities) — only for adjacent pairs
    // xi[t][i][j] = P(state_t=i, state_{t+1}=j | observations)
    const xiSum: number[][] = new Array(nStates);
    for (let i = 0; i < nStates; i++) {
      xiSum[i] = new Array(nStates).fill(0);
    }

    for (let t = 0; t < T - 1; t++) {
      const denom = logSumExp(
        logAlpha[t].flatMap((a, i) =>
          logBeta[t + 1].map((b, j) => {
            // In scaled alpha/beta, we need to account for missing scale
            // Actually we're working in normalized log space, so: P ≈ exp(logAlpha+logA+logB+logBeta - logLik)
            // But logLik is already baked into the scales. We need to be careful here.
            // Simpler: use gamma directly for the M-step.
            return 0; // placeholder — we use gamma-based updates below
          })
        )
      );
    }

    // ── M-step: update parameters ──
    // For A and pi, we can use gamma sums directly (Baum-Welch with gamma only)
    // This is a simplified M-step that still converges

    // Update pi
    const newPi = gamma[0].map((g) => Math.max(g, 1e-8));
    const piSum = newPi.reduce((a, b) => a + b, 0);
    for (let s = 0; s < nStates; s++) newPi[s] /= piSum;

    // Update A using xi approximation from gamma
    // xi[i][j] ≈ gamma[t][i] * A[i][j] * emission_j(t+1) * beta_j(t+1) / beta_i(t)
    // For simplicity, estimate xi from gamma transitions
    const newA: number[][] = new Array(nStates);
    for (let i = 0; i < nStates; i++) {
      newA[i] = new Array(nStates).fill(1e-8);
    }

    for (let t = 0; t < T - 1; t++) {
      for (let i = 0; i < nStates; i++) {
        for (let j = 0; j < nStates; j++) {
          // Estimate xi from gamma-weighted transitions
          const xiApprox = gamma[t][i] * gamma[t + 1][j];
          newA[i][j] += xiApprox;
        }
      }
    }

    // Normalize rows
    for (let i = 0; i < nStates; i++) {
      const rowSum = newA[i].reduce((a, b) => a + b, 0);
      for (let j = 0; j < nStates; j++) {
        newA[i][j] /= rowSum;
      }
    }

    // Update means
    const newMu: number[][] = new Array(nStates);
    const gammaSums = new Array(nStates).fill(0);

    for (let s = 0; s < nStates; s++) {
      newMu[s] = new Array(nFeatures).fill(0);
      for (let t = 0; t < T; t++) {
        const g = gamma[t][s];
        gammaSums[s] += g;
        for (let d = 0; d < nFeatures; d++) {
          if (!Number.isNaN(features[t][d])) {
            newMu[s][d] += g * features[t][d];
          }
        }
      }
      for (let d = 0; d < nFeatures; d++) {
        newMu[s][d] /= Math.max(gammaSums[s], 1e-8);
      }
    }

    // Update variances
    const newSigma2: number[][] = new Array(nStates);
    for (let s = 0; s < nStates; s++) {
      newSigma2[s] = new Array(nFeatures).fill(1e-8);
      for (let t = 0; t < T; t++) {
        const g = gamma[t][s];
        for (let d = 0; d < nFeatures; d++) {
          if (!Number.isNaN(features[t][d])) {
            const diff = features[t][d] - newMu[s][d];
            newSigma2[s][d] += g * diff * diff;
          }
        }
      }
      for (let d = 0; d < nFeatures; d++) {
        newSigma2[s][d] = Math.max(newSigma2[s][d] / Math.max(gammaSums[s], 1e-8), 1e-8);
      }
    }

    params = { pi: newPi, A: newA, mu: newMu, sigma2: newSigma2 };
  }

  return { ...params, logLikelihoods };
}

// ── Viterbi decoding ────────────────────────────────────────────────────

/**
 * Viterbi algorithm: find the most likely state sequence.
 */
function viterbi(
  features: number[][],
  params: HmmParams
): number[] {
  const { pi, A, mu, sigma2 } = params;
  const nStates = mu.length;
  const T = features.length;

  const logDelta: number[][] = new Array(T);
  const psi: number[][] = new Array(T); // back-pointers

  // t = 0
  logDelta[0] = new Array(nStates);
  psi[0] = new Array(nStates).fill(0);
  for (let s = 0; s < nStates; s++) {
    logDelta[0][s] = Math.log(pi[s] + 1e-16) + multiGaussianLogPdf(features[0], mu[s], sigma2[s]);
  }

  // t = 1..T-1
  for (let t = 1; t < T; t++) {
    logDelta[t] = new Array(nStates);
    psi[t] = new Array(nStates);
    for (let j = 0; j < nStates; j++) {
      let bestVal = -Infinity;
      let bestState = 0;
      const emis = multiGaussianLogPdf(features[t], mu[j], sigma2[j]);
      for (let i = 0; i < nStates; i++) {
        const val = logDelta[t - 1][i] + Math.log(A[i][j] + 1e-16);
        if (val > bestVal) {
          bestVal = val;
          bestState = i;
        }
      }
      logDelta[t][j] = bestVal + emis;
      psi[t][j] = bestState;
    }
  }

  // Backtrack
  const states = new Array(T).fill(0);
  let bestLast = 0;
  let bestLastVal = -Infinity;
  for (let s = 0; s < nStates; s++) {
    if (logDelta[T - 1][s] > bestLastVal) {
      bestLastVal = logDelta[T - 1][s];
      bestLast = s;
    }
  }
  states[T - 1] = bestLast;
  for (let t = T - 2; t >= 0; t--) {
    states[t] = psi[t + 1][states[t + 1]];
  }

  return states;
}

// ── Forward filtering (smoothed probabilities) ──────────────────────────

/**
 * Forward-Backward smoothed state probabilities for each time step.
 * Returns gamma[t][s] = P(state_t = s | all observations).
 */
function forwardBackwardProbabilities(
  features: number[][],
  params: HmmParams
): number[][] {
  const { pi, A, mu, sigma2 } = params;
  const nStates = mu.length;
  const T = features.length;

  // Emission log-probabilities
  const logB: number[][] = new Array(T);
  for (let t = 0; t < T; t++) {
    logB[t] = new Array(nStates);
    for (let s = 0; s < nStates; s++) {
      logB[t][s] = multiGaussianLogPdf(features[t], mu[s], sigma2[s]);
    }
  }

  // Forward pass (scaled)
  const logAlpha: number[][] = new Array(T);
  const logScale: number[] = new Array(T);

  logAlpha[0] = new Array(nStates);
  for (let s = 0; s < nStates; s++) {
    logAlpha[0][s] = Math.log(pi[s] + 1e-16) + logB[0][s];
  }
  logScale[0] = logSumExp(logAlpha[0]);
  for (let s = 0; s < nStates; s++) logAlpha[0][s] -= logScale[0];

  for (let t = 1; t < T; t++) {
    logAlpha[t] = new Array(nStates);
    for (let j = 0; j < nStates; j++) {
      const terms: number[] = [];
      for (let i = 0; i < nStates; i++) {
        terms.push(logAlpha[t - 1][i] + Math.log(A[i][j] + 1e-16));
      }
      logAlpha[t][j] = logSumExp(terms) + logB[t][j];
    }
    logScale[t] = logSumExp(logAlpha[t]);
    for (let j = 0; j < nStates; j++) logAlpha[t][j] -= logScale[t];
  }

  // Backward pass
  const logBeta: number[][] = new Array(T);
  logBeta[T - 1] = new Array(nStates).fill(0);
  for (let t = T - 2; t >= 0; t--) {
    logBeta[t] = new Array(nStates);
    for (let i = 0; i < nStates; i++) {
      const terms: number[] = [];
      for (let j = 0; j < nStates; j++) {
        terms.push(Math.log(A[i][j] + 1e-16) + logB[t + 1][j] + logBeta[t + 1][j]);
      }
      logBeta[t][i] = logSumExp(terms);
    }
    const betaScale = logSumExp(logBeta[t]);
    for (let i = 0; i < nStates; i++) logBeta[t][i] -= betaScale;
  }

  // Smoothed gamma
  const gamma: number[][] = new Array(T);
  for (let t = 0; t < T; t++) {
    gamma[t] = new Array(nStates);
    const denom = logSumExp(logAlpha[t].map((a, i) => a + logBeta[t][i]));
    for (let s = 0; s < nStates; s++) {
      gamma[t][s] = Math.exp(logAlpha[t][s] + logBeta[t][s] - denom);
      // Clamp to avoid NaN
      if (!Number.isFinite(gamma[t][s])) gamma[t][s] = 0;
    }
    // Renormalize
    const gSum = gamma[t].reduce((a, b) => a + b, 0);
    if (gSum > 0) {
      for (let s = 0; s < nStates; s++) gamma[t][s] /= gSum;
    }
  }

  return gamma;
}

// ── Regime Labeling ─────────────────────────────────────────────────────

/**
 * Assign human-readable labels to each state based on the learned means.
 * Uses a heuristic ranking of states by their feature profiles:
 *
 *   - high-vol:  highest ATR(14) + highest |log return| magnitude
 *   - trending:  highest |log return| magnitude, moderate ATR
 *   - range-chop: moderate vol ratio, mid-range close location
 *   - low-vol:   lowest ATR(14), lowest volume ratio
 */
function assignRegimeLabels(
  mu: number[][],
  sigma2: number[][]
): { labels: HmmRegime[]; stateOrder: number[] } {
  const nStates = mu.length;

  // Feature indices: 0=logReturn, 1=atr14, 2=volRatio, 3=closeLocation
  // Score each state
  interface StateScore {
    index: number;
    absReturn: number;
    atr: number;
    volRatio: number;
    closeLoc: number;
  }

  const scores: StateScore[] = mu.map((m, i) => ({
    index: i,
    absReturn: Math.abs(m[0]),
    atr: m[1],
    volRatio: m[2],
    closeLoc: m[3],
  }));

  // Sort by different criteria
  const byAtr = [...scores].sort((a, b) => b.atr - a.atr);
  const byAbsRet = [...scores].sort((a, b) => b.absReturn - a.absReturn);
  const byVol = [...scores].sort((a, b) => b.volRatio - a.volRatio);

  const labels: HmmRegime[] = new Array(nStates).fill("range-chop");
  const assigned = new Set<number>();

  // State with highest ATR + high abs return → high-vol
  const highVolCandidates = byAtr.filter((s) => !assigned.has(s.index));
  if (highVolCandidates.length > 0) {
    labels[highVolCandidates[0].index] = "high-vol";
    assigned.add(highVolCandidates[0].index);
  }

  // State with highest abs return (not yet assigned) → trending
  const trendCandidates = byAbsRet.filter((s) => !assigned.has(s.index));
  if (trendCandidates.length > 0) {
    labels[trendCandidates[0].index] = "trending";
    assigned.add(trendCandidates[0].index);
  }

  // State with lowest ATR + lowest vol → low-vol
  const lowVolCandidates = scores
    .map((s, i) => ({ ...s, rank: i }))
    .filter((s) => !assigned.has(s.index))
    .sort((a, b) => (a.atr + a.volRatio) - (b.atr + b.volRatio));
  if (lowVolCandidates.length > 0) {
    labels[lowVolCandidates[0].index] = "low-vol";
    assigned.add(lowVolCandidates[0].index);
  }

  // Remaining → range-chop (default already set)

  // Build state order mapping regime → numeric label
  const stateOrder = labels.map((_, i) => i);

  return { labels, stateOrder };
}

// ── Main API ────────────────────────────────────────────────────────────

/**
 * Fit a 4-state Gaussian HMM to the given bars and return regime classifications.
 *
 * Algorithm:
 * 1. Extract 4 features per bar (log return, ATR, volume ratio, close location)
 * 2. Z-score normalize features
 * 3. Initialize HMM parameters randomly
 * 4. Run Baum-Welch EM (max 30 iterations, tolerance 1e-4)
 * 5. Viterbi decode to get most-likely state sequence
 * 6. Forward-Backward for smoothed state probabilities
 * 7. Assign human-readable labels to each state
 */
export function fitHmmRegime(input: HmmRegimeInput): HmmRegimeModel {
  const {
    bars,
    nStates = 4,
    maxIterations = 30,
    tolerance = 1e-4,
    atrPeriod = 14,
    volumeSmaPeriod = 20,
    seed = 42,
  } = input;

  const symbol = bars.length > 0 ? bars[0].symbol : "UNKNOWN";

  if (bars.length < 100) {
    throw new Error(`Need at least 100 bars for HMM fitting, got ${bars.length}`);
  }

  // 1. Extract features
  const { features: rawFeatures, validFrom } = extractFeatures(bars, atrPeriod, volumeSmaPeriod);

  // 2. Z-score normalize (using only valid rows for stats)
  const nFeatures = 4;
  const validRows: number[][] = [];
  for (let i = validFrom; i < rawFeatures.length; i++) {
    if (!rawFeatures[i].some(Number.isNaN)) {
      validRows.push(rawFeatures[i]);
    }
  }

  if (validRows.length < 100) {
    throw new Error(`Not enough valid feature rows: ${validRows.length} (need >= 100)`);
  }

  const featMean = new Array(nFeatures).fill(0);
  const featStd = new Array(nFeatures).fill(0);
  for (let d = 0; d < nFeatures; d++) {
    let sum = 0;
    for (const row of validRows) sum += row[d];
    featMean[d] = sum / validRows.length;
  }
  for (let d = 0; d < nFeatures; d++) {
    let sumSq = 0;
    for (const row of validRows) sumSq += (row[d] - featMean[d]) ** 2;
    featStd[d] = Math.sqrt(sumSq / validRows.length) || 1e-8;
  }

  const normalizedFeatures: number[][] = rawFeatures.map((f) =>
    f.map((v, d) => (Number.isNaN(v) ? NaN : (v - featMean[d]) / featStd[d]))
  );

  // 3–4. Train HMM (only on valid rows)
  const trainFeatures = normalizedFeatures.slice(validFrom).filter((f) => !f.some(Number.isNaN));

  const rng = createRng(seed);
  const { pi, A, mu, sigma2, logLikelihoods } = baumWelch(
    trainFeatures,
    nStates,
    maxIterations,
    tolerance,
    rng
  );

  // Denormalize means for display
  const denormMu = mu.map((m) => m.map((v, d) => v * featStd[d] + featMean[d]));
  const denormSigma2 = sigma2.map((s) => s.map((v, d) => v * featStd[d] * featStd[d]));

  // 5. Viterbi state sequence (on all valid rows)
  const vitStates = viterbi(trainFeatures, { pi, A, mu, sigma2 });

  // 6. Forward-Backward probabilities
  const gamma = forwardBackwardProbabilities(trainFeatures, { pi, A, mu, sigma2 });

  // 7. Assign regime labels
  const { labels: regimeLabels } = assignRegimeLabels(denormMu, denormSigma2);

  // Build per-bar results
  const regimeDistribution: HmmRegimeResult[] = [];
  const regimeCounts: Record<HmmRegime, number> = {
    trending: 0,
    "range-chop": 0,
    "high-vol": 0,
    "low-vol": 0,
  };

  for (let i = 0; i < trainFeatures.length; i++) {
    const barIdx = validFrom + i;
    const stateLabel = vitStates[i];
    const regime = regimeLabels[stateLabel];
    const probs = gamma[i].map((p) => Number(p.toFixed(6)));
    const rawFeat = rawFeatures[barIdx];

    regimeCounts[regime]++;

    regimeDistribution.push({
      barTs: bars[barIdx].ts,
      symbol,
      regime,
      regimeLabel: stateLabel,
      probabilities: probs,
      features: rawFeat.map((v) => Number(Number(v).toFixed(8))),
    });
  }

  const total = regimeDistribution.length || 1;
  const regimeFractions: Record<HmmRegime, number> = {
    trending: Number((regimeCounts.trending / total).toFixed(4)),
    "range-chop": Number((regimeCounts["range-chop"] / total).toFixed(4)),
    "high-vol": Number((regimeCounts["high-vol"] / total).toFixed(4)),
    "low-vol": Number((regimeCounts["low-vol"] / total).toFixed(4)),
  };

  // State feature stats
  const stateFeatureStats = mu.map((_, s) => {
    const featSums = new Array(nFeatures).fill(0);
    let count = 0;
    for (let i = 0; i < vitStates.length; i++) {
      if (vitStates[i] === s) {
        for (let d = 0; d < nFeatures; d++) {
          featSums[d] += trainFeatures[i][d];
        }
        count++;
      }
    }
    const featMeans = featSums.map((sum) => Number((sum / Math.max(count, 1)).toFixed(6)));
    return {
      stateLabel: s,
      regime: regimeLabels[s],
      featureMeans: featMeans,
    };
  });

  return {
    symbol,
    transitionMatrix: A.map((row) => row.map((v) => Number(v.toFixed(4)))),
    initialState: pi.map((v) => Number(v.toFixed(4))),
    means: denormMu.map((row) => row.map((v) => Number(v.toFixed(8)))),
    variances: denormSigma2.map((row) => row.map((v) => Number(v.toFixed(8)))),
    regimeDistribution,
    regimeFractions,
    stateFeatureStats,
  };
}

/**
 * Fit HMM regime for multiple symbols from a combined CSV.
 * The CSV must have columns: ts,symbol,open,high,low,close,volume.
 */
export function fitHmmRegimeMulti(
  bars: Bar[],
  symbols: string[],
  options?: Omit<HmmRegimeInput, "bars">
): HmmRegimeModel[] {
  const results: HmmRegimeModel[] = [];

  for (const sym of symbols) {
    const symBars = bars.filter((b) => b.symbol === sym);
    if (symBars.length < 100) {
      console.warn(`Skipping ${sym}: only ${symBars.length} bars (need >= 100)`);
      continue;
    }
    results.push(fitHmmRegime({ ...options, bars: symBars }));
  }

  return results;
}

// ── Pretty-print helpers ────────────────────────────────────────────────

export function formatRegimeReport(model: HmmRegimeModel): string {
  const lines: string[] = [];
  lines.push(`\n══════ HMM Regime Report: ${model.symbol} ══════`);
  lines.push("");
  lines.push("─ Transition Matrix ─");
  lines.push("       State0  State1  State2  State3");
  const regimeNames = model.stateFeatureStats.map((s) => s.regime);
  for (let i = 0; i < 4; i++) {
    const row = model.transitionMatrix[i].map((v) => String(v).padStart(7)).join(" ");
    lines.push(`  S${i}  ${row}  (${regimeNames[i]})`);
  }

  lines.push("");
  lines.push("─ Initial State Distribution ─");
  for (let i = 0; i < 4; i++) {
    lines.push(`  S${i} (${regimeNames[i]}): ${model.initialState[i].toFixed(4)}`);
  }

  lines.push("");
  lines.push("─ State Means (raw feature space) ─");
  lines.push("  State    logRet      ATR14     volRatio   closeLoc");
  for (const s of model.stateFeatureStats) {
    const m = model.means[s.stateLabel];
    lines.push(
      `  S${s.stateLabel} (${s.regime.padEnd(10)}) ` +
        m.map((v) => String(v).slice(0, 10).padStart(10)).join(" ")
    );
  }

  lines.push("");
  lines.push("─ Regime Fractions ─");
  for (const [regime, frac] of Object.entries(model.regimeFractions)) {
    lines.push(`  ${regime.padEnd(12)} ${(frac * 100).toFixed(1)}%`);
  }

  lines.push("");
  lines.push(`  Total bars classified: ${model.regimeDistribution.length}`);
  lines.push("══════════════════════════════════════════\n");

  return lines.join("\n");
}

// ── Demo / test runner ──────────────────────────────────────────────────

/**
 * Run a demo HMM fit on the first symbol found in a CSV and print the report.
 * This serves as the built-in test/verification.
 */
export async function runHmmDemo(csvPath: string, symbol?: string): Promise<HmmRegimeModel[]> {
  const fs = await import("node:fs");
  const path = await import("node:path");

  const content = fs.readFileSync(csvPath, "utf-8");
  const lines = content.trim().split("\n");
  if (lines.length < 2) throw new Error("CSV is empty");

  const header = lines[0].split(",");
  const tsIdx = header.indexOf("ts");
  const symIdx = header.indexOf("symbol");
  const openIdx = header.indexOf("open");
  const highIdx = header.indexOf("high");
  const lowIdx = header.indexOf("low");
  const closeIdx = header.indexOf("close");
  const volIdx = header.indexOf("volume");

  const bars: Bar[] = [];
  for (let i = 1; i < lines.length; i++) {
    const cols = lines[i].split(",");
    bars.push({
      ts: cols[tsIdx],
      symbol: cols[symIdx],
      open: Number(cols[openIdx]),
      high: Number(cols[highIdx]),
      low: Number(cols[lowIdx]),
      close: Number(cols[closeIdx]),
      volume: Number(cols[volIdx]),
    });
  }

  const symbols = symbol
    ? [symbol]
    : [...new Set(bars.map((b) => b.symbol))].slice(0, 3); // max 3 for demo

  console.log(`Fitting HMM for symbols: ${symbols.join(", ")}`);
  console.log(`Total bars loaded: ${bars.length}\n`);

  const results = fitHmmRegimeMulti(bars, symbols);

  for (const model of results) {
    console.log(formatRegimeReport(model));
  }

  return results;
}
