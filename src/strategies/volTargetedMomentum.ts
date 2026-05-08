/**
 * # Volatility-Targeted Momentum Breakout Strategy
 * Source: "Intraday Momentum Breakout Strategy: A Volatility-Targeted Approach"
 *   misango.me, Feb 2026
 *
 * Core concept: Use ATR-based "noise area" boundaries. A breakout beyond
 * the noise area + volume confirmation = momentum entry. Vol-targeted
 * sizing: risk = 0.3 * ATR — conservative for prop firm use.
 *
 * Key decision rules:
 * - Noise area = recent range (high-low over last N bars)
 * - Breakout: price > noise_high AND volume > 1.5x avg → long
 * - Breakdown: price < noise_low AND volume > 1.5x avg → short
 * - Vol-targeted stop: risk = 0.3 * ATR (tight, vol-aware)
 * - Targets: ES, NQ only (index futures)
 * - Session filter: wait 15 min after open
 */
import type { Strategy, StrategyContext, StrategySignal, TradeSide } from "../domain.js";
import { calculateRr } from "../risk/guardrails.js";
import { averageTrueRange } from "../utils/indicators.js";
import { isIndexSymbol } from "../utils/markets.js";
import { getMarketSessionWindow } from "../utils/sessions.js";
import { inferBarIntervalMinutes, minutesFromCtTime } from "../utils/time.js";

/** Only ES and NQ — index futures with liquid intraday profiles. */
const TARGET_SYMBOLS = new Set(["ES", "NQ"]);

/** Volume threshold: require 1.5x average volume for breakout confirmation. */
const VOLUME_MULTIPLIER = 1.5;

/** Vol-targeted risk fraction: conservative 0.3 * ATR for prop firm safety. */
const VOL_RISK_ATR_MULTIPLE = 0.3;

/** Session warmup: wait 15 minutes after open before firing signals. */
const SESSION_WARMUP_MINUTES = 15;

function buildSignal(args: {
  context: StrategyContext;
  side: TradeSide;
  stop: number;
  target: number;
  confidence: number;
  barIntervalMinutes: number;
  noiseLookback: number;
  atr: number;
}): StrategySignal | null {
  const { context, side, stop, target, confidence, barIntervalMinutes, noiseLookback, atr } = args;
  const entry = context.bar.close;
  const rr = calculateRr(entry, stop, target, side);

  if (rr <= 0) {
    return null;
  }

  return {
    symbol: context.symbol,
    strategyId: "vol-targeted-momentum",
    side,
    entry,
    stop,
    target,
    rr,
    confidence,
    contracts: 1,
    maxHoldMinutes: 20,
    meta: {
      noiseLookbackBars: noiseLookback,
      atr: Math.round(atr * 100) / 100,
      volRiskMultiple: VOL_RISK_ATR_MULTIPLE,
      volumeMultiplier: VOLUME_MULTIPLIER,
      barIntervalMinutes,
      paper: "misango.me, Feb 2026",
    },
  };
}

export class VolTargetedMomentumStrategy implements Strategy {
  public readonly id = "vol-targeted-momentum";
  public readonly description =
    "Intraday momentum breakout with volume confirmation and " +
    "volatility-targeted risk sizing (0.3×ATR stop). " +
    "ES/NQ only. Source: misango.me, Feb 2026.";

  public generateSignal(context: StrategyContext): StrategySignal | null {
    // -- Symbol gate: ES / NQ only -------------------------------------------
    if (!TARGET_SYMBOLS.has(context.symbol)) {
      return null;
    }

    // -- Bar interval detection ----------------------------------------------
    const prevBarTs = context.history[context.history.length - 1]?.ts;
    const barIntervalMinutes = inferBarIntervalMinutes(prevBarTs, context.bar.ts);
    const dailyLike = barIntervalMinutes >= 720;
    const sourceHistory = dailyLike ? context.history : context.sessionHistory;
    const noiseLookback = context.config.tuning.momentumLookbackBars;

    if (sourceHistory.length < noiseLookback) {
      return null;
    }

    // -- Session filter: wait 15 min after open ------------------------------
    if (!dailyLike && isIndexSymbol(context.symbol)) {
      const sessionWindow = getMarketSessionWindow(
        context.symbol,
        context.config.guardrails.sessionStartCt,
      );
      const sessionMinute = minutesFromCtTime(context.bar.ts, sessionWindow.startCt);
      if (sessionMinute < SESSION_WARMUP_MINUTES) {
        return null;
      }
    }

    // -- Noise area: recent high-low range over lookback --------------------
    const recent = sourceHistory.slice(-noiseLookback);
    const noiseHigh = Math.max(...recent.map((bar) => bar.high));
    const noiseLow = Math.min(...recent.map((bar) => bar.low));
    const avgVolume =
      recent.reduce((sum, bar) => sum + bar.volume, 0) / recent.length;
    const needsVolume = avgVolume * VOLUME_MULTIPLIER;

    // -- ATR for vol-targeted risk sizing -----------------------------------
    const atrPeriod = Math.min(14, Math.max(5, noiseLookback + 2));
    const atr = averageTrueRange(sourceHistory, atrPeriod);
    if (atr <= 0) {
      return null;
    }

    // -- Volatility kill: skip if bar range exceeds extreme vol threshold ---
    const barRange = context.bar.high - context.bar.low;
    if (barRange > atr * context.config.tuning.volatilityKillAtrMultiple) {
      return null;
    }

    // -- Target R:R ---------------------------------------------------------
    const targetRr = Math.max(
      context.config.guardrails.minRr,
      context.config.tuning.measuredMoveRr,
    );

    // -- Volume-confirmed breakout (long) -----------------------------------
    if (context.bar.close > noiseHigh && context.bar.volume >= needsVolume) {
      const risk = atr * VOL_RISK_ATR_MULTIPLE;
      const stop = context.bar.close - risk;
      if (stop >= context.bar.close) {
        return null;
      }
      return buildSignal({
        context,
        side: "long",
        stop,
        target: context.bar.close + risk * targetRr,
        confidence: 0.70,
        barIntervalMinutes,
        noiseLookback,
        atr,
      });
    }

    // -- Volume-confirmed breakdown (short) ---------------------------------
    if (context.bar.close < noiseLow && context.bar.volume >= needsVolume) {
      const risk = atr * VOL_RISK_ATR_MULTIPLE;
      const stop = context.bar.close + risk;
      if (stop <= context.bar.close) {
        return null;
      }
      return buildSignal({
        context,
        side: "short",
        stop,
        target: context.bar.close - risk * targetRr,
        confidence: 0.68,
        barIntervalMinutes,
        noiseLookback,
        atr,
      });
    }

    return null;
  }
}
