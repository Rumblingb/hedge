/**
 * Hybrid Kelly + VIX Position Sizing — Expiry-Flow Lane
 *
 * Derived from: Wysocki, M. (Aug 2025). "Sizing the Risk: Kelly, VIX, and
 * Hybrid Approaches in Put-Writing on Index Options." arXiv:2508.16598.
 * (#38 in research-high-signals)
 *
 * Key insight: pure Kelly criterion produces aggressive sizes in low-vol
 * regimes that lead to excessive drawdowns during volatility spikes. VIX-based
 * scaling tempers Kelly sizing: in low-VIX regimes, use full Kelly fraction;
 * in elevated VIX regimes, scale down proportionally. The hybrid approach
 * balances return maximization with drawdown control.
 *
 * This module provides a Kelly fraction calculator tempered by VIX regime,
 * suitable for position sizing in the expiry-flow (#5) lane. It can also be
 * used generically for any strategy that needs volatility-aware sizing.
 */

/** Historical VIX percentiles for context (rough values, recompute from data). */
const VIX_MEDIAN = 17.5;   // approximate VIX median (2015-2025)
const VIX_P75 = 21.0;      // 75th percentile
const VIX_P90 = 27.0;      // 90th percentile

export interface KellyVixInput {
  /** Expected win rate (0–1). */
  winRate: number;
  /** Average win in R multiples (positive). */
  avgWinR: number;
  /** Average loss in R multiples (positive). */
  avgLossR: number;
  /** Current VIX level. */
  vixLevel: number;
  /** Pre-existing risk exposure in R (for fractional Kelly). */
  currentRiskR?: number;
  /** Risk limit in R. Defaults to 4.0. */
  maxRiskR?: number;
}

export interface KellyVixOutput {
  /** Raw Kelly fraction: f* = winRate - (1 - winRate) / (avgWinR / avgLossR). */
  rawKellyFraction: number;
  /** VIX multiplier (0.25–1.0): scales Kelly based on current VIX vs historical percentiles. */
  vixMultiplier: number;
  /** Hybrid position size fraction: rawKellyFraction * vixMultiplier. */
  hybridFraction: number;
  /** Recommended contracts (rounded to integer, minimum 0). */
  recommendedContracts: number;
  /** VIX regime classification. */
  vixRegime: "calm" | "normal" | "elevated" | "extreme";
  /** Warning if hybrid fraction is negative (negative expectancy). */
  warning: string | null;
}

/**
 * Compute hybrid Kelly + VIX position sizing.
 *
 * Algorithm:
 * 1. Raw Kelly: f* = winRate - (1 - winRate) / (avgWinR / avgLossR)
 * 2. Clamp raw Kelly to [0, 0.25] (quarter-Kelly maximum for safety)
 * 3. VIX multiplier: VIX ≤ median → 1.0; VIX ≥ P90 → 0.25; linear between
 * 4. Hybrid fraction = clampedKelly * vixMultiplier
 * 5. Recommended contracts = floor(hybridFraction * (maxRiskR / avgLossR))
 */
export function computeHybridKellyVixSizing(input: KellyVixInput): KellyVixOutput {
  const { winRate, avgWinR, avgLossR, vixLevel, maxRiskR = 4.0 } = input;

  // Raw Kelly: f* = p - q / b  where p = winRate, q = 1-p, b = avgWinR/avgLossR
  if (avgLossR <= 0 || avgWinR <= 0) {
    return {
      rawKellyFraction: 0,
      vixMultiplier: 0,
      hybridFraction: 0,
      recommendedContracts: 0,
      vixRegime: "normal",
      warning: "Invalid input: avgWinR and avgLossR must be positive"
    };
  }

  const payoffRatio = avgWinR / avgLossR;
  const rawKellyFraction = winRate - (1 - winRate) / payoffRatio;

  // Clamp to quarter-Kelly maximum (standard practice for real-world robustness)
  const clampedKelly = Math.max(0, Math.min(rawKellyFraction, 0.25));

  // VIX multiplier: linear interpolation between reference points
  let vixMultiplier: number;
  let vixRegime: KellyVixOutput["vixRegime"];

  if (vixLevel <= VIX_MEDIAN) {
    vixMultiplier = 1.0;
    vixRegime = "calm";
  } else if (vixLevel >= VIX_P90) {
    vixMultiplier = 0.25;
    vixRegime = "extreme";
  } else if (vixLevel >= VIX_P75) {
    // Linear from P75 (0.5) to P90 (0.25)
    const t = (vixLevel - VIX_P75) / (VIX_P90 - VIX_P75);
    vixMultiplier = 0.5 - t * 0.25;
    vixRegime = "elevated";
  } else {
    // Linear from median (1.0) to P75 (0.5)
    const t = (vixLevel - VIX_MEDIAN) / (VIX_P75 - VIX_MEDIAN);
    vixMultiplier = 1.0 - t * 0.5;
    vixRegime = "normal";
  }

  vixMultiplier = Number(Math.max(0.25, Math.min(1.0, vixMultiplier)).toFixed(4));

  const hybridFraction = Number((clampedKelly * vixMultiplier).toFixed(6));

  // Contracts: floor of expected risk allocation
  const recommendedContracts = Math.floor(hybridFraction * (maxRiskR / avgLossR));

  const warning = rawKellyFraction < 0
    ? "Negative expectancy — Kelly fraction is zero. Strategy is unprofitable under current parameters."
    : null;

  return {
    rawKellyFraction: Number(rawKellyFraction.toFixed(6)),
    vixMultiplier,
    hybridFraction,
    recommendedContracts: Math.max(0, recommendedContracts),
    vixRegime,
    warning
  };
}
