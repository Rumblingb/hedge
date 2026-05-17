import type { LabConfig, Strategy, StrategyContext, StrategySignal } from "../domain.js";
import { IctDisplacementStrategy } from "./ictDisplacement.js";
import { IctDisplacement5mStrategy } from "./ictDisplacement5m.js";
import { IctNarrativeStrategy } from "./ictNarrative.js";
import { IctSweepReversionStrategy } from "./ictSweepReversion.js";
import { IctBreakoutStrategy } from "./ictBreakout.js";
import { LiquidityReversionStrategy } from "./liquidityReversion.js";
import { OpeningRangeReversalStrategy } from "./openingRangeReversal.js";
import { SessionMomentumStrategy } from "./sessionMomentum.js";
import { ExpiryFlowStrategy } from "./expiryFlow.js";
import { PairsTradingStrategy } from "./pairsTrading.js";
import { CrossSectionalMomentumStrategy } from "./crossSectionalMomentum.js";
import { VolatilityRegimeStrategy } from "./volatilityRegime.js";
import { Ret30MomentumStrategy } from "./ret30Momentum.js";
import { VwapReversionStrategy } from "./vwapReversion.js";
import { BollingerSqueezeStrategy } from "./bollingerSqueeze.js";
import { WqAlpha001, WqAlpha002, WqAlpha006, WqAlpha009, WqAlpha012, WqAlpha020, WqAlpha054, WqAlpha065, WqAlpha101 } from "./worldquantAlphas.js";
import { WqAlpha003, WqAlpha007, WqAlpha008, WqAlpha021, WqAlpha024, WqAlpha033, WqAlpha044, WqAlpha049, WqAlpha053, WqAlpha057, WqAlpha083 } from "./worldquantAlphas2.js";
import { DriftRegimeCSMStrategy } from "./driftRegimeCSM.js";
import { HmmPairsArbStrategy } from "./hmmPairsArb.js";
import { GammaStabilityStrategy } from "./gammaStability.js";
import { LlmMomentumGateStrategy } from "./llmMomentumGate.js";
import { TwoLevelUncertaintyStrategy } from "./twoLevelUncertainty.js";
import { LlmGaEvolutionaryStrategy } from "./llmGaEvolutionary.js";
import { DrawdownMomentumStrategy } from "./drawdownMomentum.js";
import { PushResponseAnomalyStrategy } from "./pushResponseAnomaly.js";
import { OptimalCostPairsStrategy } from "./optimalCostPairs.js";
import { NetworkMomentumStrategy } from "./networkMomentum.js";
import { StructuralFlowsStrategy } from "./structuralFlows.js";
import { CapitulationScoreStrategy } from "./capitulationScore.js";
import { EventSpikeFadeStrategy } from "./eventSpikeFade.js";
import { OpeningStopHuntStrategy } from "./openingStopHunt.js";
import { IntradayMomentumStrategy } from "./intradayMomentum.js";
import { KronosDirectionStrategy } from "./kronosDirection.js";
import { GapFadeRegimeStrategy } from "./gapFadeRegime.js";
import { ShortTermReversalStrategy } from "./shortTermReversal.js";
import { MonthlySeasonalityStrategy } from "./monthlySeasonality.js";
import { RegimeLockedMomentumStrategy } from "./regimeLockedMomentum.js";
import { RegimeOrbBreakoutStrategy } from "./regimeOrbBreakout.js";
import { Rsi2MeanReversionStrategy } from "./rsi2MeanReversion.js";
import { OptionsSellingFrameworkStrategy } from "./optionsSellingFramework.js";
import { PostNewsSettlementStrategy } from "./postNewsSettlement.js";
import { VolRiskPremiumStrategy } from "./volRiskPremium.js";
import { CotPositioningStrategy, VixTermStructureStrategy, CpiReactionStrategy, OpecFadeStrategy, EiaInventoryStrategy, GammaPinStrategy } from "./macroEvents.js";
import { WqAlpha009Strategy, WqAlpha001Strategy, WqAlpha012Strategy } from "./rustWqAlphas.js";
import { PropFvgScalpStrategy, PropLiqGrabStrategy, PropOrbScalpStrategy, PropVwapBounceStrategy, PropMomentumScalpStrategy } from "./propOptimized.js";
import { TickScalpStrategy, ZScoreMeanRevStrategy, OpenDriveFadeStrategy, TimeBasedExitStrategy, RangeBoundScalpStrategy } from "./propEdgeStrategies.js";
import { OrbBreakoutStrategy } from "./orbBreakout.js";
import { DonchianBreakoutStrategy } from "./donchianBreakout.js";
import { VolTargetedMomentumStrategy } from "./volTargetedMomentum.js";
import { VolScaledBreakoutMomentumStrategy } from "./volScaledBreakoutMomentum.js";
import { getRankingWeightSync } from "../engine/multiFactorRanking.js";

export function buildStrategyCatalog(): Record<string, Strategy> {
  return {
    "ict-displacement": new IctDisplacementStrategy(),
    "ict-displacement-5m": new IctDisplacement5mStrategy(),
    "ict-narrative": new IctNarrativeStrategy(),
    "ict-sweep-reversion": new IctSweepReversionStrategy(),
    "ict-breakout": new IctBreakoutStrategy(),
    "opening-range-reversal": new OpeningRangeReversalStrategy(),
    "session-momentum": new SessionMomentumStrategy(),
    "liquidity-reversion": new LiquidityReversionStrategy(),
    "expiry-flow": new ExpiryFlowStrategy(),
    "pairs-trading": new PairsTradingStrategy(),
    "cross-sectional-momentum": new CrossSectionalMomentumStrategy(),
    "volatility-regime": new VolatilityRegimeStrategy(),
    "ret-30-momentum": new Ret30MomentumStrategy(),
    "vwap-reversion": new VwapReversionStrategy(),
    "bollinger-squeeze": new BollingerSqueezeStrategy(),
    // WorldQuant 101 Alphas — Batch 1 (institutional alpha signals)
    "wq-alpha-001": new WqAlpha001(),
    "wq-alpha-002": new WqAlpha002(),
    "wq-alpha-006": new WqAlpha006(),
    "wq-alpha-009": new WqAlpha009(),
    "wq-alpha-012": new WqAlpha012(),
    "wq-alpha-020": new WqAlpha020(),
    "wq-alpha-054": new WqAlpha054(),
    "wq-alpha-065": new WqAlpha065(),
    "wq-alpha-101": new WqAlpha101(),
    // WorldQuant 101 Alphas — Batch 2
    "wq-alpha-003": new WqAlpha003(),
    "wq-alpha-007": new WqAlpha007(),
    "wq-alpha-008": new WqAlpha008(),
    "wq-alpha-021": new WqAlpha021(),
    "wq-alpha-024": new WqAlpha024(),
    "wq-alpha-033": new WqAlpha033(),
    "wq-alpha-044": new WqAlpha044(),
    "wq-alpha-049": new WqAlpha049(),
    "wq-alpha-053": new WqAlpha053(),
    "wq-alpha-057": new WqAlpha057(),
    "wq-alpha-083": new WqAlpha083(),
    "drift-regime-csm": new DriftRegimeCSMStrategy(),
    "hmm-pairs-arb": new HmmPairsArbStrategy(),
    "gamma-stability": new GammaStabilityStrategy(),
    "llm-momentum-gate": new LlmMomentumGateStrategy(),
    "two-level-uncertainty": new TwoLevelUncertaintyStrategy(),
    "llm-ga-evolutionary": new LlmGaEvolutionaryStrategy(),
    "drawdown-momentum": new DrawdownMomentumStrategy(),
    "push-response-anomaly": new PushResponseAnomalyStrategy(),
    "optimal-cost-pairs": new OptimalCostPairsStrategy(),
    "network-momentum": new NetworkMomentumStrategy(),
    "capitulation-score": new CapitulationScoreStrategy(),
    "structural-flows": new StructuralFlowsStrategy(),
    "event-spike-fade": new EventSpikeFadeStrategy(),
    "opening-stop-hunt": new OpeningStopHuntStrategy(),
    "intraday-momentum": new IntradayMomentumStrategy(),
    "kronos-direction": new KronosDirectionStrategy(),
    "donchian-breakout": new DonchianBreakoutStrategy(),
    "orb-breakout": new OrbBreakoutStrategy(),
    "regime-orb-breakout": new RegimeOrbBreakoutStrategy(),
    "gap-fade-regime": new GapFadeRegimeStrategy(),
    "short-term-reversal": new ShortTermReversalStrategy(),
    "monthly-seasonality": new MonthlySeasonalityStrategy(),
    "regime-locked-momentum": new RegimeLockedMomentumStrategy(),
    "rsi2-mean-reversion": new Rsi2MeanReversionStrategy(),
    "post-news-settlement": new PostNewsSettlementStrategy(),
    "options-selling-framework": new OptionsSellingFrameworkStrategy(),
    "vol-risk-premium": new VolRiskPremiumStrategy(),
    // Macro event-driven strategies (COT, VIX, CPI, OPEX, OPEC, EIA)
    "cot-positioning": new CotPositioningStrategy(),
    "vix-term-structure": new VixTermStructureStrategy(),
    "cpi-reaction": new CpiReactionStrategy(),
    "opec-fade": new OpecFadeStrategy(),
    "eia-inventory": new EiaInventoryStrategy(),
    "gamma-pin": new GammaPinStrategy(),
    // Rust WQ Alpha strategy ports. These remain research/demo candidates until
    // fresh walk-forward, OOS, and demo evidence promote them.
    "wq-alpha-009-rust": new WqAlpha009Strategy(),
    "wq-alpha-001-rust": new WqAlpha001Strategy(),
    "wq-alpha-012-rust": new WqAlpha012Strategy(),
    // Topstep prop-firm optimized scalps
    "prop-fvg-scalp": new PropFvgScalpStrategy(),
    "prop-liq-grab": new PropLiqGrabStrategy(),
    "prop-orb-scalp": new PropOrbScalpStrategy(),
    "prop-vwap-bounce": new PropVwapBounceStrategy(),
    "prop-momentum-scalp": new PropMomentumScalpStrategy(),
    "tick-scalp": new TickScalpStrategy(),
    "zscore-mean-rev": new ZScoreMeanRevStrategy(),
    "open-drive-fade": new OpenDriveFadeStrategy(),
    "time-based-exit": new TimeBasedExitStrategy(),
    "range-bound-scalp": new RangeBoundScalpStrategy(),
    "vol-targeted-momentum": new VolTargetedMomentumStrategy(),
    "vol-scaled-breakout-momentum": new VolScaledBreakoutMomentumStrategy(),
  };
}

export class WctcEnsembleStrategy implements Strategy {
  public readonly id = "wctc-ensemble";
  public readonly description = "Blends guarded momentum and sweep-reversion proxies.";

  public constructor(private readonly strategies: Strategy[]) {}

  public generateSignal(context: StrategyContext): StrategySignal | null {
    const candidates = this.strategies
      .map((strategy) => {
        const signal = strategy.generateSignal(context);
        if (!signal) return null;
        // Scale confidence by ranking weight [0.5, 2.0] from live feedback loop.
        const rankWeight = getRankingWeightSync(strategy.id);
        return { signal, scaledConfidence: signal.confidence * rankWeight };
      })
      .filter((entry): entry is NonNullable<typeof entry> => entry !== null)
      .sort((left, right) => right.scaledConfidence - left.scaledConfidence);

    const best = candidates[0];
    if (!best) {
      return null;
    }

    return {
      ...best.signal,
      strategyId: `${this.id}:${best.signal.strategyId}`
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
