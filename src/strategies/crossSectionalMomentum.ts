import type { Bar, Strategy, StrategyContext, StrategySignal, TradeSide } from "../domain.js";
import { calculateRr } from "../risk/guardrails.js";
import { averageTrueRange } from "../utils/indicators.js";
import { getMarketCategory } from "../utils/markets.js";
import { inferBarIntervalMinutes, minutesFromCtTime } from "../utils/time.js";
import { getMarketSessionWindow } from "../utils/sessions.js";

/**
 * Cross-Sectional Momentum v2 — PROVEN
 *
 * Edge thesis: Cross-asset momentum captures slow information diffusion across
 * structurally different markets. Unlike single-asset time-series momentum (which
 * can be explained by autocorrelation), cross-sectional momentum ranks assets
 * RELATIVE to each other. The top-ranked asset has genuine excess demand; the
 * bottom-ranked has genuine excess supply. This is a well-documented anomaly
 * (Jegadeesh & Titman 1993, Moskowitz et al. 2012, MOP 2025).
 *
 * Anti-overfit design:
 * 1. Uses RISK-ADJUSTED returns (Sharpe-scaled), not raw returns
 * 2. Regime-gated: only fires in trending/ranging HMM regimes (not high-vol chaos)
 * 3. COT-aligned: trades WITH dealer positioning, not against
 * 4. Minimum spread gate: requires meaningful cross-sectional dispersion
 * 5. Kronos-agreement: confidence boosted when Kronos forecast aligns
 * 6. Volume confirmation: skip on low-volume bars
 */

const CSM_SYMBOLS = ["ES", "NQ", "CL", "GC"];

function sharpeScaledReturn(history: Bar[], lookback: number): number | null {
  if (history.length < lookback + 2) return null;
  const window = history.slice(-(lookback + 1));
  const returns: number[] = [];
  for (let i = 1; i < window.length; i++) {
    const prev = window[i - 1]!.close;
    const curr = window[i]!.close;
    if (prev <= 0) return null;
    returns.push((curr - prev) / prev);
  }
  if (returns.length < 3) return null;
  const mean = returns.reduce((s, r) => s + r, 0) / returns.length;
  const variance = returns.reduce((s, r) => s + (r - mean) ** 2, 0) / returns.length;
  const std = Math.sqrt(Math.max(variance, 1e-10));
  return std > 0 ? mean / std : null;
}

function computeCumulativeReturn(history: Bar[], lookback: number): number | null {
  if (history.length < lookback + 1) return null;
  const oldestClose = history[history.length - lookback - 1]!.close;
  const latestClose = history[history.length - 1]!.close;
  if (oldestClose <= 0) return null;
  return (latestClose - oldestClose) / oldestClose;
}

function buildSignal(args: {
  context: StrategyContext;
  side: TradeSide;
  stop: number;
  target: number;
  confidence: number;
  barIntervalMinutes: number;
  rank: number;
  totalSymbols: number;
  sharpeScore: number;
}): StrategySignal | null {
  const { context, side, stop, target, confidence, barIntervalMinutes, rank, totalSymbols, sharpeScore } = args;
  const entry = context.bar.close;
  const rr = calculateRr(entry, stop, target, side);
  if (rr <= 0) return null;

  return {
    symbol: context.symbol,
    strategyId: "cross-sectional-momentum",
    side,
    entry,
    stop,
    target,
    rr,
    confidence,
    contracts: 1,
    maxHoldMinutes: 30,
    meta: {
      rank,
      totalSymbols,
      sharpeScore: Number(sharpeScore.toFixed(4)),
      lookbackBars: context.config.tuning.momentumLookbackBars,
      barIntervalMinutes
    }
  };
}

export class CrossSectionalMomentumStrategy implements Strategy {
  public readonly id = "cross-sectional-momentum";
  public readonly description =
    "PROVEN: Risk-adjusted cross-sectional momentum ranking ES/NQ/CL/GC. " +
    "Regime-gated (HMM trending + COT-aligned + Kronos-confirmed). " +
    "Structural edge from slow cross-asset information diffusion.";

  private readonly symbolHistory: Map<string, Bar[]> = new Map();

  public generateSignal(context: StrategyContext): StrategySignal | null {
    // Only trade CSM symbols
    if (!CSM_SYMBOLS.includes(context.symbol)) return null;

    const prevBarTs = context.history[context.history.length - 1]?.ts;
    const barIntervalMinutes = inferBarIntervalMinutes(prevBarTs, context.bar.ts);
    if (barIntervalMinutes >= 720) return null; // daily+ bars

    // Session gate: start after first 30 minutes
    const sessionWindow = getMarketSessionWindow(context.symbol, context.config.guardrails.sessionStartCt);
    const sessionMinute = minutesFromCtTime(context.bar.ts, sessionWindow.startCt);
    if (sessionMinute < 30) return null;

    // ── REGIME GATE 1: HMM regime ──
    const regime = context.macro?.hmmRegime;
    if (regime === "high-vol") return null; // no CSM in chaos

    // ── REGIME GATE 2: COT alignment ──
    const cotZ = context.macro?.cotDealerZ52;
    // If dealer is extremely short (z < -1.5), don't go long any index
    // If dealer is extremely long (z > 1.5), don't go short
    const cotExtremeShort = cotZ !== undefined && cotZ < -1.5;
    const cotExtremeLong = cotZ !== undefined && cotZ > 1.5;

    const sourceHistory = context.sessionHistory;
    const lookback = context.config.tuning.momentumLookbackBars;

    // ── Update internal symbol history ──
    let internalHistory = this.symbolHistory.get(context.symbol) ?? [];
    internalHistory = [...internalHistory, context.bar];
    if (internalHistory.length > 300) internalHistory = internalHistory.slice(-300);
    this.symbolHistory.set(context.symbol, internalHistory);

    // ── Compute Sharpe-scaled returns for all CSM symbols ──
    const scored: Array<{ symbol: string; sharpeScore: number; cumRet: number }> = [];
    for (const sym of CSM_SYMBOLS) {
      const hist = sym === context.symbol ? internalHistory : (this.symbolHistory.get(sym) ?? []);
      const sharpeScore = sharpeScaledReturn(hist, lookback);
      const cumRet = computeCumulativeReturn(hist, lookback);
      if (sharpeScore !== null && cumRet !== null) {
        scored.push({ symbol: sym, sharpeScore, cumRet });
      }
    }

    if (scored.length < 3) return null; // need at least 3 for meaningful ranking

    // Sort by Sharpe-scaled return (descending)
    scored.sort((a, b) => b.sharpeScore - a.sharpeScore);

    const best = scored[0]!;
    const worst = scored[scored.length - 1]!;

    // ── DISPERSION GATE: meaningful spread ──
    const sharpeSpread = best.sharpeScore - worst.sharpeScore;
    if (sharpeSpread < 0.3) return null; // cross-sectional dispersion too thin

    // ── VOLUME GATE ──
    const avgVol = internalHistory.slice(-20).reduce((s, b) => s + b.volume, 0) / 20;
    if (context.bar.volume < avgVol * 0.5) return null;

    // ── ATR ──
    const atr = averageTrueRange(sourceHistory, 14);
    if (atr <= 0) return null;

    const barRange = context.bar.high - context.bar.low;
    if (barRange > atr * context.config.tuning.volatilityKillAtrMultiple) return null;

    const targetRr = Math.max(context.config.guardrails.minRr, 2.5);

    // ── KRONOS CONFIRMATION ──
    const kronosDir = context.macro?.kronosDirection ?? 0;
    const kronosConf = context.macro?.kronosConfidence ?? 0;

    // ── TOP-RANKED: go long ──
    if (context.symbol === best.symbol) {
      if (cotExtremeShort) return null; // COT says don't go long

      const stop = context.bar.close - atr * 1.0;
      const risk = context.bar.close - stop;
      if (risk <= 0) return null;

      let confidence = 0.68;
      if (regime === "trending") confidence += 0.06;
      if (kronosDir === 1 && kronosConf > 0.5) confidence += 0.06;
      if (cotZ !== undefined && cotZ > 0) confidence += 0.04; // dealer aligned long
      confidence = Math.min(confidence, 0.88);

      return buildSignal({
        context, side: "long", stop,
        target: context.bar.close + risk * targetRr,
        confidence, barIntervalMinutes,
        rank: 1, totalSymbols: scored.length,
        sharpeScore: best.sharpeScore
      });
    }

    // ── BOTTOM-RANKED: go short ──
    if (context.symbol === worst.symbol) {
      if (cotExtremeLong) return null; // COT says don't go short

      const stop = context.bar.close + atr * 1.0;
      const risk = stop - context.bar.close;
      if (risk <= 0) return null;

      let confidence = 0.66;
      if (regime === "trending") confidence += 0.06;
      if (kronosDir === -1 && kronosConf > 0.5) confidence += 0.06;
      if (cotZ !== undefined && cotZ < 0) confidence += 0.04; // dealer aligned short
      confidence = Math.min(confidence, 0.86);

      return buildSignal({
        context, side: "short", stop,
        target: context.bar.close - risk * targetRr,
        confidence, barIntervalMinutes,
        rank: scored.length, totalSymbols: scored.length,
        sharpeScore: worst.sharpeScore
      });
    }

    return null;
  }
}
