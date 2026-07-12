import type { Bar, Strategy, StrategyContext, StrategySignal, TradeSide } from "../domain.js";
import { calculateRr } from "../risk/guardrails.js";
import { averageTrueRange } from "../utils/indicators.js";
import { isIndexSymbol } from "../utils/markets.js";
import { inferBarIntervalMinutes, minutesFromCtTime } from "../utils/time.js";

/**
 * ICT Liquidity Sweep & Reversion
 * Looks for equal highs/lows with wider tolerance, then reversion entry.
 */

function findEqualLevel(history: Bar[], lookback: number): { level: number; type: "high" | "low"; tolerance: number } | null {
  const highClusters: number[] = [];
  const lowClusters: number[] = [];

  for (let i = history.length - lookback; i < history.length; i++) {
    highClusters.push(history[i].high);
    lowClusters.push(history[i].low);
  }

  highClusters.sort((a, b) => a - b);
  lowClusters.sort((a, b) => a - b);

  // Find clusters of similar highs (within 0.3% tolerance)
  for (let i = 0; i < highClusters.length - 1; i++) {
    const avg = (highClusters[i] + highClusters[i + 1]) / 2;
    const tol = avg * 0.003;
    let count = 1;
    for (let j = i + 1; j < highClusters.length; j++) {
      if (Math.abs(highClusters[j] - avg) <= tol) count++;
      else break;
    }
    if (count >= 2 && i < highClusters.length - 2) return { level: avg, type: "high", tolerance: tol };
  }

  // Find clusters of similar lows
  for (let i = 0; i < lowClusters.length - 1; i++) {
    const avg = (lowClusters[i] + lowClusters[i + 1]) / 2;
    const tol = avg * 0.003;
    let count = 1;
    for (let j = i + 1; j < lowClusters.length; j++) {
      if (Math.abs(lowClusters[j] - avg) <= tol) count++;
      else break;
    }
    if (count >= 2 && i < lowClusters.length - 2) return { level: avg, type: "low", tolerance: tol };
  }

  return null;
}

export class IctSweepReversionStrategy implements Strategy {
  public readonly id = "ict-sweep-reversion";
  public readonly description = "ICT liquidity sweep into equal level zone with FVG reversion. ES/NQ only.";

  public generateSignal(context: StrategyContext): StrategySignal | null {
    if (!isIndexSymbol(context.symbol)) return null;
    if (context.symbol === "ES") return null; // NQ focused

    const prevBarTs = context.history[context.history.length - 1]?.ts;
    const barIntervalMinutes = inferBarIntervalMinutes(prevBarTs, context.bar.ts);
    if (barIntervalMinutes >= 720) return null;

    const sessionMinute = minutesFromCtTime(context.bar.ts, context.config.guardrails.sessionStartCt);
    if (sessionMinute < 30 || sessionMinute > 180) return null; // 09:00 - 11:30

    const history = context.history;
    if (history.length < 50) return null;

    const atr = averageTrueRange(history, Math.min(14, history.length));
    if (atr <= 0) return null;

    const bar = context.bar;
    const equalLevel = findEqualLevel(history, 50);
    if (!equalLevel) return null;

    // Has price swept through the level?
    const sweptHigh = equalLevel.type === "high" && bar.high > equalLevel.level + equalLevel.tolerance;
    const sweptLow = equalLevel.type === "low" && bar.low < equalLevel.level - equalLevel.tolerance;

    if (!sweptHigh && !sweptLow) return null;

    // Look for FVG on the other side (reversion signal)
    let side: TradeSide;
    let target: number;

    // After sweeping equal highs, look for bearish FVG (short entry)
    // After sweeping equal lows, look for bullish FVG (long entry)
    if (sweptHigh) {
      side = "short";
      target = equalLevel.level - atr * 0.5;
      // Stop above the swept level
      const stop = equalLevel.level + atr * 0.5;
      const entry = bar.close;
      const risk = Math.abs(entry - stop);
      if (risk <= 0 || risk < atr * 0.2) return null;
      if (entry >= stop) return null; // Must be below stop

      const rr = calculateRr(entry, stop, target, side);
      if (rr < 2.0) return null;

      return {
        symbol: context.symbol,
        strategyId: this.id,
        side,
        entry,
        stop,
        target,
        rr,
        confidence: 0.6,
        contracts: 1,
        maxHoldMinutes: 45,
        meta: { pattern: "equal-level-sweep", level: equalLevel.level, type: equalLevel.type }
      };
    }

    if (sweptLow) {
      side = "long";
      target = equalLevel.level + atr * 0.5;
      const stop = equalLevel.level - atr * 0.5;
      const entry = bar.close;
      const risk = Math.abs(entry - stop);
      if (risk <= 0 || risk < atr * 0.2) return null;
      if (entry <= stop) return null; // Must be above stop

      const rr = calculateRr(entry, stop, target, side);
      if (rr < 2.0) return null;

      return {
        symbol: context.symbol,
        strategyId: this.id,
        side,
        entry,
        stop,
        target,
        rr,
        confidence: 0.6,
        contracts: 1,
        maxHoldMinutes: 45,
        meta: { pattern: "equal-level-sweep", level: equalLevel.level, type: equalLevel.type }
      };
    }

    return null;
  }
}