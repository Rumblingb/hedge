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

export class WctcEnsembleStrategy implements Strategy {
  public readonly id = "wctc-ensemble";
  public readonly description = "Blends guarded momentum and sweep-reversion proxies.";

  public constructor(private readonly strategies: Strategy[]) {}

  public generateSignal(context: StrategyContext): StrategySignal | null {
    const candidates = this.strategies
      .map((strategy) => strategy.generateSignal(context))
      .filter((signal): signal is StrategySignal => signal !== null)
      .sort((left, right) => right.confidence - left.confidence);

    const best = candidates[0];
    if (!best) {
      return null;
    }

    return {
      ...best,
      strategyId: `${this.id}:${best.strategyId}`
    };
  }
}

export function buildDefaultEnsemble(config: LabConfig): Strategy {
  const catalog = buildStrategyCatalog();

  const enabled = config.enabledStrategies
    .map((id) => catalog[id])
    .filter((strategy): strategy is Strategy => strategy !== undefined);

  return new WctcEnsembleStrategy(enabled);
}
