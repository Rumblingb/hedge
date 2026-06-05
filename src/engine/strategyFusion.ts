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
import { existsSync, readFileSync } from "node:fs";
import { resolve as resolvePath } from "node:path";
import { buildStrategyCatalog } from "../strategies/wctcEnsemble.js";
import { fitHmmRegime, type HmmRegime, type HmmRegimeModel } from "../signals/hmmRegime.js";

// ── HMM Regime Detector (lazy-loaded Baum-Welch) ──

let hmmModelCache: { model: HmmRegimeModel; barsLength: number; trainedAt: number } | null = null;
let hmmCallCount = 0;

const HMM_RETRAIN_INTERVAL_MS = 3_600_000;  // retrain HMM hourly
const HMM_RETRAIN_CALLS = 100;              // or every 100 classifyRegime calls
const HMM_MIN_BARS = 100;                   // need 100+ bars for meaningful HMM
const HMM_MAX_ITERATIONS = 20;              // lighter training for 16GB Mac Mini

const HMM_TO_MARKET: Record<HmmRegime, MarketRegime> = {
  "trending": "trending-bull",   // refined by direction below
  "range-chop": "ranging",
  "high-vol": "volatile",
  "low-vol": "quiet",
};

export function isHmmRegimeFusionEnabled(env: NodeJS.ProcessEnv = process.env): boolean {
  return env.BILL_ENABLE_HMM_REGIME_FUSION === "true";
}

/** Run HMM-based regime classification (lazy-trained, cached). */
function classifyWithHmm(bars: Bar[]): { regime: MarketRegime; confidence: number } | null {
  if (!isHmmRegimeFusionEnabled()) return null;
  if (bars.length < HMM_MIN_BARS) return null;

  const now = Date.now();
  hmmCallCount++;

  // Train or retrain if needed
  const shouldRetrain = !hmmModelCache
    || hmmModelCache.barsLength !== bars.length
    || (now - hmmModelCache.trainedAt) > HMM_RETRAIN_INTERVAL_MS
    || hmmCallCount % HMM_RETRAIN_CALLS === 0;

  if (shouldRetrain) {
    try {
      const model = fitHmmRegime({ bars, nStates: 4, maxIterations: HMM_MAX_ITERATIONS });
      hmmModelCache = { model, barsLength: bars.length, trainedAt: now };
    } catch {
      return null; // HMM unavailable — keep heuristic
    }
  }

  const last = hmmModelCache!.model.regimeDistribution.at(-1);
  if (!last) return null;

  const confidence = Math.max(...last.probabilities);
  let regime: MarketRegime;

  if (last.regime === "trending") {
    // trending state needs direction from recent price action
    const lookback = Math.min(10, bars.length - 1);
    const recentChange = (bars[bars.length - 1].close - bars[bars.length - 1 - lookback].close)
      / bars[bars.length - 1 - lookback].close;
    regime = recentChange > 0 ? "trending-bull" : "trending-bear";
  } else {
    regime = HMM_TO_MARKET[last.regime] ?? "ranging";
  }

  return { regime, confidence: Math.min(confidence * 1.15, 1.0) };
}

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
  // ── EMPIRICALLY VALIDATED EDGES (AI Scientist walkforward on 3yr NQ data) ──
  "wq-vol-regime-60m":          { "trending-bull": 0.75, "trending-bear": 0.75, "breakout": 0.60, "ranging": 0.35, "quiet": 0.40, "reversal": 0.30 } as any,
  // ── ORIGINAL 8 (design-intent, NOT validated — scores preserved for compatibility) ──
  "ict-displacement":           { "trending-bull": 0.85, "trending-bear": 0.85, "breakout": 0.70, "reversal": 0.30, "ranging": 0.40, "quiet": 0.30 } as any,
  "liquidity-reversion":        { "ranging": 0.80, "quiet": 0.70, "reversal": 0.75, "trending-bull": 0.20, "trending-bear": 0.20, "breakout": 0.25 } as any,
  "session-momentum":           { "trending-bull": 0.75, "trending-bear": 0.75, "breakout": 0.80, "ranging": 0.35, "quiet": 0.25 } as any,
  "opening-range-reversal":     { "breakout": 0.60, "ranging": 0.70, "quiet": 0.75, "reversal": 0.65, "trending-bull": 0.25, "trending-bear": 0.25 } as any,
  "orb-breakout":               { "breakout": 0.90, "trending-bull": 0.70, "trending-bear": 0.70, "quiet": 0.20, "volatile": 0.10, "ranging": 0.30 } as any,
  "donchian-breakout":          { "breakout": 0.85, "trending-bull": 0.80, "trending-bear": 0.80, "ranging": 0.15, "quiet": 0.10 } as any,
  "wq-trend-mom":               { "trending-bull": 0.90, "trending-bear": 0.90, "breakout": 0.75, "ranging": 0.10, "volatile": 0.30, "quiet": 0.40 } as any,
  "daily-range-breakout":       { "breakout": 0.85, "trending-bull": 0.60, "trending-bear": 0.60, "quiet": 0.15, "ranging": 0.20 } as any,
  // ── NEWLY CATALOGED (design-intent, awaiting walkforward validation) ──
  "seasonality":                 { "quiet": 0.70, "trending-bull": 0.65, "trending-bear": 0.65, "ranging": 0.60, "breakout": 0.40, "reversal": 0.30 } as any,
  "gap-fade":                    { "ranging": 0.75, "quiet": 0.70, "reversal": 0.65, "breakout": 0.30, "trending-bull": 0.25, "trending-bear": 0.25, "volatile": 0.15 } as any,
  "power-hour":                  { "trending-bull": 0.75, "trending-bear": 0.75, "breakout": 0.80, "ranging": 0.35, "quiet": 0.30 } as any,
  "supply-demand":               { "ranging": 0.80, "reversal": 0.75, "quiet": 0.60, "breakout": 0.45, "trending-bull": 0.35, "trending-bear": 0.35 } as any,
  "rsi-divergence":              { "reversal": 0.85, "ranging": 0.70, "quiet": 0.55, "breakout": 0.25, "trending-bull": 0.20, "trending-bear": 0.20 } as any,
  "scalping":                    { "quiet": 0.80, "ranging": 0.65, "breakout": 0.40, "trending-bull": 0.30, "trending-bear": 0.30, "volatile": 0.20 } as any,
  "carry-trade":                 { "trending-bull": 0.80, "trending-bear": 0.80, "quiet": 0.60, "ranging": 0.25 } as any,
  "market-profile":              { "ranging": 0.70, "reversal": 0.65, "quiet": 0.60, "breakout": 0.50, "trending-bull": 0.35, "trending-bear": 0.35 } as any,
  "overnight-hold":              { "trending-bull": 0.85, "trending-bear": 0.85, "breakout": 0.60, "quiet": 0.40, "ranging": 0.20 } as any,
  "dark-pool-print":             { "trending-bull": 0.70, "trending-bear": 0.70, "reversal": 0.75, "breakout": 0.50, "ranging": 0.35, "quiet": 0.25 } as any,
  // ── OPTIONS ZONE (proxy-based, no real options data) ──
  "gamma-stability":             { "trending-bull": 0.55, "trending-bear": 0.55, "breakout": 0.45, "volatile": 0.70, "ranging": 0.60, "quiet": 0.35, "reversal": 0.65 } as any,
  "options-selling-framework":   { "ranging": 0.80, "quiet": 0.65, "reversal": 0.60, "trending-bull": 0.20, "trending-bear": 0.20, "volatile": 0.05, "breakout": 0.15 } as any,
  "vol-risk-premium":            { "trending-bull": 0.40, "trending-bear": 0.40, "volatile": 0.75, "reversal": 0.70, "ranging": 0.50, "quiet": 0.55, "breakout": 0.20 } as any,
  "volatility-regime":           { "trending-bull": 0.65, "trending-bear": 0.65, "volatile": 0.30, "quiet": 0.75, "ranging": 0.60, "breakout": 0.40, "reversal": 0.35 } as any,
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

export const CORRELATION_GROUPS: Record<string, string[]> = {
  "breakout": ["orb-breakout", "daily-range-breakout"],
  "momentum": ["wq-trend-mom"],
  "reversal": ["liquidity-reversion", "opening-range-reversal", "gap-fade"],
  "options-zone": ["gamma-stability", "vol-risk-premium", "options-selling-framework", "volatility-regime"],
};

const OPTIONS_ZONE_STRATEGIES = new Set(CORRELATION_GROUPS["options-zone"]);

export function isOptionsZoneStrategy(strategyId: string): boolean {
  return OPTIONS_ZONE_STRATEGIES.has(strategyId);
}

export function allowsProxyOptionsFusion(env: NodeJS.ProcessEnv = process.env): boolean {
  return env.BILL_ALLOW_PROXY_OPTIONS_FUSION === "true";
}

export function shouldBlockOptionsZoneFusionStrategy(
  strategyId: string,
  env: NodeJS.ProcessEnv = process.env
): boolean {
  return isOptionsZoneStrategy(strategyId) && !allowsProxyOptionsFusion(env);
}

// ── Strategy Decay Awareness ──
// Reads signal-decay-ledger to penalize strategies that lost edge

let decayCache: { entries: Array<{ key: string; status: string }>; loadedAt: number } | null = null;
const DECAY_CACHE_TTL_MS = 300_000; // 5 min

function getDecayMultiplier(strategyId: string): number {
  // Lazy-load decay ledger
  const now = Date.now();
  if (!decayCache || now - decayCache.loadedAt > DECAY_CACHE_TTL_MS) {
    try {
      const decayPath = resolvePath(
        process.env.BILL_SIGNAL_DECAY_LEDGER_PATH ?? ".rumbling-hedge/state/signal-decay-ledger.latest.json"
      );
      if (existsSync(decayPath)) {
        const raw = readFileSync(decayPath, "utf8");
        const report = JSON.parse(raw);
        decayCache = { entries: report.entries ?? [], loadedAt: now };
      } else {
        decayCache = { entries: [], loadedAt: now };
      }
    } catch {
      decayCache = { entries: [], loadedAt: now };
    }
  }

  const entry = decayCache.entries.find((e) => e.key === strategyId);
  if (!entry) return 1.0; // Unknown = assume active

  switch (entry.status) {
    case "active":   return 1.0;
    case "shadow":   return 0.7;
    case "decaying": return 0.3;
    case "disabled": return 0.0;
    default:         return 1.0;
  }
}

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

  // ── HMM override: if Baum-Welch model gives higher-confidence classification, use it ──
  try {
    const hmm = classifyWithHmm(bars);
    if (hmm && hmm.confidence > confidence) {
      regime = hmm.regime;
      confidence = hmm.confidence;
    }
  } catch {
    // HMM failed silently — keep heuristic result
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

      if (shouldBlockOptionsZoneFusionStrategy(id)) {
        rejectedStrategies.push(`${id}: options-zone proxy blocked`);
        reasons.push(`${id}: options-zone proxy blocked until real options data is wired or BILL_ALLOW_PROXY_OPTIONS_FUSION=true`);
        continue;
      }

      // Base score from regime suitability
      const regimeScores = STRATEGY_REGIME_SCORES[id] || {};
      let score = regimeScores[regime.regime] || 0.3;
      
      // Apply decay multiplier (from signal-decay-ledger)
      const decayMul = getDecayMultiplier(id);
      if (decayMul < 1.0) {
        reasons.push(`${id}: decay=${decayMul.toFixed(1)} (decay ledger penalty)`);
      }
      score *= decayMul;
      
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
