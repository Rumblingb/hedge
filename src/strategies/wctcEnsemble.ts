import type { LabConfig, Strategy, StrategyContext, StrategySignal } from "../domain.js";
import { IctDisplacementStrategy } from "./ictDisplacement.js";
import { LiquidityReversionStrategy } from "./liquidityReversion.js";
import { SessionMomentumStrategy } from "./sessionMomentum.js";
import { OpeningRangeReversalStrategy } from "./openingRangeReversal.js";
import { OrbBreakoutStrategy } from "./orbBreakout.js";
import { DonchianBreakoutStrategy } from "./donchianBreakout.js";
import { WqTrendMomStrategy } from "./wqTrendMom.js";
import { DailyRangeBreakoutStrategy } from "./dailyRangeBreakout.js";
import { BollingerSqueezeStrategy } from "./bollingerSqueeze.js";
import { CapitulationScoreStrategy } from "./capitulationScore.js";
import { CrossSectionalMomentumStrategy } from "./crossSectionalMomentum.js";
import { DrawdownMomentumStrategy } from "./drawdownMomentum.js";
import { DriftRegimeCSMStrategy } from "./driftRegimeCSM.js";
import { EventSpikeFadeStrategy } from "./eventSpikeFade.js";
import { ExpiryFlowStrategy } from "./expiryFlow.js";
import { GammaStabilityStrategy } from "./gammaStability.js";
import { HmmPairsArbStrategy } from "./hmmPairsArb.js";
import { IctBreakoutStrategy } from "./ictBreakout.js";
import { IctNarrativeStrategy } from "./ictNarrative.js";
import { IctSweepReversionStrategy } from "./ictSweepReversion.js";
import { KronosDirectionStrategy } from "./kronosDirection.js";
import { LlmGaEvolutionaryStrategy } from "./llmGaEvolutionary.js";
import { LlmMomentumGateStrategy } from "./llmMomentumGate.js";
import { NetworkMomentumStrategy } from "./networkMomentum.js";
import { OpeningStopHuntStrategy } from "./openingStopHunt.js";
import { OptimalCostPairsStrategy } from "./optimalCostPairs.js";
import { OrbBreakout60m } from "./orbBreakout60m.js";
import { PairsTradingStrategy } from "./pairsTrading.js";
import { PushResponseAnomalyStrategy } from "./pushResponseAnomaly.js";
import { RegimeOrbBreakoutStrategy } from "./regimeOrbBreakout.js";
import { WqAlpha001Strategy, WqAlpha009Strategy, WqAlpha012Strategy } from "./rustWqAlphas.js";
import { TwoLevelUncertaintyStrategy } from "./twoLevelUncertainty.js";
import { VolRiskPremiumStrategy } from "./volRiskPremium.js";
import { VolatilityRegimeStrategy } from "./volatilityRegime.js";
import { VwapReversionStrategy } from "./vwapReversion.js";
import { WqAlpha001, WqAlpha002, WqAlpha006, WqAlpha009, WqAlpha012, WqAlpha020, WqAlpha054, WqAlpha065, WqAlpha101 } from "./worldquantAlphas.js";
import { WqAlpha003, WqAlpha007, WqAlpha008, WqAlpha021, WqAlpha024, WqAlpha033, WqAlpha044, WqAlpha049, WqAlpha053, WqAlpha057, WqAlpha083 } from "./worldquantAlphas2.js";
import { WqTrendMom60m } from "./wqTrendMom60m.js";
import { WqVolRegime60m } from "./wqVolRegime60m.js";
import { SeasonalityStrategy } from "./seasonality.js";
import { GapFadeStrategy } from "./gapFade.js";
import { PowerHourStrategy } from "./powerHour.js";
import { SupplyDemandStrategy } from "./supplyDemand.js";
import { RsiDivergenceStrategy } from "./rsiDivergence.js";
import { ScalpingStrategy } from "./scalping.js";
import { CarryTradeStrategy } from "./carryTrade.js";
import { MarketProfileStrategy } from "./marketProfile.js";
import { OvernightHoldStrategy } from "./overnightHold.js";
import { DarkPoolPrintStrategy } from "./flowMacro.js";
import { RegimeLockedMomentumStrategy } from "./regimeLockedMomentum.js";
import { StructuralFlowsStrategy } from "./structuralFlows.js";
import { ShortTermReversalStrategy } from "./shortTermReversal.js";
import { Ret30MomentumStrategy } from "./ret30Momentum.js";
import { Rsi2MeanReversionStrategy } from "./rsi2MeanReversion.js";
import { OptionsSellingFrameworkStrategy } from "./optionsSellingFramework.js";

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
    "bollinger-squeeze": new BollingerSqueezeStrategy(),
    "capitulation-score": new CapitulationScoreStrategy(),
    "cross-sectional-momentum": new CrossSectionalMomentumStrategy(),
    "drawdown-momentum": new DrawdownMomentumStrategy(),
    "drift-regime-csm": new DriftRegimeCSMStrategy(),
    "event-spike-fade": new EventSpikeFadeStrategy(),
    "expiry-flow": new ExpiryFlowStrategy(),
    "gamma-stability": new GammaStabilityStrategy(),
    "hmm-pairs-arb": new HmmPairsArbStrategy(),
    "ict-breakout": new IctBreakoutStrategy(),
    "ict-narrative": new IctNarrativeStrategy(),
    "ict-sweep-reversion": new IctSweepReversionStrategy(),
    "kronos-direction": new KronosDirectionStrategy(),
    "llm-ga-evolutionary": new LlmGaEvolutionaryStrategy(),
    "llm-momentum-gate": new LlmMomentumGateStrategy(),
    "network-momentum": new NetworkMomentumStrategy(),
    "opening-stop-hunt": new OpeningStopHuntStrategy(),
    "optimal-cost-pairs": new OptimalCostPairsStrategy(),
    "orb-breakout-60m": new OrbBreakout60m(),
    "pairs-trading": new PairsTradingStrategy(),
    "push-response-anomaly": new PushResponseAnomalyStrategy(),
    "regime-orb-breakout": new RegimeOrbBreakoutStrategy(),
    "wq-alpha-009-rust": new WqAlpha009Strategy(),
    "wq-alpha-001-rust": new WqAlpha001Strategy(),
    "wq-alpha-012-rust": new WqAlpha012Strategy(),
    "two-level-uncertainty": new TwoLevelUncertaintyStrategy(),
    "vol-risk-premium": new VolRiskPremiumStrategy(),
    "volatility-regime": new VolatilityRegimeStrategy(),
    "vwap-reversion": new VwapReversionStrategy(),
    "wq-alpha-001": new WqAlpha001(),
    "wq-alpha-002": new WqAlpha002(),
    "wq-alpha-006": new WqAlpha006(),
    "wq-alpha-009": new WqAlpha009(),
    "wq-alpha-012": new WqAlpha012(),
    "wq-alpha-020": new WqAlpha020(),
    "wq-alpha-054": new WqAlpha054(),
    "wq-alpha-065": new WqAlpha065(),
    "wq-alpha-101": new WqAlpha101(),
    "wq-alpha-003": new WqAlpha003(),
    "wq-alpha-007": new WqAlpha007(),
    "wq-alpha-008": new WqAlpha008(),
    "wq-alpha-021": new WqAlpha021(),
    "wq-alpha-033": new WqAlpha033(),
    "wq-alpha-049": new WqAlpha049(),
    "wq-alpha-053": new WqAlpha053(),
    "wq-alpha-083": new WqAlpha083(),
    "wq-alpha-024": new WqAlpha024(),
    "wq-alpha-044": new WqAlpha044(),
    "wq-alpha-057": new WqAlpha057(),
    "wq-trend-mom-60m": new WqTrendMom60m(),
    "wq-vol-regime-60m": new WqVolRegime60m(),
    "seasonality": new SeasonalityStrategy(),
    "gap-fade": new GapFadeStrategy(),
    "power-hour": new PowerHourStrategy(),
    "supply-demand": new SupplyDemandStrategy(),
    "rsi-divergence": new RsiDivergenceStrategy(),
    "scalping": new ScalpingStrategy(),
    "carry-trade": new CarryTradeStrategy(),
    "market-profile": new MarketProfileStrategy(),
    "overnight-hold": new OvernightHoldStrategy(),
    "dark-pool-print": new DarkPoolPrintStrategy(),
    "regime-locked-momentum": new RegimeLockedMomentumStrategy(),
    "structural-flows": new StructuralFlowsStrategy(),
    "short-term-reversal": new ShortTermReversalStrategy(),
    "ret-30-momentum": new Ret30MomentumStrategy(),
    "rsi-2-mean-reversion": new Rsi2MeanReversionStrategy(),
    "options-selling-framework": new OptionsSellingFrameworkStrategy(),
  };
}

// ── Composite ensemble strategy (for walkforward/backtest compatibility) ──

export class WctcEnsembleStrategy implements Strategy {
  id = "wctc-ensemble";
  description = "WCTC multi-strategy ensemble — runs all loaded strategies and combines signals";

  public constructor(private readonly enabledStrategyIds?: string[]) {}

  generateSignal(context: StrategyContext): StrategySignal | null {
    const catalog = buildStrategyCatalog();
    const strategies = this.enabledStrategyIds && this.enabledStrategyIds.length > 0
      ? this.enabledStrategyIds.map((id) => catalog[id]).filter((strategy): strategy is Strategy => Boolean(strategy))
      : Object.values(catalog);
    let best: StrategySignal | null = null;
    let bestConfidence = 0;

    for (const strat of strategies) {
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
export function buildDefaultEnsemble(config?: Partial<LabConfig>): Strategy {
  return new WctcEnsembleStrategy(config?.enabledStrategies);
}
