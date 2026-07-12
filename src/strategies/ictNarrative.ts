import type { Bar, Strategy, StrategyContext, StrategySignal, TradeSide } from "../domain.js";
import { calculateRr } from "../risk/guardrails.js";
import { averageTrueRange } from "../utils/indicators.js";
import { isIndexSymbol } from "../utils/markets.js";
import { inferBarIntervalMinutes, minutesFromCtTime } from "../utils/time.js";

/**
 * ICT Narrative Trading — FVG Entry with Session Filter
 * Simplified: Drop strict HTF bias, focus on FVG entries in kill zone.
 * The bias comes from direction of the FVG itself + bar close context.
 */

function findFvg(history: Bar[], index: number): { start: number; end: number; direction: "bullish" | "bearish" } | null {
  if (index < 2) return null;
  const c1 = history[index - 2];
  const c2 = history[index - 1];
  const c3 = history[index];

  if (c2.low > c1.high && c2.low > c3.high) {
    return { start: c1.high, end: c2.low, direction: "bullish" };
  }
  if (c2.high < c1.low && c2.high < c3.low) {
    return { start: c2.high, end: c1.low, direction: "bearish" };
  }
  if (c1.low > c2.high && c3.low > c2.high) {
    return { start: c2.high, end: c1.low, direction: "bearish" };
  }
  if (c1.high < c2.low && c3.high < c2.low) {
    return { start: c1.high, end: c2.low, direction: "bullish" };
  }
  return null;
}

function trailingStop(history: Bar[], side: TradeSide): number {
  const last3 = history.slice(-3);
  if (side === "long") return Math.min(...last3.map((b) => b.low));
  return Math.max(...last3.map((b) => b.high));
}

export class IctNarrativeStrategy implements Strategy {
  public readonly id = "ict-narrative";
  public readonly description = "ICT narrative: FVG entry in kill zone 08:30-11:00 ET. ES/NQ.";

  public generateSignal(context: StrategyContext): StrategySignal | null {
    if (!isIndexSymbol(context.symbol)) return null;
    if (context.symbol === "ES") return null; // NQ only — ES underperforms

    const prevBarTs = context.history[context.history.length - 1]?.ts;
    const barIntervalMinutes = inferBarIntervalMinutes(prevBarTs, context.bar.ts);
    if (barIntervalMinutes >= 720) return null;

    const sessionMinute = minutesFromCtTime(context.bar.ts, context.config.guardrails.sessionStartCt);
    if (sessionMinute < 80 || sessionMinute > 150) return null; // 09:20 - 11:00

    const history = context.history;
    if (history.length < 40) return null;

    const atr = averageTrueRange(history, Math.min(20, history.length));
    if (atr <= 0) return null;

    const bar = context.bar;
    const barRange = bar.high - bar.low;
    if (barRange > atr * 2.5) return null; // Skip wicks/noise bars

    const fvg = findFvg(history, history.length - 1);
    if (!fvg) return null;

    const fvgSize = fvg.end - fvg.start;
    if (fvgSize <= 0 || fvgSize > atr * 3) return null; // FVG must be reasonable size

    // Check if current bar overlaps with the FVG zone
    const overlapsFvg =
      (fvg.direction === "bullish" && bar.low <= fvg.end && bar.close >= fvg.start) ||
      (fvg.direction === "bearish" && bar.high >= fvg.start && bar.close <= fvg.end);

    if (!overlapsFvg) return null;

    let side: TradeSide;
    let stop: number;
    let entry: number;

    if (fvg.direction === "bullish") {
      side = "long";
      entry = bar.close;
      stop = Math.min(bar.low, fvg.start) - atr * 0.2;
    } else {
      side = "short";
      entry = bar.close;
      stop = Math.max(bar.high, fvg.end) + atr * 0.2;
    }

    const risk = Math.abs(entry - stop);
    if (risk <= 0 || risk < atr * 0.15) return null;

    const targetMultiplier = Math.max(2.5, context.config.guardrails.minRr);
    const target = side === "long" ? entry + risk * targetMultiplier : entry - risk * targetMultiplier;
    const rr = calculateRr(entry, stop, target, side);
    if (rr <= 0) return null;

    let confidence = 0.65;
    if (fvgSize < atr * 0.5) confidence += 0.1; // Tighter FVG = better
    if (barRange < atr * 0.8) confidence += 0.1; // Tighter candle = better
    confidence = Math.max(0.18, Math.min(0.85, confidence));

    const ts = trailingStop(history, side);
    const finalStop = side === "long" ? Math.min(stop, ts) : Math.max(stop, ts);

    return {
      symbol: context.symbol,
      strategyId: this.id,
      side,
      entry,
      stop: finalStop,
      target,
      rr,
      confidence,
      contracts: 1,
      maxHoldMinutes: 60,
      meta: { pattern: "fvg-entry", fvgDirection: fvg.direction, fvgSize, atr }
    };
  }
}