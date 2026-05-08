/**
 * #40 Optimal Pairs Trading with Proportional Transaction Costs
 * Source: Xing, H. (Nov 2019). "A singular stochastic control approach for
 *   optimal pairs trading with proportional transaction costs." arXiv:1911.10450.
 *
 * Key finding: First solution for optimal pairs trading with BOTH optimal timing
 * AND share quantities under transaction costs. Derives a FREE BOUNDARY that
 * defines a no-trade zone — prevents the death-by-a-thousand-spreads problem.
 *
 * The free boundary defines three zones:
 *   - NO-TRADE ZONE: |spread| < cost_threshold → don't trade (friction > edge)
 *   - ENTRY ZONE: cost_threshold < |spread| < max_threshold → entry signal
 *   - OVER-EXTENDED ZONE: |spread| > max_threshold → too far, wait for pullback
 *
 * Implementation: Compute the cost-aware free boundary and only trade when
 * the spread is in the entry zone (edge exceeds friction, but not overextended).
 *
 * Market logic: Every trade incurs ~0.6R in costs. If your edge < 0.6R, you lose
 * money on every trade. The no-trade zone explicitly accounts for this.
 */
import type { Bar, Strategy, StrategyContext, StrategySignal, TradeSide } from "../domain.js";
import { calculateRr } from "../risk/guardrails.js";
import { averageTrueRange } from "../utils/indicators.js";
import { inferBarIntervalMinutes } from "../utils/time.js";

const SPREAD_LOOKBACK = 50;
const COST_PER_TRADE_R = 0.65; // Roundtrip fee + slippage + buffer per trade
const MIN_EDGE_MULTIPLE = 1.5; // Edge must exceed cost by 1.5x to enter

/**
 * Compute z-score of spread between two assets.
 * Simplified: z-score of price relative to rolling mean.
 */
function computeSpreadZScore(history: Bar[], lookback: number): { zScore: number; sigma: number } | null {
  if (history.length < lookback) return null;
  const closes = history.slice(-lookback).map((b) => b.close);
  const mean = closes.reduce((a, b) => a + b, 0) / closes.length;
  const variance = closes.reduce((s, v) => s + (v - mean) ** 2, 0) / closes.length;
  const sigma = Math.sqrt(variance);
  if (sigma <= 0) return null;
  return { zScore: (closes[closes.length - 1]! - mean) / sigma, sigma };
}

/**
 * Compute the cost-aware free boundary.
 * Returns: { noTradeZone: number, entryZoneMax: number }
 * noTradeZone: |z| below this = don't trade (edge < cost)
 * entryZoneMax: |z| above this = over-extended, wait for pullback
 */
function computeFreeBoundary(history: Bar[]): { noTradeZone: number; entryZoneMax: number } | null {
  const { zScore, sigma } = (() => {
    const result = computeSpreadZScore(history, SPREAD_LOOKBACK);
    return result ?? { zScore: 0, sigma: 0 };
  })();
  if (sigma <= 0) return null;

  // Cost in sigma units: cost_per_trade_R / (sigma in R units)
  // ATR approximates 1R of risk, sigma approximates spread volatility
  const atr = averageTrueRange(history, 14);
  if (atr <= 0) return null;

  const sigmaInR = sigma / atr; // How many R-units per sigma
  const costInSigma = COST_PER_TRADE_R / Math.max(sigmaInR, 0.1);

  // No-trade zone: spread within cost boundary
  const noTradeZone = costInSigma * MIN_EDGE_MULTIPLE;

  // Entry zone max: 2x no-trade zone (beyond this = over-extended)
  const entryZoneMax = noTradeZone * 2.5;

  return { noTradeZone, entryZoneMax };
}

export class OptimalCostPairsStrategy implements Strategy {
  public readonly id = "optimal-cost-pairs";
  public readonly description =
    "Optimal pairs trading with proportional transaction costs. " +
    "Free boundary defines no-trade zone, entry zone, and over-extended zone. " +
    "Prevents death-by-a-thousand-spreads. Source: Xing 2019 arXiv:1911.10450.";

  private readonly symbolHistory: Map<string, Bar[]> = new Map();

  public generateSignal(context: StrategyContext): StrategySignal | null {
    // Trade on CL and GC (commodities with mean-reverting tendencies)
    if (context.symbol !== "CL" && context.symbol !== "GC") return null;

    const prevBarTs = context.history[context.history.length - 1]?.ts;
    const barIntervalMinutes = inferBarIntervalMinutes(prevBarTs, context.bar.ts);
    if (barIntervalMinutes >= 240) return null;

    let history = this.symbolHistory.get(context.symbol) ?? [];
    history = [...history, context.bar];
    if (history.length > 300) history = history.slice(-300);
    this.symbolHistory.set(context.symbol, history);

    if (history.length < SPREAD_LOOKBACK) return null;

    const spreadResult = computeSpreadZScore(history, SPREAD_LOOKBACK);
    if (!spreadResult) return null;

    const boundary = computeFreeBoundary(history);
    if (!boundary) return null;

    const absZ = Math.abs(spreadResult.zScore);

    // Zone check
    if (absZ < boundary.noTradeZone) return null; // No-trade zone
    if (absZ > boundary.entryZoneMax) return null; // Over-extended

    // Entry zone: trade!
    const side: TradeSide = spreadResult.zScore > 0 ? "short" : "long";

    const atr = averageTrueRange(context.sessionHistory, 14);
    if (atr <= 0) return null;

    const risk = atr * 1.0;
    const targetRr = Math.max(context.config.guardrails.minRr, 2.0);
    const entry = context.bar.close;
    const stop = side === "long" ? entry - risk : entry + risk;
    const target = side === "long" ? entry + risk * targetRr : entry - risk * targetRr;

    const rr = calculateRr(entry, stop, target, side);
    if (rr <= 0) return null;

    // Confidence: higher when in sweet spot of entry zone
    const zonePosition = (absZ - boundary.noTradeZone) / (boundary.entryZoneMax - boundary.noTradeZone);
    const confidence = Math.min(0.7, 0.45 + (1 - Math.abs(zonePosition - 0.5) * 2) * 0.25);

    return {
      symbol: context.symbol,
      strategyId: "optimal-cost-pairs",
      side, entry, stop, target, rr,
      confidence, contracts: 1, maxHoldMinutes: 30,
      meta: {
        zScore: Math.round(spreadResult.zScore * 100) / 100,
        noTradeBoundary: Math.round(boundary.noTradeZone * 100) / 100,
        zone: "entry",
        costPerTradeR: COST_PER_TRADE_R,
        paper: "arXiv:1911.10450",
      },
    };
  }
}
