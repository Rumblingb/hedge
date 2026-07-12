import type { Strategy, StrategyContext, StrategySignal, TradeSide } from "../domain.js";
import { calculateRr } from "../risk/guardrails.js";
import { averageTrueRange } from "../utils/indicators.js";

const STRATEGY_ID = "vol-scaled-breakout-momentum";
const TARGET_SYMBOLS = new Set(["ES", "NQ", "CL", "GC", "ZN"]);

function high(history: Array<{ high: number }>, period: number): number {
  return Math.max(...history.slice(-period).map((bar) => bar.high));
}

function low(history: Array<{ low: number }>, period: number): number {
  return Math.min(...history.slice(-period).map((bar) => bar.low));
}

function confidenceFrom(args: {
  momentumPct: number;
  volumeRatio: number;
  atrRatio: number;
  macroAligned: boolean;
}): number {
  const momentumScore = Math.min(0.08, Math.abs(args.momentumPct) * 8);
  const volumeScore = Math.min(0.06, Math.max(0, args.volumeRatio - 1) * 0.03);
  const volatilityPenalty = Math.max(0, args.atrRatio - 1.6) * 0.05;
  const macroBonus = args.macroAligned ? 0.03 : 0;
  return Math.max(0.45, Math.min(0.68, 0.5 + momentumScore + volumeScore + macroBonus - volatilityPenalty));
}

function buildSignal(args: {
  context: StrategyContext;
  side: TradeSide;
  stop: number;
  target: number;
  confidence: number;
  lookback: number;
  momentumPct: number;
  volumeRatio: number;
  atrRatio: number;
  macroAligned: boolean;
}): StrategySignal | null {
  const entry = args.context.bar.close;
  const rr = calculateRr(entry, args.stop, args.target, args.side);
  if (rr <= 0) return null;
  return {
    symbol: args.context.symbol,
    strategyId: STRATEGY_ID,
    side: args.side,
    entry,
    stop: args.stop,
    target: args.target,
    rr,
    confidence: args.confidence,
    contracts: 1,
    maxHoldMinutes: 90,
    meta: {
      pattern: "donchian-vol-scaled-intraday-momentum",
      lookback: args.lookback,
      momentumPct: Number(args.momentumPct.toFixed(6)),
      volumeRatio: Number(args.volumeRatio.toFixed(4)),
      atrRatio: Number(args.atrRatio.toFixed(4)),
      macroAligned: args.macroAligned
    }
  };
}

export class VolScaledBreakoutMomentumStrategy implements Strategy {
  public readonly id = STRATEGY_ID;
  public readonly description =
    "Vol-scaled breakout momentum: Donchian breakout confirmed by short-horizon momentum, participation, and volatility-normalized risk. Research-only until OOS/demo gates pass.";

  public generateSignal(context: StrategyContext): StrategySignal | null {
    if (!TARGET_SYMBOLS.has(context.symbol.toUpperCase())) return null;
    if (context.dailyTradeCount > 0) return null;

    const history = context.history;
    if (history.length < 64) return null;

    const lookback = 40;
    const channelHigh = high(history, lookback);
    const channelLow = low(history, lookback);
    const atrFast = averageTrueRange(history.slice(-18), 14);
    const atrSlow = averageTrueRange(history.slice(-64), 50);
    if (atrFast <= 0 || atrSlow <= 0) return null;

    const atrRatio = atrFast / atrSlow;
    if (atrRatio > 2.2) return null;

    const momentumAnchor = history.at(-8);
    if (!momentumAnchor || momentumAnchor.close <= 0) return null;
    const momentumPct = (context.bar.close - momentumAnchor.close) / momentumAnchor.close;

    const recent = history.slice(-20);
    const avgVolume = recent.reduce((sum, bar) => sum + bar.volume, 0) / recent.length;
    const volumeRatio = avgVolume > 0 ? context.bar.volume / avgVolume : 1;
    if (volumeRatio < 0.85) return null;

    const macroDir = context.macro?.kronosDirection;
    const macroConf = context.macro?.kronosConfidence ?? 0;
    const longMacroAligned = macroDir === undefined || macroConf < 0.35 || macroDir >= -0.05;
    const shortMacroAligned = macroDir === undefined || macroConf < 0.35 || macroDir <= 0.05;

    if (context.bar.close > channelHigh && momentumPct > 0.0015 && longMacroAligned) {
      const stop = context.bar.close - Math.max(atrFast * 1.05, context.bar.close - channelHigh + atrFast * 0.5);
      const risk = context.bar.close - stop;
      const target = context.bar.close + risk * 2.4;
      return buildSignal({
        context,
        side: "long",
        stop,
        target,
        confidence: confidenceFrom({ momentumPct, volumeRatio, atrRatio, macroAligned: macroDir !== undefined && macroDir > 0 }),
        lookback,
        momentumPct,
        volumeRatio,
        atrRatio,
        macroAligned: macroDir !== undefined && macroDir > 0
      });
    }

    if (context.bar.close < channelLow && momentumPct < -0.0015 && shortMacroAligned) {
      const stop = context.bar.close + Math.max(atrFast * 1.05, channelLow - context.bar.close + atrFast * 0.5);
      const risk = stop - context.bar.close;
      const target = context.bar.close - risk * 2.4;
      return buildSignal({
        context,
        side: "short",
        stop,
        target,
        confidence: confidenceFrom({ momentumPct, volumeRatio, atrRatio, macroAligned: macroDir !== undefined && macroDir < 0 }),
        lookback,
        momentumPct,
        volumeRatio,
        atrRatio,
        macroAligned: macroDir !== undefined && macroDir < 0
      });
    }

    return null;
  }
}
