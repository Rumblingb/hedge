import type { Bar, LabConfig, TradeSide } from "../domain.js";
import { averageTrueRange } from "../utils/indicators.js";
import { getMarketCategory } from "../utils/markets.js";
import { chicagoDateKey, inferBarIntervalMinutes } from "../utils/time.js";

export type RegimeLabel =
  | "trend-up"
  | "trend-down"
  | "opening-reversal-up"
  | "opening-reversal-down"
  | "displacement-up"
  | "displacement-down"
  | "range-chop"
  | "insufficient-data";

export interface SymbolRegimeAssessment {
  symbol: string;
  marketFamily: string;
  label: RegimeLabel;
  confidence: number;
  directionalBias: TradeSide | "flat";
  preferredStrategies: string[];
  note: string;
  features: {
    sessionBars: number;
    sessionRange: number;
    atr: number;
    netMove: number;
    closeLocation: number;
    openingRangeWidth: number;
  };
}

function clamp01(value: number): number {
  return Math.max(0, Math.min(1, value));
}

function latestSessionBarsBySymbol(bars: Bar[]): Map<string, Bar[]> {
  const latestDayBySymbol = new Map<string, string>();

  for (const bar of bars) {
    const current = latestDayBySymbol.get(bar.symbol);
    const dayKey = chicagoDateKey(bar.ts);
    if (!current || dayKey > current) {
      latestDayBySymbol.set(bar.symbol, dayKey);
    }
  }

  const grouped = new Map<string, Bar[]>();
  for (const bar of bars) {
    const latestDay = latestDayBySymbol.get(bar.symbol);
    if (!latestDay || chicagoDateKey(bar.ts) !== latestDay) {
      continue;
    }

    const current = grouped.get(bar.symbol) ?? [];
    current.push(bar);
    grouped.set(bar.symbol, current);
  }

  return grouped;
}

function averageBodySize(history: Bar[], period: number): number {
  const tail = history.slice(-period);
  if (tail.length === 0) {
    return 0;
  }

  return tail.reduce((sum, bar) => sum + Math.abs(bar.close - bar.open), 0) / tail.length;
}

function classifySession(args: {
  symbol: string;
  sessionBars: Bar[];
  config: LabConfig;
}): SymbolRegimeAssessment {
  const { symbol, sessionBars, config } = args;
  const marketFamily = getMarketCategory(symbol);

  if (sessionBars.length < 8) {
    return {
      symbol,
      marketFamily,
      label: "insufficient-data",
      confidence: 0,
      directionalBias: "flat",
      preferredStrategies: [],
      note: "Not enough latest-session bars to classify the regime safely.",
      features: {
        sessionBars: sessionBars.length,
        sessionRange: 0,
        atr: 0,
        netMove: 0,
        closeLocation: 0.5,
        openingRangeWidth: 0
      }
    };
  }

  const firstBar = sessionBars[0]!;
  const latestBar = sessionBars[sessionBars.length - 1]!;
  const sessionHigh = Math.max(...sessionBars.map((bar) => bar.high));
  const sessionLow = Math.min(...sessionBars.map((bar) => bar.low));
  const sessionRange = Math.max(0.0001, sessionHigh - sessionLow);
  const closeLocation = clamp01((latestBar.close - sessionLow) / sessionRange);
  const netMove = latestBar.close - firstBar.open;
  const atr = averageTrueRange(sessionBars, Math.min(14, sessionBars.length));
  const intervalMinutes = inferBarIntervalMinutes(sessionBars[sessionBars.length - 2]?.ts, latestBar.ts) || 5;
  const openingBarCount = Math.max(3, Math.min(sessionBars.length, Math.round(30 / Math.max(1, intervalMinutes))));
  const openingBars = sessionBars.slice(0, openingBarCount);
  const openingHigh = Math.max(...openingBars.map((bar) => bar.high));
  const openingLow = Math.min(...openingBars.map((bar) => bar.low));
  const openingRangeWidth = Math.max(0.0001, openingHigh - openingLow);
  const prevTwoBack = sessionBars[sessionBars.length - 3];
  const previousBar = sessionBars[sessionBars.length - 2];
  const avgBody = averageBodySize(sessionBars, Math.min(8, sessionBars.length));
  const latestBody = Math.abs(latestBar.close - latestBar.open);
  const displacementThreshold = Math.max(0.0001, atr * 0.55, avgBody * 1.35);

  const bullishDisplacement = Boolean(
    prevTwoBack &&
    previousBar &&
    latestBar.close > latestBar.open &&
    latestBody >= displacementThreshold &&
    latestBar.low > prevTwoBack.high &&
    latestBar.close > previousBar.high
  );

  if (bullishDisplacement) {
    return {
      symbol,
      marketFamily,
      label: "displacement-up",
      confidence: clamp01(0.55 + ((latestBody / Math.max(displacementThreshold, 0.0001)) * 0.1)),
      directionalBias: "long",
      preferredStrategies: ["ict-displacement", "session-momentum"],
      note: "Latest session shows bullish displacement through prior structure with an imbalance left behind.",
      features: {
        sessionBars: sessionBars.length,
        sessionRange,
        atr: Number(atr.toFixed(4)),
        netMove: Number(netMove.toFixed(4)),
        closeLocation: Number(closeLocation.toFixed(4)),
        openingRangeWidth: Number(openingRangeWidth.toFixed(4))
      }
    };
  }

  const bearishDisplacement = Boolean(
    prevTwoBack &&
    previousBar &&
    latestBar.close < latestBar.open &&
    latestBody >= displacementThreshold &&
    latestBar.high < prevTwoBack.low &&
    latestBar.close < previousBar.low
  );

  if (bearishDisplacement) {
    return {
      symbol,
      marketFamily,
      label: "displacement-down",
      confidence: clamp01(0.55 + ((latestBody / Math.max(displacementThreshold, 0.0001)) * 0.1)),
      directionalBias: "short",
      preferredStrategies: ["ict-displacement", "session-momentum"],
      note: "Latest session shows bearish displacement through prior structure with an imbalance left behind.",
      features: {
        sessionBars: sessionBars.length,
        sessionRange,
        atr: Number(atr.toFixed(4)),
        netMove: Number(netMove.toFixed(4)),
        closeLocation: Number(closeLocation.toFixed(4)),
        openingRangeWidth: Number(openingRangeWidth.toFixed(4))
      }
    };
  }

  const openingReversalUp =
    sessionLow < openingLow &&
    latestBar.close > openingHigh &&
    closeLocation > 0.68;

  if (openingReversalUp) {
    return {
      symbol,
      marketFamily,
      label: "opening-reversal-up",
      confidence: clamp01(0.52 + ((closeLocation - 0.68) * 0.8)),
      directionalBias: "long",
      preferredStrategies: ["opening-range-reversal", "ict-displacement"],
      note: "The session swept below the opening range and then reclaimed above it, favoring an opening reversal read.",
      features: {
        sessionBars: sessionBars.length,
        sessionRange,
        atr: Number(atr.toFixed(4)),
        netMove: Number(netMove.toFixed(4)),
        closeLocation: Number(closeLocation.toFixed(4)),
        openingRangeWidth: Number(openingRangeWidth.toFixed(4))
      }
    };
  }

  const openingReversalDown =
    sessionHigh > openingHigh &&
    latestBar.close < openingLow &&
    closeLocation < 0.32;

  if (openingReversalDown) {
    return {
      symbol,
      marketFamily,
      label: "opening-reversal-down",
      confidence: clamp01(0.52 + ((0.32 - closeLocation) * 0.8)),
      directionalBias: "short",
      preferredStrategies: ["opening-range-reversal", "ict-displacement"],
      note: "The session swept above the opening range and then failed back below it, favoring an opening reversal read.",
      features: {
        sessionBars: sessionBars.length,
        sessionRange,
        atr: Number(atr.toFixed(4)),
        netMove: Number(netMove.toFixed(4)),
        closeLocation: Number(closeLocation.toFixed(4)),
        openingRangeWidth: Number(openingRangeWidth.toFixed(4))
      }
    };
  }

  const trendUp =
    netMove > Math.max(atr * 0.7, openingRangeWidth * 0.35) &&
    closeLocation > 0.7;

  if (trendUp) {
    return {
      symbol,
      marketFamily,
      label: "trend-up",
      confidence: clamp01(0.5 + ((closeLocation - 0.7) * 0.8)),
      directionalBias: "long",
      preferredStrategies: ["session-momentum", "ict-displacement"],
      note: "Session is holding near highs with enough directional expansion to treat it as a trend-up day.",
      features: {
        sessionBars: sessionBars.length,
        sessionRange,
        atr: Number(atr.toFixed(4)),
        netMove: Number(netMove.toFixed(4)),
        closeLocation: Number(closeLocation.toFixed(4)),
        openingRangeWidth: Number(openingRangeWidth.toFixed(4))
      }
    };
  }

  const trendDown =
    netMove < -Math.max(atr * 0.7, openingRangeWidth * 0.35) &&
    closeLocation < 0.3;

  if (trendDown) {
    return {
      symbol,
      marketFamily,
      label: "trend-down",
      confidence: clamp01(0.5 + ((0.3 - closeLocation) * 0.8)),
      directionalBias: "short",
      preferredStrategies: ["session-momentum", "ict-displacement"],
      note: "Session is holding near lows with enough directional expansion to treat it as a trend-down day.",
      features: {
        sessionBars: sessionBars.length,
        sessionRange,
        atr: Number(atr.toFixed(4)),
        netMove: Number(netMove.toFixed(4)),
        closeLocation: Number(closeLocation.toFixed(4)),
        openingRangeWidth: Number(openingRangeWidth.toFixed(4))
      }
    };
  }

  return {
    symbol,
    marketFamily,
    label: "range-chop",
    confidence: clamp01(0.45 + (0.15 - Math.abs(closeLocation - 0.5))),
    directionalBias: "flat",
    preferredStrategies: ["liquidity-reversion", "opening-range-reversal"],
    note: "The latest session is balanced and mean-reverting rather than directional.",
    features: {
      sessionBars: sessionBars.length,
      sessionRange,
      atr: Number(atr.toFixed(4)),
      netMove: Number(netMove.toFixed(4)),
      closeLocation: Number(closeLocation.toFixed(4)),
      openingRangeWidth: Number(openingRangeWidth.toFixed(4))
    }
  };
}

export function classifyLatestSessionRegimes(args: {
  bars: Bar[];
  config: LabConfig;
  allowedSymbols: string[];
}): SymbolRegimeAssessment[] {
  const grouped = latestSessionBarsBySymbol(args.bars);

  return args.allowedSymbols
    .map((symbol) => {
      const sessionBars = grouped.get(symbol) ?? [];
      return classifySession({
        symbol,
        sessionBars,
        config: args.config
      });
    })
    .sort((left, right) => right.confidence - left.confidence);
}
