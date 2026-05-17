import type { LabConfig, Strategy, StrategyContext, StrategySignal } from "../domain.js";
import { IctDisplacementStrategy } from "./ictDisplacement.js";
import { LiquidityReversionStrategy } from "./liquidityReversion.js";
import { OpeningRangeReversalStrategy } from "./openingRangeReversal.js";
import { SessionMomentumStrategy } from "./sessionMomentum.js";
import { OrbBreakoutStrategy } from "./orbBreakout.js";
import { DonchianBreakoutStrategy } from "./donchianBreakout.js";
import { WqTrendMomStrategy } from "./wqTrendMom.js";
import { DailyRangeBreakoutStrategy } from "./dailyRangeBreakout.js";

export function buildStrategyCatalog(): Record<string, Strategy> {
  return {
    "ict-displacement": new IctDisplacementStrategy(),
    "opening-range-reversal": new OpeningRangeReversalStrategy(),
    "session-momentum": new SessionMomentumStrategy(),
    "liquidity-reversion": new LiquidityReversionStrategy(),
    "orb-breakout": new OrbBreakoutStrategy(),
    "donchian-breakout": new DonchianBreakoutStrategy(),
    "wq-trend-mom": new WqTrendMomStrategy(),
    "daily-range-breakout": new DailyRangeBreakoutStrategy(),
  };
}
