/**
 * Beta-Normalized Gamma Exposure Feature — Expiry-Flow Lane
 *
 * Derived from: Dai, H. (Nov 2025). "Beta-Dependent Gamma Feedback and
 * Endogenous Volatility Amplification in Option Markets." arXiv:2511.22766.
 * (#42 in research-high-signals)
 *
 * Key insight: gamma exposure must be weighted by 1/β because low-beta
 * stocks (and futures) exhibit disproportionately strong gamma feedback.
 * Raw gamma underestimates risk in low-beta assets; the stability condition
 * derived in the paper depends on beta-normalized gamma.
 *
 * This module computes a beta-normalized aggregate gamma exposure score
 * from Polygon/Alpaca option snapshots. The score feeds into the expiry-flow
 * strategy as a regime modifier: high normalized gamma → heightened dealer
 * hedging flow expected → amplify or suppress signals accordingly.
 */

import type { PolygonOptionSnapshot } from "../research/options.js";

/** Beta required for normalization. If unavailable, use default. */
export interface GammaFeatureInput {
  /** Option snapshots for the underlying (typically nearest expiry). */
  snapshots: PolygonOptionSnapshot[];
  /** Beta of the underlying relative to ES (S&P 500 mini). Default: 1.0. */
  beta?: number;
  /** Only consider contracts with open interest above this floor. Default: 0. */
  minOpenInterest?: number;
  /** Maximum days to expiry to include. Default: no filter. */
  maxDte?: number;
}

export interface GammaFeatureOutput {
  /** Beta-normalized aggregate gamma (sum of gamma / beta). */
  netGamma: number;
  /** Simple sum of raw gamma (un-normalized, for reference). */
  rawGamma: number;
  /** Number of contracts contributing. */
  contractCount: number;
  /** Ratio netGamma/rawGamma — >1 means low-beta amplification. */
  amplificationFactor: number;
  /** Whether the stability condition from Dai (2025) is at risk (|netGamma| > 2.0 threshold). */
  gammaSqueezeRisk: boolean;
  /** Call / put gamma imbalance. Positive = calls dominant (dealer short gamma). */
  callPutGammaImbalance: number;
}

const GAMMA_SQUEEZE_THRESHOLD = 2.0;

/**
 * Compute beta-normalized gamma exposure from option snapshots.
 *
 * Algorithm:
 * 1. Filter snapshots to those with valid gamma and open interest
 * 2. Sum gamma * open_interest for calls and puts separately
 * 3. Divide by beta (default 1.0 if unknown) for normalization
 * 4. Check stability: |netGamma| > 2.0 → elevated gamma-squeeze risk
 */
export function computeGammaFeature(input: GammaFeatureInput): GammaFeatureOutput {
  const { snapshots, beta = 1.0, minOpenInterest = 0, maxDte } = input;
  const betaSafe = Math.max(beta, 0.1); // floor at 0.1 to avoid division by zero

  let callGamma = 0;
  let putGamma = 0;
  let rawGamma = 0;
  let contractCount = 0;

  for (const snap of snapshots) {
    if (snap.gamma === undefined || !Number.isFinite(snap.gamma)) continue;
    if (snap.openInterest === undefined || !Number.isFinite(snap.openInterest)) continue;
    if (snap.openInterest < minOpenInterest) continue;

    // Optional DTE filter
    if (maxDte !== undefined && snap.expirationDate) {
      const dte = daysToExpiry(snap.expirationDate);
      if (dte > maxDte) continue;
    }

    const weightedGamma = snap.gamma * snap.openInterest;
    rawGamma += weightedGamma;
    contractCount += 1;

    if (snap.contractType === "call") {
      callGamma += weightedGamma;
    } else if (snap.contractType === "put") {
      putGamma += weightedGamma;
    }
  }

  const netGamma = rawGamma / betaSafe;
  const amplificationFactor = betaSafe < 1.0 ? 1 / betaSafe : 1.0;
  const gammaSqueezeRisk = Math.abs(netGamma) > GAMMA_SQUEEZE_THRESHOLD;
  const callPutGammaImbalance = contractCount > 0 ? (callGamma - putGamma) / (Math.abs(callGamma) + Math.abs(putGamma) + 1e-10) : 0;

  return {
    netGamma: Number(netGamma.toFixed(6)),
    rawGamma: Number(rawGamma.toFixed(6)),
    contractCount,
    amplificationFactor: Number(amplificationFactor.toFixed(4)),
    gammaSqueezeRisk,
    callPutGammaImbalance: Number(callPutGammaImbalance.toFixed(4))
  };
}

/** Estimated beta for common futures relative to ES (S&P 500). */
const FUTURES_BETA_MAP: Record<string, number> = {
  ES: 1.0,
  MES: 1.0,
  NQ: 1.25,
  MNQ: 1.25,
  RTY: 0.85,
  M2K: 0.85,
  YM: 0.90,
  MYM: 0.90,
  CL: 0.30,
  GC: 0.05,
  ZB: -0.25,
  ZN: -0.20
};

/**
 * Get the estimated beta for a futures symbol relative to ES.
 * Returns 1.0 for unknown symbols (safe default).
 */
export function getFuturesBeta(symbol: string): number {
  const upper = symbol.toUpperCase();
  // Strip contract month/year suffix if present (e.g., ESM6 → ES)
  const base = upper.replace(/[FGHJKMNQUVXZ]\d{1,2}$/, "").replace(/\d{1,2}$/, "");
  return FUTURES_BETA_MAP[base] ?? 1.0;
}

function daysToExpiry(expirationDate: string): number {
  const expiry = new Date(`${expirationDate}T23:59:59.999Z`);
  const now = new Date();
  return Math.max(0, Math.round((expiry.getTime() - now.getTime()) / 86_400_000));
}
