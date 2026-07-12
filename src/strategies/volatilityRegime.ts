import type { Strategy, StrategyContext, StrategySignal, TradeSide } from "../domain.js";
import { calculateRr } from "../risk/guardrails.js";
import { averageTrueRange } from "../utils/indicators.js";
import { isIndexSymbol } from "../utils/markets.js";
import { inferBarIntervalMinutes, minutesFromCtTime } from "../utils/time.js";
import { getMarketSessionWindow } from "../utils/sessions.js";
import { classifyVixRegime } from "../signals/vixContangoFlag.js";

function buildSignal(args: {
  context: StrategyContext;
  side: TradeSide;
  stop: number;
  target: number;
  confidence: number;
  barIntervalMinutes: number;
  regime: "low-vol" | "high-vol";
  atrRatio: number;
}): StrategySignal | null {
  const { context, side, stop, target, confidence, barIntervalMinutes, regime, atrRatio } = args;
  const entry = context.bar.close;
  const rr = calculateRr(entry, stop, target, side);

  if (rr <= 0) {
    return null;
  }

  return {
    symbol: context.symbol,
    strategyId: "volatility-regime",
    side,
    entry,
    stop,
    target,
    rr,
    confidence,
    contracts: 1,
    maxHoldMinutes: 25,
    meta: {
      regime,
      atrRatio: Number(atrRatio.toFixed(4)),
      barIntervalMinutes
    }
  };
}

export class VolatilityRegimeStrategy implements Strategy {
  public readonly id = "volatility-regime";
  public readonly description = "Meta-strategy that adapts to volatility regime: trend-following in low-vol, mean-reversion in high-vol. Cycle 14: VIX term structure overrides ATR-based regime detection.";

  public generateSignal(context: StrategyContext): StrategySignal | null {
    const prevBarTs = context.history[context.history.length - 1]?.ts;
    const barIntervalMinutes = inferBarIntervalMinutes(prevBarTs, context.bar.ts);
    const dailyLike = barIntervalMinutes >= 720;
    const sourceHistory = dailyLike ? context.history : context.sessionHistory;

    const fastPeriod = context.config.tuning.volRegimeAtrFast;
    const slowPeriod = context.config.tuning.volRegimeAtrSlow;
    const regimeThreshold = context.config.tuning.volRegimeThreshold;

    if (sourceHistory.length < slowPeriod + 2) {
      return null;
    }

    const sessionWindow = getMarketSessionWindow(context.symbol, context.config.guardrails.sessionStartCt);
    const sessionMinute = minutesFromCtTime(context.bar.ts, sessionWindow.startCt);
    if (!dailyLike && sessionMinute < 10) {
      return null;
    }

    // Compute ATR ratio: fast ATR / slow ATR
    const fastAtr = averageTrueRange(sourceHistory, fastPeriod);
    const slowAtr = averageTrueRange(sourceHistory, slowPeriod);

    if (fastAtr <= 0 || slowAtr <= 0) {
      return null;
    }

    const atrRatio = fastAtr / slowAtr;
    const atrHighVol = atrRatio > regimeThreshold;

    // --- VIX regime override (Cycle 14: Tier 1 scaffolding) ---
    // When VIX is in backwardation, force high-vol mode regardless of ATR ratio.
    // VIX contango confirms low-vol and adds confidence to ATR-based detection.
    const vixPayload: { spot: number; front: number; second?: number } | undefined = (context as any).vixData;
    const vixRegime = vixPayload
      ? classifyVixRegime({ vixSpot: vixPayload.spot, frontMonthFuture: vixPayload.front, secondMonthFuture: vixPayload.second })
      : null;
    const vixForcesHighVol = vixRegime?.regime === "backwardation";
    const vixConfirmsLowVol = vixRegime?.regime === "contango";

    // Regime: VIX backwardation overrides ATR (stress trumps local vol)
    const isHighVol = vixForcesHighVol || atrHighVol;
    // VIX contango adds confidence when ATR also says low-vol
    const regimeConfidenceBonus = (vixConfirmsLowVol && !atrHighVol) ? 0.04 : (vixForcesHighVol ? 0.06 : 0);

    const barRange = context.bar.high - context.bar.low;
    if (barRange > fastAtr * context.config.tuning.volatilityKillAtrMultiple) {
      return null;
    }

    const lookback = dailyLike ? 4 : 10;
    const recent = sourceHistory.slice(-lookback);
    const recentHigh = Math.max(...recent.map((b) => b.high));
    const recentLow = Math.min(...recent.map((b) => b.low));

    if (isHighVol) {
      // HIGH VOLATILITY => mean-reversion: fade moves away from recent range mid
      // Cycle 14: VIX backwardation adds +0.06 confidence to fade signals
      const midRange = (recentHigh + recentLow) / 2;
      const deviation = context.bar.close - midRange;
      const targetRr = Math.max(context.config.guardrails.minRr, 2.2);

      if (context.bar.close > recentHigh && deviation > fastAtr * 0.5) {
        // Price pushed above range, fade short
        const stop = context.bar.close + fastAtr * 0.75;
        const risk = stop - context.bar.close;
        if (risk <= 0) return null;
        return buildSignal({
          context,
          side: "short",
          stop,
          target: midRange,
          confidence: Math.min(0.72, 0.62 + regimeConfidenceBonus),
          barIntervalMinutes,
          regime: "high-vol",
          atrRatio
        });
      }

      if (context.bar.close < recentLow && -deviation > fastAtr * 0.5) {
        // Price pushed below range, fade long
        const stop = context.bar.close - fastAtr * 0.75;
        const risk = context.bar.close - stop;
        if (risk <= 0) return null;
        return buildSignal({
          context,
          side: "long",
          stop,
          target: midRange,
          confidence: Math.min(0.72, 0.62 + regimeConfidenceBonus),
          barIntervalMinutes,
          regime: "high-vol",
          atrRatio
        });
      }

      return null;
    }

    // LOW VOLATILITY => trend-following: continuation breakouts with momentum
    // Cycle 14: VIX contango confirmation adds +0.04 confidence to breakout signals
    const targetRr = Math.max(context.config.guardrails.minRr, 2.6);
    const body = Math.abs(context.bar.close - context.bar.open);

    if (context.bar.close > recentHigh && context.bar.close > context.bar.open && body > fastAtr * 0.2) {
      // Bullish breakout in low-vol => ride the trend
      const stop = Math.min(recentLow, context.bar.close - fastAtr * 1.0);
      const risk = context.bar.close - stop;
      if (risk <= 0) return null;
      return buildSignal({
        context,
        side: "long",
        stop,
        target: context.bar.close + risk * targetRr,
        confidence: Math.min(0.78, 0.68 + regimeConfidenceBonus),
        barIntervalMinutes,
        regime: "low-vol",
        atrRatio
      });
    }

    if (context.bar.close < recentLow && context.bar.close < context.bar.open && body > fastAtr * 0.2) {
      // Bearish breakout in low-vol => ride the trend
      const stop = Math.max(recentHigh, context.bar.close + fastAtr * 1.0);
      const risk = stop - context.bar.close;
      if (risk <= 0) return null;
      return buildSignal({
        context,
        side: "short",
        stop,
        target: context.bar.close - risk * targetRr,
        confidence: Math.min(0.76, 0.66 + regimeConfidenceBonus),
        barIntervalMinutes,
        regime: "low-vol",
        atrRatio
      });
    }

    return null;
  }
}
