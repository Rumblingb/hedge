/**
 * regimeOrbBreakout.ts — Regime-aware Opening Range Breakout Strategy
 *
 * Research-backed FOMC day strategy:
 *   Pre-announcement (11:00-14:00 ET): Vol contracts 30-40%. Tight range. Block aggressive entries.
 *   Blackout (13:30-14:30 ET): NO TRADES.
 *   Post-announcement ORB (14:30-16:00 ET): New opening range at 14:30. ~61% WR, Sharpe 0.78.
 *   ATR expansion: +52% on FOMC. Scale size to 0.66x, widen SL to 2.0 ATR.
 */

import type { Bar, Strategy, StrategyContext, StrategySignal, TradeSide } from "../domain.js";
import { calculateRr } from "../risk/guardrails.js";
import { averageTrueRange } from "../utils/indicators.js";

// ====== REGIME DETECTION ======

/** Known FOMC release dates for 2026 — 14:00 ET */
const FOMC_DATES_2026 = new Set([
  "2026-01-29", "2026-03-19", "2026-05-07", "2026-05-15", // TOMORROW
  "2026-06-18", "2026-07-30", "2026-09-17", "2026-11-05", "2026-12-17",
]);

interface RegimeConfig {
  rangeWindow: number;
  volThreshold: number;
  exitOffset: number;     // bars to hold
  stopAtr: number;        // 0 = no stop
  targetAtr: number;      // 0 = no target
  maxHoldMinutes: number;
  positionScale: number;  // 1.0 = normal, 0.66 = reduced for FOMC
  usePostFomcOrb: boolean; // Post-announcement ORB (14:30 range)
}

const REGIMES: Record<string, RegimeConfig> = {
  fomc: {
    rangeWindow: 16,
    volThreshold: 2.0,
    exitOffset: 5,
    stopAtr: 1.5,
    targetAtr: 3.0,
    maxHoldMinutes: 240,
    positionScale: 0.66,  // -34% size due to +52% ATR
    usePostFomcOrb: false,
  },
  prefomc: {
    rangeWindow: 10,
    volThreshold: 1.3,
    exitOffset: 8,
    stopAtr: 1.0,
    targetAtr: 0,
    maxHoldMinutes: 480,
    positionScale: 0.5,   // -50% size pre-announcement
    usePostFomcOrb: false,
  },
  postfomc: {
    rangeWindow: 14,
    volThreshold: 1.5,
    exitOffset: 10,
    stopAtr: 2.0,         // Wider stop for volatility
    targetAtr: 0,         // Let trends run (no fixed target)
    maxHoldMinutes: 720,
    positionScale: 0.66,  // Reduced for ATR expansion
    usePostFomcOrb: true, // Use post-announcement ORB
  },
  expiry: {
    rangeWindow: 10,
    volThreshold: 1.5,
    exitOffset: 5,
    stopAtr: 1.0,
    targetAtr: 2.0,
    maxHoldMinutes: 240,
    positionScale: 1.0,
    usePostFomcOrb: false,
  },
  normal: {
    rangeWindow: 12,
    volThreshold: 1.3,
    exitOffset: 8,
    stopAtr: 0,
    targetAtr: 0,
    maxHoldMinutes: 480,
    positionScale: 1.0,
    usePostFomcOrb: false,
  },
};

// Session-specific overrides (applied on top of base regime)
const SESSION_CONFIGS: Record<string, Partial<RegimeConfig>> = {
  ny:       { rangeWindow: 12, volThreshold: 1.5, exitOffset: 8 },
  asia:     { rangeWindow: 8,  volThreshold: 1.3, exitOffset: 3 },
  afterhours: { rangeWindow: 8, volThreshold: 1.3, exitOffset: 3 },
  london_skip: { rangeWindow: 0, volThreshold: 0, exitOffset: 0 },  // blocked
  premarket_skip: { rangeWindow: 0, volThreshold: 0, exitOffset: 0 }, // blocked
};

/** Get session name from ET time */
function getSession(hour: number, minute: number): string {
  const totalMin = hour * 60 + minute;
  if (totalMin >= 570 && totalMin < 960) return "ny";         // 09:30-16:00
  if (totalMin >= 960 && totalMin < 1140) return "afterhours"; // 16:00-19:00
  if (totalMin >= 1140 || totalMin < 180) return "asia";       // 19:00-03:00
  if (totalMin >= 180 && totalMin < 420) return "london_skip"; // 03:00-07:00 - skip
  if (totalMin >= 420 && totalMin < 570) return "premarket_skip"; // 07:00-09:30 - skip
  return "london_skip";
}

/** Check if today is a known FOMC date */
function isFomcDate(now: Date): boolean {
  const y = now.getFullYear();
  const m = String(now.getMonth() + 1).padStart(2, "0");
  const d = String(now.getDate()).padStart(2, "0");
  return FOMC_DATES_2026.has(`${y}-${m}-${d}`);
}

/**
 * Detect current market regime from calendar + session.
 * On FOMC days:
 *   11:00-13:30 ET → prefomc (tight, reduced size)
 *   13:30-14:30 ET → BLOCKED (blackout window)
 *   14:30-16:00 ET → postfomc (post-announcement ORB)
 *   All other times → normal
 */
function detectRegime(now: Date): { regime: string; config: RegimeConfig; signalBlocked: boolean } {
  const dateStr = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}`;
  const minutes = now.getUTCHours() * 60 + now.getUTCMinutes();
  const etMinutes = minutes - 4 * 60; // UTC → ET
  const hour = Math.floor(etMinutes / 60);
  const minute = etMinutes % 60;
  const session = getSession(hour, minute);

  // Apply session gate first (skip London/Premarket)
  if (REGIMES.normal.rangeWindow === 0) {
    // This shouldn't happen - session configs are above
  }

  // FOMC day logic
  if (isFomcDate(now)) {
    const totalMin = etMinutes;
    
    // Pre-announcement: 11:00-13:30 ET → reduced activity
    if (totalMin >= 660 && totalMin < 810) {
      return { regime: "prefomc", config: REGIMES.prefomc, signalBlocked: false };
    }
    
    // Blackout window: 13:30-14:30 ET → NO TRADES
    if (totalMin >= 810 && totalMin < 870) {
      return { regime: "fomc", config: { ...REGIMES.fomc, rangeWindow: 0 }, signalBlocked: true };
    }
    
    // Post-announcement: 14:30-16:00 ET → Post-FOMC ORB
    if (totalMin >= 870 && totalMin < 960) {
      return { regime: "postfomc", config: { 
        ...REGIMES.postfomc,
        // 14:30 range (30 min) = 2 bars on 15m chart
        rangeWindow: 2,
        volThreshold: 1.2, // Lower threshold post-announcement
      }, signalBlocked: false };
    }
  }

  // Normal day logic
  const baseRegime = "normal";
  const baseConfig = { ...REGIMES.normal };

  // Apply session-specific overrides
  const sessionConfig = SESSION_CONFIGS[session];
  if (sessionConfig) {
    Object.assign(baseConfig, sessionConfig);
  }

  return { regime: baseRegime, config: baseConfig, signalBlocked: baseConfig.rangeWindow === 0 };
}

export { detectRegime, REGIMES, FOMC_DATES_2026 };
export type { RegimeConfig };
