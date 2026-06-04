/**
 * strategyFusion.ts — 200iq Strategy Fusion Engine
 * 
 * NOT a naive ensemble. Regime-gated intelligent dispatch:
 * 1. Classify current market state (regime, vol, session phase)
 * 2. Score each strategy's suitability for the regime
 * 3. Pick the best strategy, deconflicting correlated entries
 * 4. Override/boost signals when conditions are ideal
 */

import type { Bar, StrategyContext, StrategySignal } from "../domain.js";
import { buildStrategyCatalog } from "../strategies/wctcEnsemble.js";

// ── Market Regimes ──

export type MarketRegime =
  | "trending-bull"       // Strong uptrend, momentum works
  | "trending-bear"       // Strong downtrend, momentum works
  | "ranging"             // Range-bound, mean reversion works
  | "breakout"            // Breaking out of range, ORB works
  | "volatile"            // High vol, nothing works — don't trade
  | "quiet"               // Low vol, scalping/reversion works
  | "reversal"            // Trend exhaustion, reversal patterns
  | "news"                // News-driven, high uncertainty

export interface RegimeAnalysis {
  regime: MarketRegime;
  confidence: number;       // 0-1
  volatility: "low" | "normal" | "high" | "extreme";
  session: "asia" | "london" | "ny-open" | "ny-mid" | "ny-close";
  atrPercentile: number;    // 0-1: where current ATR sits in 20-day range
  trendStrength: number;    // 0-1: ADX-like measure
  rangeBound: boolean;      // Is price range-bound?
  nqEsDivergence: boolean;  // Are NQ and ES diverging?
}

export interface FusionDecision {
  regime: RegimeAnalysis;
  selectedStrategy: string | null;
  signal: StrategySignal | null;
  rejectedStrategies: string[];
  reasons: string[];
  safetyLock: boolean;      // true = no trade recommended
}

// ── Strategy Regime Suitability Matrix ──
// Which strategies perform best in which regimes

const STRATEGY_REGIME_SCORES: Record<string, Partial<Record<MarketRegime, number>>> = {
  "ict-displacement": {
    "trending-bull": 0.85,
    "trending-bear": 0.85,
    "breakout": 0.70,
    "reversal": 0.30,
    "ranging": 0.40,
  } as any,
  "liquidity-reversion": {
    "ranging": 0.80,
    "quiet": 0.70,
    "reversal": 0.75,
    "trending-bull": 0.20,
    "trending-bear": 0.20,
  } as any,
  "session-momentum": {
    "trending-bull": 0.75,
    "trending-bear": 0.75,
    "breakout": 0.80,
  } as any,
  "opening-range-reversal": {
    "breakout": 0.60,
    "ranging": 0.70,
    "quiet": 0.75,
    "reversal": 0.65,
  } as any,
  "orb-breakout": {
    "breakout": 0.90,
    "trending-bull": 0.70,
    "trending-bear": 0.70,
    "quiet": 0.20,
    "volatile": 0.10,
  } as any,
  "donchian-breakout": {
    "breakout": 0.85,
    "trending-bull": 0.80,
    "trending-bear": 0.80,
    "ranging": 0.15,
  } as any,
  "wq-trend-mom": {
    "trending-bull": 0.90,
    "trending-bear": 0.90,
    "breakout": 0.75,
    "ranging": 0.10,
    "volatile": 0.30,
    "quiet": 0.40,
  } as any,
  "daily-range-breakout": {
    "breakout": 0.85,
    "trending-bull": 0.60,
    "trending-bear": 0.60,
    "quiet": 0.15,
  } as any,
};

// ── Session gating ──
// Some strategies only work during specific sessions

const STRATEGY_SESSION_PREFERENCE: Record<string, ("asia" | "london" | "ny-open" | "ny-mid" | "ny-close")[]> = {
  "orb-breakout": ["ny-open"],
  "opening-range-reversal": ["ny-open"],
  "session-momentum": ["ny-open", "ny-mid"],
  "wq-trend-mom": ["asia", "london"],     // From memory: WINS in Asia+London, LOSES in NY
  "ict-displacement": ["ny-open", "ny-mid", "london"],
  "daily-range-breakout": ["ny-open"],
};

// ── Strategy correlation groups ──
// Strategies in the same group should NOT both fire

const CORRELATION_GROUPS: Record<string, string[]> = {
  "breakout": ["orb-breakout", "daily-range-breakout", "donchian-breakout"],
  "momentum": ["wq-trend-mom", "session-momentum"],
  "reversal": ["liquidity-reversion", "opening-range-reversal"],
};

function getCorrelationGroup(strategyId: string): string | null {
  for (const [group, members] of Object.entries(CORRELATION_GROUPS)) {
    if (members.includes(strategyId)) return group;
  }
  return null;
}

// ── Regime Classifier ──

export function classifyRegime(bars: Bar[]): RegimeAnalysis {
  const now = new Date();
  const nyMinutes = (now.getUTCHours() * 60 + now.getUTCMinutes() - 4 * 60); // UTC → ET (simplified)
  
  // Session detection
  let session: RegimeAnalysis["session"] = "asia";
  if (nyMinutes >= 9 * 60 + 30 && nyMinutes < 11 * 60 + 30) session = "ny-open";
  else if (nyMinutes >= 11 * 60 + 30 && nyMinutes < 15 * 60) session = "ny-mid";
  else if (nyMinutes >= 15 * 60 && nyMinutes < 16 * 60) session = "ny-close";
  else if (nyMinutes >= 3 * 60 && nyMinutes < 9 * 60 + 30) session = "london";

  if (bars.length < 10) {
    return { regime: "quiet", confidence: 0.3, volatility: "normal", session, atrPercentile: 0.5, trendStrength: 0, rangeBound: true, nqEsDivergence: false };
  }

  const closes = bars.map(b => b.close);
  const highs = bars.map(b => b.high);
  const lows = bars.map(b => b.low);

  // Trend strength via directional movement (simplified ADX)
  let upMoves = 0, downMoves = 0;
  for (let i = 1; i < closes.length; i++) {
    if (closes[i] > closes[i-1]) upMoves++;
    else if (closes[i] < closes[i-1]) downMoves++;
  }
  const trendStrength = Math.abs(upMoves - downMoves) / closes.length;

  // ATR (14-period)
  const trs: number[] = [];
  for (let i = 1; i < bars.length; i++) {
    trs.push(Math.max(
      highs[i] - lows[i],
      Math.abs(highs[i] - closes[i-1]),
      Math.abs(lows[i] - closes[i-1])
    ));
  }
  const atr = trs.slice(-14).reduce((a, b) => a + b, 0) / Math.min(14, trs.length);
  const avgPrice = closes.reduce((a, b) => a + b, 0) / closes.length;
  const atrPct = atr / avgPrice;

  // Range detection
  const recentHigh = Math.max(...highs.slice(-10));
  const recentLow = Math.min(...lows.slice(-10));
  const rangeWidth = (recentHigh - recentLow) / avgPrice;
  const rangeBound = rangeWidth < 0.015;  // <1.5% range over 10 bars = ranging

  // Price vs moving average (20-period)
  const ma20 = closes.slice(-20).reduce((a, b) => a + b, 0) / Math.min(20, closes.length);
  const priceVsMA = (closes[closes.length-1] - ma20) / ma20;

  // Volatility classification
  let volatility: RegimeAnalysis["volatility"] = "normal";
  if (atrPct > 0.012) volatility = "extreme";
  else if (atrPct > 0.008) volatility = "high";
  else if (atrPct < 0.003) volatility = "low";

  // Recent price change
  const recentChange = (closes[closes.length-1] - closes[Math.max(0, closes.length-5)]) / closes[Math.max(0, closes.length-5)];

  // Regime classification
  let regime: MarketRegime;
  let confidence = 0.5;

  if (volatility === "extreme") {
    regime = "volatile";
    confidence = 0.7;
  } else if (rangeBound && volatility === "low") {
    regime = "quiet";
    confidence = 0.6;
  } else if (rangeBound) {
    regime = "ranging";
    confidence = 0.6;
  } else if (trendStrength > 0.6 && Math.abs(priceVsMA) > 0.005) {
    // Strong trend
    regime = priceVsMA > 0 ? "trending-bull" : "trending-bear";
    confidence = 0.7 + (trendStrength - 0.6) * 0.5;
  } else if (trendStrength > 0.4 && Math.abs(recentChange) > 0.008) {
    // Breakout
    regime = "breakout";
    confidence = 0.65;
  } else if (Math.abs(priceVsMA) > 0.01 && trendStrength < 0.3) {
    // Reversal setup (price far from MA but no trend)
    regime = "reversal";
    confidence = 0.55;
  } else {
    regime = "ranging";
    confidence = 0.4;
  }

  return {
    regime,
    confidence: Math.min(confidence, 1),
    volatility,
    session,
    atrPercentile: Math.min(atrPct / 0.01, 1),
    trendStrength,
    rangeBound,
    nqEsDivergence: false, // Would need ES bars too
  };
}

// ── Fusion Engine ──

export function fuseStrategies(
  context: StrategyContext,
  regime: RegimeAnalysis
): FusionDecision {
  const catalog = buildStrategyCatalog();
  const reasons: string[] = [];
  const rejectedStrategies: string[] = [];
  
  // ── Safety locks ──
  let safetyLock = false;
  
  if (regime.volatility === "extreme") {
    safetyLock = true;
    reasons.push("SAFETY: Extreme volatility detected — no trades");
  }
  
  if (regime.regime === "volatile") {
    safetyLock = true;
    reasons.push("SAFETY: Volatile regime — skipping all entries");
  }

  // ── Score each strategy ──

  interface ScoredSignal {
    strategyId: string;
    score: number;
    signal: StrategySignal;
    correlationGroup: string | null;
  }

  const scoredSignals: ScoredSignal[] = [];

  for (const [id, strategy] of Object.entries(catalog)) {
    try {
      const signal = strategy.generateSignal(context);
      if (!signal) {
        rejectedStrategies.push(id);
        continue;
      }

      // Base score from regime suitability
      const regimeScores = STRATEGY_REGIME_SCORES[id] || {};
      let score = regimeScores[regime.regime] || 0.3;
      
      // Session bonus/penalty
      const preferredSessions = STRATEGY_SESSION_PREFERENCE[id];
      if (preferredSessions) {
        if (preferredSessions.includes(regime.session)) {
          score += 0.15;
          reasons.push(`${id}: preferred session ${regime.session} (+0.15)`);
        } else if (preferredSessions.length > 0) {
          score -= 0.1;
          reasons.push(`${id}: not in preferred session ${regime.session} (-0.1)`);
        }
      }

      // Confidence boost from signal
      score += (signal.confidence - 0.5) * 0.3;

      // Trend alignment
      if (regime.regime === "trending-bull" && signal.side === "long") score += 0.1;
      if (regime.regime === "trending-bear" && signal.side === "short") score += 0.1;

      const correlationGroup = getCorrelationGroup(id);
      scoredSignals.push({ strategyId: id, score, signal, correlationGroup });
      
    } catch (e) {
      rejectedStrategies.push(`${id}: error`);
    }
  }

  // ── Sort by score ──
  scoredSignals.sort((a, b) => b.score - a.score);

  // ── Pick best, deconflicting correlated entries ──
  let selected: ScoredSignal | null = null;
  const usedGroups = new Set<string>();

  for (const ss of scoredSignals) {
    if (ss.score < 0.1) {
      rejectedStrategies.push(`${ss.strategyId}: score too low (${ss.score.toFixed(2)})`);
      continue;
    }

    // Check correlation deconflict
    if (ss.correlationGroup && usedGroups.has(ss.correlationGroup)) {
      rejectedStrategies.push(`${ss.strategyId}: correlated with ${ss.correlationGroup}`);
      continue;
    }

    selected = ss;
    if (ss.correlationGroup) usedGroups.add(ss.correlationGroup);
    reasons.push(`SELECTED: ${ss.strategyId} (score=${ss.score.toFixed(2)}, side=${ss.signal.side})`);
    break;
  }

  if (!selected && scoredSignals.length > 0) {
    reasons.push("No strategy passed correlation deconflict — using best available");
    selected = scoredSignals[0];
    safetyLock = true;  // override-protected
  }

  if (!selected) {
    return {
      regime,
      selectedStrategy: null,
      signal: null,
      rejectedStrategies,
      reasons,
      safetyLock: true,
    };
  }

  return {
    regime,
    selectedStrategy: selected.strategyId,
    signal: selected.signal,
    rejectedStrategies,
    reasons,
    safetyLock,
  };
}
