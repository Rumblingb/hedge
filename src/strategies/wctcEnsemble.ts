import type { LabConfig, Strategy, StrategyContext, StrategySignal } from "../domain.js";
import { IctDisplacementStrategy } from "./ictDisplacement.js";
import { LiquidityReversionStrategy } from "./liquidityReversion.js";
import { SessionMomentumStrategy } from "./sessionMomentum.js";
import { OpeningRangeReversalStrategy } from "./openingRangeReversal.js";
import { OrbBreakoutStrategy } from "./orbBreakout.js";
import { DonchianBreakoutStrategy } from "./donchianBreakout.js";
import { WqTrendMomStrategy } from "./wqTrendMom.js";
import { DailyRangeBreakoutStrategy } from "./dailyRangeBreakout.js";

// ── Build catalog (all strategies as a record) ──

export function buildStrategyCatalog(): Record<string, Strategy> {
  return {
    "ict-displacement": new IctDisplacementStrategy(),
    "liquidity-reversion": new LiquidityReversionStrategy(),
    "session-momentum": new SessionMomentumStrategy(),
    "opening-range-reversal": new OpeningRangeReversalStrategy(),
    "orb-breakout": new OrbBreakoutStrategy(),
    "donchian-breakout": new DonchianBreakoutStrategy(),
    "wq-trend-mom": new WqTrendMomStrategy(),
    "daily-range-breakout": new DailyRangeBreakoutStrategy(),
  };
}

// ── Composite ensemble strategy (for walkforward/backtest compatibility) ──

export class WctcEnsembleStrategy implements Strategy {
  id = "wctc-ensemble";
  description = "WCTC multi-strategy ensemble — runs all loaded strategies and combines signals";

  generateSignal(context: StrategyContext): StrategySignal | null {
    const catalog = buildStrategyCatalog();
    let best: StrategySignal | null = null;
    let bestConfidence = 0;

    for (const strat of Object.values(catalog)) {
      try {
        const signal = strat.generateSignal(context);
        if (signal && signal.confidence > bestConfidence) {
          best = signal;
          bestConfidence = signal.confidence;
        }
      } catch {
        // Individual strategy failure shouldn't crash the ensemble
      }
    }
    return best;
  }
}

/**
 * Build the default ensemble as a single Strategy instance.
 * Used by walkforward, backtest, and CLI commands.
 */
export function buildDefaultEnsemble(_config?: Partial<LabConfig>): Strategy {
  return new WctcEnsembleStrategy();
}
