import type { Bar, Strategy, StrategyContext, StrategySignal, TradeSide } from "../domain.js";
import { calculateRr } from "../risk/guardrails.js";
import { averageTrueRange } from "../utils/indicators.js";
import { isIndexSymbol } from "../utils/markets.js";
import { inferBarIntervalMinutes, minutesFromCtTime } from "../utils/time.js";

/**
 * ICT Market Structure Shift Breakout — Displacement candle
 * with three-candle trailing stop. ES/NQ morning session.
 */

function detectStructureShift(history: Bar[], lookback: number = 12): "bullish" | "bearish" | null {
  const recent = history.slice(-lookback);

  let higherHighs = 0;
  let higherLows = 0;
  let lowerHighs = 0;
  let lowerLows = 0;

  for (let i = 1; i < recent.length; i++) {
    if (recent[i].high > recent[i - 1].high) higherHighs++;
    if (recent[i].low > recent[i - 1].low) higherLows++;
    if (recent[i].high < recent[i - 1].high) lowerHighs++;
    if (recent[i].low < recent[i - 1].low) lowerLows++;
  }

  if (higherHighs >= 2 && higherLows >= 1) return "bullish";
  if (lowerHighs >= 2 && lowerLows >= 1) return "bearish";
  return null;
}

export class IctBreakoutStrategy implements Strategy {
  public readonly id = "ict-breakout";
  public readonly description =
    "ICT MSS breakout with displacement + three-candle trailing stop. ES/NQ morning session.";

  public generateSignal(context: StrategyContext): StrategySignal | null {
    if (!isIndexSymbol(context.symbol)) return null;
    if (context.symbol === "ES") return null; // NQ focused

    const prevBarTs = context.history[context.history.length - 1]?.ts;
    const barIntervalMinutes = inferBarIntervalMinutes(prevBarTs, context.bar.ts);
    if (barIntervalMinutes >= 720) return null;

    const sessionMinute = minutesFromCtTime(context.bar.ts, context.config.guardrails.sessionStartCt);
    if (sessionMinute < 15 || sessionMinute > 150) return null;

    const history = context.history;
    if (history.length < 30) return null;

    const atr = averageTrueRange(history, Math.min(14, history.length));
    if (atr <= 0) return null;

    const bar = context.bar;
    const barRange = bar.high - bar.low;
    if (barRange < atr * 0.8) return null; // Too small to matter

    const structure = detectStructureShift(history, 12);
    if (!structure) return null;

    const averageVolume = history.slice(-14).reduce((sum, b) => sum + (b.volume ?? 0), 0) / 14;
    const volumeSpike = bar.volume && bar.volume > averageVolume * 1.2;

    // Displacement: range > ATR (relaxed from 1.5x)
    const displacement = barRange > atr;
    if (!displacement) return null;

    let side: TradeSide;
    let stop: number;

    if (structure === "bullish" && bar.close > bar.open) {
      side = "long";
      stop = Math.min(bar.low, ...history.slice(-3).map((b) => b.low)) - atr * 0.2;
    } else if (structure === "bearish" && bar.close < bar.open) {
      side = "short";
      stop = Math.max(bar.high, ...history.slice(-3).map((b) => b.high)) + atr * 0.2;
    } else {
      return null;
    }

    const entry = bar.close;
    const risk = Math.abs(entry - stop);
    if (risk <= 0 || risk < atr * 0.15) return null;

    // Three-candle trailing stop
    const last3 = history.slice(-3);
    let trailStop: number;
    if (side === "long") {
      trailStop = Math.min(...last3.map((b) => b.low));
      if (trailStop > stop) stop = trailStop; // Use the tighter (higher) stop
    } else {
      trailStop = Math.max(...last3.map((b) => b.high));
      if (trailStop < stop) stop = trailStop; // Use the tighter (lower) stop
    }

    const finalRisk = Math.abs(entry - stop);
    if (finalRisk <= 0) return null;

    const targetMultiplier = Math.max(2.5, context.config.guardrails.minRr);
    const target = side === "long" ? entry + finalRisk * targetMultiplier : entry - finalRisk * targetMultiplier;
    const rr = calculateRr(entry, stop, target, side);
    if (rr <= 0) return null;

    let confidence = 0.55;
    if (volumeSpike) confidence += 0.15;
    if (barRange > atr * 1.5) confidence += 0.1;
    confidence = Math.max(0.18, Math.min(0.88, confidence));

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
      maxHoldMinutes: 45,
      meta: {
        pattern: "mss-displacement-breakout",
        structure,
        atr,
        barRange,
        volumeSpike,
        rangeAtrRatio: Number((barRange / atr).toFixed(2))
      }
    };
  }
}