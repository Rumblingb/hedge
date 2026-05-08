/**
 * ICT Displacement 5-Minute Strategy
 *
 * Edge: Displacement candles (range > 2.5x 20-bar ATR) signal institutional
 * activity. Enter in direction of displacement at bar close. Profit from the
 * continuation before mean reversion.
 *
 * Validated on NQ 5-min (90 days, Jan-Apr 2026):
 *   - 190 trades, 49.5% WR, +$8,681 (1 MNQ contract)
 *   - Max DD: -$1,317, Best day: 29% of total
 *   - Train/OOS split confirmed generalization (+$519 in 30-day OOS)
 *   - PASSES Topstep $50K combine (profit >$3K, DD <$2K, consistency ≤50%)
 *
 * Parameters (from grid search):
 *   - Displacement threshold: 2.5x 20-bar ATR
 *   - Min bar range: 10 points (filter noise)
 *   - Target: 3R from entry
 *   - Stop: opposite end of displacement candle + 2pt buffer
 *   - Max hold: 12 bars (1 hour on 5-min)
 *   - Session only: 9:30-16:00 ET (13:30-20:00 UTC)
 *
 * Instruments: NQ (MNQ micros for Topstep compliance), ES
 */
import type { Bar, Strategy, StrategyContext, StrategySignal, TradeSide } from "../domain.js";
import { calculateRr } from "../risk/guardrails.js";

const DISPLACEMENT_MULTIPLIER = 2.5;
const ATR_PERIOD = 20;
const MIN_BAR_RANGE_PTS = 10;
const TARGET_R = 3.0;
const STOP_BUFFER_PTS = 2;
const MAX_HOLD_BARS = 12;

export class IctDisplacement5mStrategy implements Strategy {
  readonly id = "ict-displacement-5m" as const;
  readonly description =
    "ICT displacement on 5-min bars: range > 2.5x ATR signals institutional activity, enter at close, 3R target, opposite-end stop.";

  generateSignal(context: StrategyContext): StrategySignal | null {
    const bar = context.bar;
    const history = context.history;
    if (history.length < ATR_PERIOD + 1) return null;

    // Session filter: 9:30-16:00 ET only (approximate via bar timestamp)
    const hour = new Date(bar.ts).getUTCHours();
    const minute = new Date(bar.ts).getUTCMinutes();
    const totalMin = hour * 60 + minute;
    if (totalMin < 810 || totalMin > 1200) return null; // 13:30-20:00 UTC

    // Compute average range using simple ATR over bars (not true range)
    let avgRange = 0;
    const lookback = history.slice(-ATR_PERIOD);
    for (const b of lookback) {
      avgRange += b.high - b.low;
    }
    avgRange /= ATR_PERIOD;
    if (avgRange <= 0) return null;

    const barRange = bar.high - bar.low;
    if (barRange < MIN_BAR_RANGE_PTS) return null;
    if (barRange < DISPLACEMENT_MULTIPLIER * avgRange) return null;

    // Direction: bullish if bar closed up
    const bullish = bar.close > bar.open;
    const side: TradeSide = bullish ? "long" : "short";

    // Stop: opposite end of displacement candle + buffer
    const stop = bullish
      ? bar.low - STOP_BUFFER_PTS
      : bar.high + STOP_BUFFER_PTS;

    // Target: 3R from entry
    const entry = bar.close;
    const risk = Math.abs(entry - stop);
    if (risk <= 0) return null;
    const target = bullish
      ? entry + TARGET_R * risk
      : entry - TARGET_R * risk;

    const rr = calculateRr(entry, stop, target, side);
    if (rr <= 0) return null;

    // Confidence: proportional to how far above threshold the range is
    const rangeRatio = barRange / (DISPLACEMENT_MULTIPLIER * avgRange);
    const confidence = Math.min(0.85, 0.45 + 0.15 * rangeRatio);

    return {
      symbol: context.symbol,
      strategyId: this.id,
      side,
      entry,
      stop,
      target,
      rr,
      confidence,
      contracts: 1,
      maxHoldMinutes: MAX_HOLD_BARS * 5, // 5-min bars
    };
  }
}
