/**
 * #35 LLM-Gated Momentum with Volume/News Confirmation
 * Source: Anic, N., Barbon, A., Seiz, R., & Zarattini, C. (Oct 2025).
 *   "ChatGPT in Systematic Investing — Enhancing Risk-Adjusted Returns
 *    with LLMs." arXiv:2510.26228.
 *
 * Key finding: LLMs condition momentum portfolio entry on firm-specific news.
 * ChatGPT scores whether news supports return continuation, gating stock selection.
 * LLM-gated momentum outperforms pure price momentum on risk-adjusted basis.
 *
 * Our proxy implementation (no external LLM needed):
 * Instead of calling Ollama per bar, we use a heuristic "news coherence" score:
 *   coherence = volume_confirmation × trend_stability × low_vol_check
 * Only enter momentum trades when coherence > 0.6.
 *
 * Market logic: Momentum driven by informed institutional flow (high volume,
 * steady trend, controlled volatility) persists. Momentum without volume
 * confirmation is noise and mean-reverts.
 */
import type { Bar, Strategy, StrategyContext, StrategySignal, TradeSide } from "../domain.js";
import { calculateRr } from "../risk/guardrails.js";
import { averageTrueRange } from "../utils/indicators.js";
import { isIndexSymbol } from "../utils/markets.js";
import { inferBarIntervalMinutes, minutesFromCtTime } from "../utils/time.js";
import { getMarketSessionWindow } from "../utils/sessions.js";

const MOMENTUM_LOOKBACK = 20;
const VOLUME_LOOKBACK = 10;
const COHERENCE_THRESHOLD = 0.6;
const TARGET_SYMBOLS = ["ES", "NQ"];

function buildSignal(args: {
  context: StrategyContext;
  side: TradeSide;
  stop: number;
  target: number;
  confidence: number;
  barIntervalMinutes: number;
  coherenceScore: number;
}): StrategySignal | null {
  const { context, side, stop, target, confidence, barIntervalMinutes, coherenceScore } = args;
  const entry = context.bar.close;
  const rr = calculateRr(entry, stop, target, side);
  if (rr <= 0) return null;

  return {
    symbol: context.symbol,
    strategyId: "llm-momentum-gate",
    side,
    entry,
    stop,
    target,
    rr,
    confidence: Math.min(confidence, coherenceScore),
    contracts: 1,
    maxHoldMinutes: 20,
    meta: {
      coherenceScore: Math.round(coherenceScore * 100) / 100,
      lookback: MOMENTUM_LOOKBACK,
      barIntervalMinutes,
      paper: "arXiv:2510.26228",
    },
  };
}

/**
 * Compute momentum return over lookback.
 */
function computeMomentum(history: Bar[], lookback: number): number | null {
  if (history.length < lookback + 1) return null;
  const oldestClose = history[history.length - lookback - 1]!.close;
  const latestClose = history[history.length - 1]!.close;
  if (oldestClose <= 0) return null;
  return (latestClose - oldestClose) / oldestClose;
}

/**
 * Compute volume confirmation: is recent volume above average?
 * High volume during trend = institutional participation = higher persistence.
 */
function volumeConfirmation(history: Bar[]): number {
  if (history.length < VOLUME_LOOKBACK + 5) return 0.5;

  const recentVolumes = history.slice(-VOLUME_LOOKBACK).map((b) => b.volume);
  const olderVolumes = history.slice(-VOLUME_LOOKBACK * 2, -VOLUME_LOOKBACK).map((b) => b.volume);

  const recentAvg = recentVolumes.reduce((a, b) => a + b, 0) / recentVolumes.length;
  const olderAvg = olderVolumes.reduce((a, b) => a + b, 0) / olderVolumes.length;

  if (olderAvg <= 0) return 0.5;

  const ratio = recentAvg / olderAvg;
  // Clamp to [0, 1]: ratio < 1.0 = below avg (0), ratio > 2.0 = strongly above (1)
  return Math.max(0, Math.min(1, (ratio - 0.8) / 1.2));
}

/**
 * Trend stability: how consistently has the price moved in one direction?
 * High stability = steady trend, low stability = choppy.
 */
function trendStability(history: Bar[], lookback: number): number {
  if (history.length < lookback + 1) return 0;

  const window = history.slice(-lookback);
  let upBars = 0;
  let downBars = 0;

  for (let i = 1; i < window.length; i++) {
    if (window[i]!.close > window[i - 1]!.close) upBars++;
    else if (window[i]!.close < window[i - 1]!.close) downBars++;
  }

  const total = upBars + downBars;
  if (total === 0) return 0;

  // Ratio of dominant direction
  return Math.max(upBars, downBars) / total;
}

/**
 * Low volatility check: momentum works better in moderate vol, not extreme.
 */
function volCheck(atr: number, price: number): number {
  const volRatio = atr / price;
  // Optimal: 0.5-2% daily ATR/price. Outside = penalty.
  if (volRatio < 0.002) return 0.3; // Too quiet
  if (volRatio > 0.03) return 0.2;  // Too volatile
  return 1.0; // Optimal range
}

export class LlmMomentumGateStrategy implements Strategy {
  public readonly id = "llm-momentum-gate";
  public readonly description =
    "LLM-gated momentum with volume/news confirmation proxy. " +
    "Coherence score (volume × trend stability × vol check) gates momentum entries. " +
    "Only trades when coherence > 0.6. Source: Anic et al. arXiv:2510.26228.";

  private readonly symbolHistory: Map<string, Bar[]> = new Map();

  public generateSignal(context: StrategyContext): StrategySignal | null {
    if (!isIndexSymbol(context.symbol)) return null;

    const prevBarTs = context.history[context.history.length - 1]?.ts;
    const barIntervalMinutes = inferBarIntervalMinutes(prevBarTs, context.bar.ts);
    if (barIntervalMinutes >= 720) return null;

    const sessionWindow = getMarketSessionWindow(
      context.symbol,
      context.config.guardrails.sessionStartCt,
    );
    const sessionMinute = minutesFromCtTime(context.bar.ts, sessionWindow.startCt);
    if (sessionMinute < 30) return null;

    // Internal history
    let history = this.symbolHistory.get(context.symbol) ?? [];
    history = [...history, context.bar];
    if (history.length > 300) history = history.slice(-300);
    this.symbolHistory.set(context.symbol, history);

    // Momentum signal
    const momentum = computeMomentum(history, MOMENTUM_LOOKBACK);
    if (momentum === null || Math.abs(momentum) < 0.002) return null; // Need min 0.2% move

    // Coherence score = volume × trend × vol
    const volConf = volumeConfirmation(history);
    const trendStab = trendStability(history, MOMENTUM_LOOKBACK);
    const atr = averageTrueRange(context.sessionHistory, 14);
    if (atr <= 0) return null;
    const volOk = volCheck(atr, context.bar.close);

    const coherenceScore = volConf * trendStab * volOk;

    // Gate: only trade when coherence is high
    if (coherenceScore < COHERENCE_THRESHOLD) return null;

    // Direction: go with momentum
    const side: TradeSide = momentum > 0 ? "long" : "short";
    const risk = atr * 1.2;
    const targetRr = Math.max(context.config.guardrails.minRr, 2.0);

    const entry = context.bar.close;
    const stop = side === "long" ? entry - risk : entry + risk;
    const target = side === "long" ? entry + risk * targetRr : entry - risk * targetRr;

    return buildSignal({
      context,
      side,
      stop,
      target,
      confidence: 0.65,
      barIntervalMinutes,
      coherenceScore,
    });
  }
}
