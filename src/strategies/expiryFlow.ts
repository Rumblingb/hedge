import { DateTime } from "luxon";
import type { Strategy, StrategyContext, StrategySignal, TradeSide } from "../domain.js";
import { calculateRr } from "../risk/guardrails.js";
import { averageTrueRange } from "../utils/indicators.js";
import { isIndexSymbol } from "../utils/markets.js";
import { getMarketSessionWindow } from "../utils/sessions.js";
import { chicagoTime, inferBarIntervalMinutes, minutesFromCtTime } from "../utils/time.js";
import {
  buildExpiryCalendar,
  getExpiryProximity,
  type ExpiryProximity
} from "../utils/expiryCalendar.js";
import { computeGammaFeature, getFuturesBeta } from "../signals/expiryFlowGammaFeature.js";
import { classifyVixRegime } from "../signals/vixContangoFlag.js";
import type { PolygonOptionSnapshot } from "../research/options.js";

// Cache calendar per month-bucket to avoid rebuilding every bar
const calendarCache = new Map<string, ReturnType<typeof buildExpiryCalendar>>();

function getCalendar(barIso: string) {
  const ct = chicagoTime(barIso);
  const key = `${ct.year}-${ct.month}`;
  if (!calendarCache.has(key)) {
    calendarCache.set(key, buildExpiryCalendar(ct.startOf("month"), 3));
  }
  return calendarCache.get(key)!;
}

function buildSignal(args: {
  context: StrategyContext;
  side: TradeSide;
  stop: number;
  target: number;
  confidence: number;
  barIntervalMinutes: number;
  proximity: ExpiryProximity;
}): StrategySignal | null {
  const { context, side, stop, target, confidence, barIntervalMinutes, proximity } = args;
  const entry = context.bar.close;
  const rr = calculateRr(entry, stop, target, side);
  if (rr <= 0) return null;

  return {
    symbol: context.symbol,
    strategyId: "expiry-flow",
    side,
    entry,
    stop,
    target,
    rr,
    confidence,
    contracts: 1,
    maxHoldMinutes: 30,
    meta: {
      barIntervalMinutes,
      daysToNearest: proximity.daysToNearest,
      nearestKind: proximity.nearestKind ?? "",
      isOpexDay: proximity.isOpexDay,
      isVixDay: proximity.isVixDay,
      isQuarterlyExpiryDay: proximity.isQuarterlyExpiryDay,
      inRollWindow: proximity.inRollWindow
    }
  };
}

export class ExpiryFlowStrategy implements Strategy {
  public readonly id = "expiry-flow";
  public readonly description =
    "Exploits forced dealer hedge unwinds and fund roll flows near monthly OPEX, quarterly CME expiry, and VIX settlement Wednesdays. Index-only. Cycle 14: Tier 1 gamma + VIX scaffolding augments signal confidence.";

  public generateSignal(context: StrategyContext): StrategySignal | null {
    if (!isIndexSymbol(context.symbol)) return null;

    const prevBarTs = context.history[context.history.length - 1]?.ts;
    const barIntervalMinutes = inferBarIntervalMinutes(prevBarTs, context.bar.ts);
    const dailyLike = barIntervalMinutes >= 720;
    const sourceHistory = dailyLike ? context.history : context.sessionHistory;

    if (sourceHistory.length < 8) return null;

    const calendar = getCalendar(context.bar.ts);
    const ct = chicagoTime(context.bar.ts);
    const barDateStr = ct.toISODate()!;
    const proximity = getExpiryProximity(barDateStr, calendar);

    // Only activate within 3 trading days of any expiry event
    if (!proximity.isOpexDay && !proximity.isVixDay && !proximity.inRollWindow && proximity.daysToNearest > 3) {
      return null;
    }

    const sessionWindow = getMarketSessionWindow(context.symbol, context.config.guardrails.sessionStartCt);
    const sessionMinute = minutesFromCtTime(context.bar.ts, sessionWindow.startCt);

    // --- External signal augmentation (Cycle 14: Tier 1 scaffolding) ---
    // Gamma exposure feature: high gamma → amplified dealer flow on OPEX/quarterly
    const optionSnapshots: PolygonOptionSnapshot[] | undefined = (context as any).optionSnapshots;
    const gammaFeature = optionSnapshots?.length
      ? computeGammaFeature({
          snapshots: optionSnapshots,
          beta: getFuturesBeta(context.symbol),
          minOpenInterest: 50,
          maxDte: 5
        })
      : null;

    // VIX contango regime: backwardation → stress, reduce momentum confidence
    const vixPayload: { spot: number; front: number; second?: number } | undefined = (context as any).vixData;
    const vixRegime = vixPayload
      ? classifyVixRegime({ vixSpot: vixPayload.spot, frontMonthFuture: vixPayload.front, secondMonthFuture: vixPayload.second })
      : null;

    // Gamma squeeze boost: when gammaSqueezeRisk is active, increase fade conviction on OPEX
    const gammaBoost = gammaFeature?.gammaSqueezeRisk ? 0.08 : 0;
    // VIX stress penalty: backwardation reduces momentum signal confidence
    const vixStressPenalty = vixRegime?.regime === "backwardation" ? 0.10 : 0;

    // Only act in the first 90 minutes of the RTH session (forced unwinds happen at open)
    if (!dailyLike && (sessionMinute < 10 || sessionMinute > 90)) return null;

    const atr = averageTrueRange(sourceHistory, 14);
    if (atr <= 0) return null;

    const lookback = dailyLike ? 5 : Math.min(sourceHistory.length, 12);
    const recent = sourceHistory.slice(-lookback);
    const rangeHigh = Math.max(...recent.map((b) => b.high));
    const rangeLow = Math.min(...recent.map((b) => b.low));
    const rangeSize = rangeHigh - rangeLow;

    // Require a meaningful range to define the fade boundaries
    if (rangeSize < atr * 0.4) return null;

    const bar = context.bar;
    const body = Math.abs(bar.close - bar.open);
    const upperWick = bar.high - Math.max(bar.open, bar.close);
    const lowerWick = Math.min(bar.open, bar.close) - bar.low;

    // --- OPEX / Quarterly fade logic ---
    // On OPEX Friday (and quarterly), dealers that were long gamma are now flat.
    // Initial range breakouts tend to reverse as the hedging pressure dissipates.
    // Signal: bar closes near the range extreme with a rejection wick → fade it.
    // Cycle 14: gammaSqueezeRisk boosts fade conviction (+0.08).
    if (proximity.isOpexDay || proximity.isQuarterlyExpiryDay) {
      const quarterlyBoost = proximity.isQuarterlyExpiryDay ? 0.1 : 0;

      // Fade a push above range high (long wick, close well below high)
      if (
        bar.high > rangeHigh &&
        upperWick > body * 1.2 &&
        bar.close < rangeHigh &&
        bar.close > rangeLow
      ) {
        const stop = bar.high + atr * 0.25;
        const target = rangeLow + (rangeSize * 0.3);
        return buildSignal({
          context,
          side: "short",
          stop,
          target,
          confidence: Math.min(0.72 + quarterlyBoost + gammaBoost, 0.85),
          barIntervalMinutes,
          proximity
        });
      }

      // Fade a push below range low (lower wick, close well above low)
      if (
        bar.low < rangeLow &&
        lowerWick > body * 1.2 &&
        bar.close > rangeLow &&
        bar.close < rangeHigh
      ) {
        const stop = bar.low - atr * 0.25;
        const target = rangeHigh - (rangeSize * 0.3);
        return buildSignal({
          context,
          side: "long",
          stop,
          target,
          confidence: Math.min(0.72 + quarterlyBoost + gammaBoost, 0.85),
          barIntervalMinutes,
          proximity
        });
      }
    }

    // --- VIX Wednesday / Roll window momentum ---
    // VIX settlement and roll-window periods create directional flow as vol funds
    // and CTAs reposition. Follow the session open direction if momentum is clean.
    // Cycle 14: VIX backwardation reduces momentum conviction (-0.10).
    if (proximity.isVixDay || (proximity.inRollWindow && proximity.daysToNearest <= 2)) {
      const openBar = sourceHistory[0];
      if (!openBar) return null;
      const sessionOpen = openBar.open;
      const midRange = (rangeHigh + rangeLow) / 2;

      // Strong momentum up off session open (price well above session mid, close > open)
      if (
        bar.close > sessionOpen &&
        bar.close > midRange + atr * 0.15 &&
        bar.close > bar.open &&
        body > atr * 0.15
      ) {
        const stop = Math.min(bar.open, bar.low) - atr * 0.2;
        const target = bar.close + atr * 1.5;
        return buildSignal({
          context,
          side: "long",
          stop,
          target,
          confidence: Math.max(0.52, 0.62 - vixStressPenalty),
          barIntervalMinutes,
          proximity
        });
      }

      // Strong momentum down
      if (
        bar.close < sessionOpen &&
        bar.close < midRange - atr * 0.15 &&
        bar.close < bar.open &&
        body > atr * 0.15
      ) {
        const stop = Math.max(bar.open, bar.high) + atr * 0.2;
        const target = bar.close - atr * 1.5;
        return buildSignal({
          context,
          side: "short",
          stop,
          target,
          confidence: Math.max(0.52, 0.62 - vixStressPenalty),
          barIntervalMinutes,
          proximity
        });
      }
    }

    return null;
  }
}
