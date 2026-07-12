/**
 * VIX Contango / Backwardation Regime Flag — Expiry-Flow & Macro-Rates Lanes
 *
 * Derived from: Avellaneda, M., Li, T.N., Papanicolaou, A., & Wang, G.
 * (Mar 2021). "Trading Signals In VIX Futures." arXiv:2103.02016.
 * (#39 in research-high-signals)
 *
 * Key insight: the VIX futures term structure (contango vs backwardation)
 * is a Markov regime indicator. In contango (futures > VIX spot), the market
 * is in "carry" mode — sell volatility premium. In backwardation (futures <
 * VIX spot), the market is in "stress" mode — buy protection. The paper's
 * 5-layer DNN maps the full term structure shape/level to optimal position,
 * but even a simple contango/backwardation flag provides significant regime
 * information.
 *
 * This module provides a lightweight VIX term-structure flag that can be
 * used without the full DNN, serving as:
 * - A regime override for volatility-regime strategy (#8)
 * - A macro context signal for expiry-flow strategy (#5)
 * - An input to hybrid Kelly sizing (#38)
 */

/** Contango: front-month future above VIX spot (normal, ~80% of days). */
export type VixRegime = "contango" | "backwardation" | "flat";

export interface VixContangoInput {
  /** VIX spot (CBOE VIX index level). */
  vixSpot: number;
  /** Front-month VIX futures price. */
  frontMonthFuture: number;
  /** Second-month VIX futures price (optional, for slope). */
  secondMonthFuture?: number;
  /** Term structure slope (optional, computed if not provided). */
  termStructureSlope?: number;
}

export interface VixContangoOutput {
  /** Regime classification. */
  regime: VixRegime;
  /** Contango premium as percentage: (future - spot) / spot. */
  contangoPct: number;
  /** Term structure slope: second - front month difference (if available). */
  termStructureSlope?: number;
  /** Whether the VIX regime suggests selling premium (true in contango). */
  sellPremium: boolean;
  /** Whether the VIX regime suggests buying protection (true in backwardation). */
  buyProtection: boolean;
  /** Volatility-of-volatility flag: large contango spread (>5%) or steep backwardation (<-2%). */
  elevatedVolOfVol: boolean;
}

/** Contango threshold: futures > spot by this margin to count as contango. */
const CONTANGO_THRESHOLD_PCT = 0.5;
/** Backwardation threshold: futures < spot by this margin. */
const BACKWARDATION_THRESHOLD_PCT = -0.5;
/** Elevated vol-of-vol: contango >5% or backwardation <-2%. */
const ELEVATED_CONTANGO_PCT = 5.0;
const ELEVATED_BACKWARDATION_PCT = -2.0;

/**
 * Classify the VIX term structure into contango/backwardation/flat.
 *
 * Algorithm:
 * 1. Compute contango premium = (front-month - spot) / spot * 100
 * 2. If >0.5% → contango, <-0.5% → backwardation, else flat
 * 3. Term structure slope = second-month - front-month (if available)
 * 4. Elevated vol-of-vol if contango >5% or backwardation <-2%
 */
export function classifyVixRegime(input: VixContangoInput): VixContangoOutput {
  const { vixSpot, frontMonthFuture, secondMonthFuture } = input;

  if (vixSpot <= 0 || frontMonthFuture <= 0) {
    return {
      regime: "flat",
      contangoPct: 0,
      sellPremium: false,
      buyProtection: false,
      elevatedVolOfVol: false
    };
  }

  const contangoPct = ((frontMonthFuture - vixSpot) / vixSpot) * 100;
  let regime: VixRegime;
  if (contangoPct > CONTANGO_THRESHOLD_PCT) {
    regime = "contango";
  } else if (contangoPct < BACKWARDATION_THRESHOLD_PCT) {
    regime = "backwardation";
  } else {
    regime = "flat";
  }

  const termStructureSlope = secondMonthFuture !== undefined && secondMonthFuture > 0
    ? Number((secondMonthFuture - frontMonthFuture).toFixed(4))
    : input.termStructureSlope;

  const elevatedVolOfVol = contangoPct > ELEVATED_CONTANGO_PCT || contangoPct < ELEVATED_BACKWARDATION_PCT;

  return {
    regime,
    contangoPct: Number(contangoPct.toFixed(2)),
    termStructureSlope,
    sellPremium: regime === "contango",
    buyProtection: regime === "backwardation",
    elevatedVolOfVol
  };
}
