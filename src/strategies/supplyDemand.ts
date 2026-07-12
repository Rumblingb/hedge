import type { Strategy, StrategyContext, StrategySignal, TradeSide } from "../domain.js";
import { calculateRr } from "../risk/guardrails.js";
import { averageTrueRange } from "../utils/indicators.js";
import { getMarketSessionWindow } from "../utils/sessions.js";
import { inferBarIntervalMinutes, minutesFromCtTime } from "../utils/time.js";

/**
 * Supply/Demand Zone Strategy
 * Identifies price zones where supply/demand imbalance exists.
 * Based on Sam Seiden / institutional order flow concepts.
 * Long at demand zones (support), short at supply zones (resistance).
 */

interface Zone {
  level: number;
  strength: number; // 0-1 based on pivot quality
  type: "supply" | "demand";
}

function findZones(bars: { high: number; low: number; close: number }[], lookback: number): Zone[] {
  const zones: Zone[] = [];
  if (bars.length < 3) return zones;
  for (let i = 1; i < bars.length - 1; i++) {
    const range = bars[i].high - bars[i].low;
    if (range < 0.0001) continue;
    // Pivot high (supply zone)
    if (bars[i].high > bars[i - 1].high && bars[i].high >= bars[i + 1].high) {
      const strength = Math.min(1, (bars[i].high - Math.max(bars[i - 1].high, bars[i + 1].high)) / range);
      zones.push({ level: bars[i].high, strength, type: "supply" });
    }
    // Pivot low (demand zone)
    if (bars[i].low < bars[i - 1].low && bars[i].low <= bars[i + 1].low) {
      const strength = Math.min(1, (Math.min(bars[i - 1].low, bars[i + 1].low) - bars[i].low) / range);
      zones.push({ level: bars[i].low, strength, type: "demand" });
    }
  }
  return zones;
}

function buildSignal(args: {
  context: StrategyContext; side: TradeSide; stop: number; target: number;
  confidence: number; zoneLevel: number; zoneType: string;
}): StrategySignal | null {
  const { context, side, stop, target, confidence, zoneLevel, zoneType } = args;
  const entry = context.bar.close;
  const rr = calculateRr(entry, stop, target, side);
  if (rr <= 0) return null;
  return {
    symbol: context.symbol, strategyId: "supply-demand", side, entry, stop, target, rr,
    confidence, contracts: 1, maxHoldMinutes: 25,
    meta: { pattern: `${zoneType}-zone`, zoneLevel: Number(zoneLevel.toFixed(4)) },
  };
}

export class SupplyDemandStrategy implements Strategy {
  public readonly id = "supply-demand";
  public readonly description = "Trades institutional supply/demand zones: buy at demand, sell at supply. Pivot-based zone detection.";

  public generateSignal(context: StrategyContext): StrategySignal | null {
    const sourceHistory = context.sessionHistory.length >= 10 ? context.sessionHistory : context.history;
    const lookback = Math.min(50, sourceHistory.length);
    if (lookback < 10) return null;

    const recent = sourceHistory.slice(-lookback);
    const atr = averageTrueRange(recent, 14);
    if (atr <= 0) return null;

    const zones = findZones(recent, lookback);
    if (zones.length === 0) return null;

    const currentPrice = context.bar.close;
    const zoneBuffer = atr * 0.3; // Width of the zone

    // Find nearest demand zone below price
    const demandZones = zones
      .filter((z) => z.type === "demand" && z.level < currentPrice && z.level > currentPrice - atr * 2)
      .sort((a, b) => b.level - a.level);

    // Find nearest supply zone above price
    const supplyZones = zones
      .filter((z) => z.type === "supply" && z.level > currentPrice && z.level < currentPrice + atr * 2)
      .sort((a, b) => a.level - b.level);

    // Buy at demand zone if price approaching
    if (demandZones.length > 0 && currentPrice <= demandZones[0].level + zoneBuffer) {
      const zone = demandZones[0];
      const stop = zone.level - atr * 0.5;
      const target = currentPrice + atr * 2;
      if (stop >= currentPrice) return null;
      return buildSignal({ context, side: "long", stop, target,
        confidence: Math.min(0.68, zone.strength * 0.8), zoneLevel: zone.level, zoneType: "demand" });
    }

    // Sell at supply zone if price approaching
    if (supplyZones.length > 0 && currentPrice >= supplyZones[0].level - zoneBuffer) {
      const zone = supplyZones[0];
      const stop = zone.level + atr * 0.5;
      const target = currentPrice - atr * 2;
      if (stop <= currentPrice) return null;
      return buildSignal({ context, side: "short", stop, target,
        confidence: Math.min(0.68, zone.strength * 0.8), zoneLevel: zone.level, zoneType: "supply" });
    }

    return null;
  }
}
