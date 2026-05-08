/**
 * #54 HMM Regime-Switching Statistical Arbitrage (Pairs)
 * Source: Fanelli, V., Fontana, C., & Rotondi, F. (Sep 2023, v3 Feb 2026).
 *   "A hidden Markov model for statistical arbitrage in international
 *    crude oil futures markets." arXiv:2309.00875.
 *
 * Key finding: Traditional Brent/WTI/Dubai pairs NOT profitable.
 * HMM regime-switching cointegration spread model identifies when
 * mean-reversion is active vs dormant. Shanghai crude oil futures
 * identified as the key differentiator for profitability.
 *
 * Implementation: 2-state HMM on spread z-score.
 * State 1: mean-reverting (trade — high prob of reversion)
 * State 2: trending (avoid — spread drifting)
 * Only trade when P(mean-reverting) > 0.7.
 *
 * Market logic: Cointegration relationships are regime-dependent.
 * Static OU assumes constant mean-reversion speed — HMM detects
 * when the relationship is actually active.
 */
import type { Bar, Strategy, StrategyContext, StrategySignal } from "../domain.js";
import { calculateRr } from "../risk/guardrails.js";
import { averageTrueRange } from "../utils/indicators.js";

// Pairs: CL (WTI Crude) is primary, we trade against mean-reversion
const PAIRS: Array<{ a: string; b: string; hedgeRatio: number }> = [
  { a: "CL", b: "ES", hedgeRatio: 0.3 },  // Crude vs Equity (risk-on/off proxy)
  { a: "CL", b: "GC", hedgeRatio: 0.25 }, // Crude vs Gold (inflation hedge)
  { a: "ES", b: "NQ", hedgeRatio: 1.0 },  // Equity index spread
];

interface HMMState {
  mu1: number;     // Mean of state 1 (mean-reverting)
  mu2: number;     // Mean of state 2 (trending)
  sigma1: number;  // Std of state 1
  sigma2: number;  // Std of state 2
  p11: number;     // P(stay in state 1)
  p22: number;     // P(stay in state 2)
  pi1: number;     // Stationary prob of state 1
}

/**
 * Fit 2-state Gaussian HMM using EM algorithm (simplified).
 * Input: spread z-scores. Output: HMM parameters.
 */
function fitHmm2State(
  zScores: number[],
  maxIter = 50,
  tol = 1e-4,
): HMMState {
  const n = zScores.length;
  if (n < 20) {
    return { mu1: 0, mu2: 0, sigma1: 1, sigma2: 1, p11: 0.95, p22: 0.95, pi1: 0.5 };
  }

  // Initialize: state 1 = values near zero (mean-reverting), state 2 = extremes
  const sorted = [...zScores].sort((a, b) => a - b);
  const q25 = sorted[Math.floor(n * 0.25)]!;
  const q75 = sorted[Math.floor(n * 0.75)]!;

  let mu1 = 0;
  let mu2 = zScores.reduce((a, b) => a + b, 0) / n;
  let sigma1 = 0.5;
  let sigma2 = 1.5;
  let p11 = 0.95;
  let p22 = 0.95;

  // EM iterations
  for (let iter = 0; iter < maxIter; iter++) {
    // E-step: compute responsibilities
    const gamma1: number[] = [];
    const gamma2: number[] = [];

    for (const z of zScores) {
      const like1 = gaussianPdf(z, mu1, sigma1);
      const like2 = gaussianPdf(z, mu2, sigma2);
      const denom = like1 + like2;
      gamma1.push(denom > 1e-10 ? like1 / denom : 0.5);
      gamma2.push(denom > 1e-10 ? like2 / denom : 0.5);
    }

    // M-step: update parameters
    const sum1 = gamma1.reduce((a, b) => a + b, 0);
    const sum2 = gamma2.reduce((a, b) => a + b, 0);

    const newMu1 = gamma1.reduce((s, g, i) => s + g * zScores[i]!, 0) / (sum1 || 1);
    const newMu2 = gamma2.reduce((s, g, i) => s + g * zScores[i]!, 0) / (sum2 || 1);

    const newSigma1 = Math.sqrt(
      gamma1.reduce((s, g, i) => s + g * (zScores[i]! - newMu1) ** 2, 0) / (sum1 || 1),
    );
    const newSigma2 = Math.sqrt(
      gamma2.reduce((s, g, i) => s + g * (zScores[i]! - newMu2) ** 2, 0) / (sum2 || 1),
    );

    // Check convergence
    if (
      Math.abs(newMu1 - mu1) < tol &&
      Math.abs(newMu2 - mu2) < tol &&
      Math.abs(newSigma1 - sigma1) < tol &&
      Math.abs(newSigma2 - sigma2) < tol
    ) {
      mu1 = newMu1;
      mu2 = newMu2;
      sigma1 = newSigma1;
      sigma2 = newSigma2;
      break;
    }

    mu1 = newMu1;
    mu2 = newMu2;
    sigma1 = newSigma1 || 0.1;
    sigma2 = newSigma2 || 0.1;
  }

  // Ensure sigma1 < sigma2 (mean-reverting = tighter)
  if (sigma1 > sigma2) {
    [mu1, mu2] = [mu2, mu1];
    [sigma1, sigma2] = [sigma2, sigma1];
  }

  const pi1 = (1 - p22) / (2 - p11 - p22);

  return { mu1, mu2, sigma1, sigma2, p11, p22, pi1 };
}

function gaussianPdf(x: number, mu: number, sigma: number): number {
  const z = (x - mu) / (sigma || 0.1);
  return Math.exp(-0.5 * z * z) / (Math.sqrt(2 * Math.PI) * (sigma || 0.1));
}

/**
 * Compute current probability of being in mean-reverting state.
 */
function probMeanReverting(
  zScore: number,
  hmm: HMMState,
  prevProb: number,
): number {
  const like1 = gaussianPdf(zScore, hmm.mu1, hmm.sigma1);
  const like2 = gaussianPdf(zScore, hmm.mu2, hmm.sigma2);

  // Forward probability
  const p1GivenPrev = prevProb * hmm.p11 + (1 - prevProb) * (1 - hmm.p22);
  const unnormProb = p1GivenPrev * like1;
  const denom = unnormProb + (1 - p1GivenPrev) * like2;

  return denom > 1e-10 ? unnormProb / denom : 0.5;
}

export class HmmPairsArbStrategy implements Strategy {
  public readonly id = "hmm-pairs-arb";
  public readonly description =
    "HMM regime-switching statistical arbitrage. Replaces static OU with 2-state HMM. " +
    "Only trades pairs when P(mean-reverting) > 0.7. Source: Fanelli et al. arXiv:2309.00875.";

  private readonly pairHistories: Map<string, Bar[]> = new Map();
  private prevProb = 0.5;
  private lastHmm: HMMState | null = null;
  private hmmFitCount = 0;

  public generateSignal(context: StrategyContext): StrategySignal | null {
    // Only trade specific symbols
    const pairCfg = PAIRS.find((p) => p.a === context.symbol);
    if (!pairCfg) return null;

    // Build internal history
    const key = `pair:${pairCfg.a}-${pairCfg.b}`;
    let pairHistory = this.pairHistories.get(key) ?? [];
    pairHistory = [...pairHistory, context.bar];
    if (pairHistory.length > 300) pairHistory = pairHistory.slice(-300);
    this.pairHistories.set(key, pairHistory);

    if (pairHistory.length < 50) return null;

    // Compute cointegration spread = log(priceA) - hedgeRatio * log(priceB)
    // Since we only have symbol A's bars, we approximate using price-only spread
    // For full implementation, need both symbols' bars simultaneously
    // Simplified: z-score of price relative to its own moving average
    const closes = pairHistory.map((b) => b.close);
    const lookback = context.config.tuning.pairsLookbackBars || 50;

    if (closes.length < lookback) return null;

    const window = closes.slice(-lookback);
    const mean = window.reduce((a, b) => a + b, 0) / window.length;
    const variance =
      window.reduce((s, v) => s + (v - mean) ** 2, 0) / window.length;
    const std = Math.sqrt(variance);
    if (std <= 0) return null;

    const zScore = (closes[closes.length - 1]! - mean) / std;

    // Fit/update HMM every 20 bars
    if (this.hmmFitCount % 20 === 0 && closes.length >= 50) {
      const zHistory: number[] = [];
      for (let i = lookback; i < closes.length; i++) {
        const w = closes.slice(Math.max(0, i - lookback), i);
        const m = w.reduce((a, b) => a + b, 0) / w.length;
        const v = w.reduce((s, x) => s + (x - m) ** 2, 0) / w.length;
        const s = Math.sqrt(v);
        zHistory.push(s > 0 ? (closes[i]! - m) / s : 0);
      }
      this.lastHmm = fitHmm2State(zHistory);
    }
    this.hmmFitCount++;

    if (!this.lastHmm) return null;

    // Compute current probability of mean-reverting state
    const pMr = probMeanReverting(zScore, this.lastHmm, this.prevProb);
    this.prevProb = pMr;

    // Only trade when confident we're in mean-reverting regime
    if (pMr < 0.70) return null;

    // Entry: z-score beyond threshold
    const zEntry = context.config.tuning.pairsZEntry || 1.5;
    if (Math.abs(zScore) < zEntry) return null;

    const atr = averageTrueRange(context.sessionHistory, 14);
    if (atr <= 0) return null;

    const side = zScore > 0 ? "short" : "long";
    const risk = atr * 1.0;
    const targetRr = Math.max(context.config.guardrails.minRr, 2.0);

    const entry = context.bar.close;
    const stop = side === "long" ? entry - risk : entry + risk;
    const target = side === "long" ? entry + risk * targetRr : entry - risk * targetRr;

    const rr = calculateRr(entry, stop, target, side);
    if (rr <= 0) return null;

    return {
      symbol: context.symbol,
      strategyId: "hmm-pairs-arb",
      side,
      entry,
      stop,
      target,
      rr,
      confidence: pMr, // Confidence = HMM probability
      contracts: 1,
      maxHoldMinutes: 30,
      meta: {
        zScore: Math.round(zScore * 100) / 100,
        pMeanReverting: Math.round(pMr * 100) / 100,
        hmmState: pMr > 0.7 ? "mean-reverting" : "trending",
        paper: "arXiv:2309.00875",
      },
    };
  }
}
