/**
 * #42 Beta-Dependent Gamma Feedback & Volatility Amplification
 * Source: Dai, H. (Nov 2025). "Beta-Dependent Gamma Feedback and Endogenous
 *   Volatility Amplification in Option Markets." arXiv:2511.22766.
 *
 * Key finding: Derives a stability condition for gamma-squeeze onset by
 * modeling the nonlinear recursive feedback loop between market-maker
 * delta hedging and price movements. Critical insight:
 *   LOW-BETA stocks exhibit disproportionately strong gamma feedback.
 *   → Beta normalization is essential for accurate gamma exposure measurement.
 *
 * Stability condition formula:
 *   |γ × ΔS| < liquidity_depth × (1 - β/β_max)
 *   When violated → gamma squeeze likely → trade with the amplification.
 *
 * Implementation: For futures (no options data needed for v1):
 *   - Compute realized beta vs ES
 *   - Estimate implied gamma exposure from vol surface steepness
 *   - Signal when gamma imbalance exceeds stability threshold
 *   - Trade with the dealer hedging flow (trend continuation)
 *
 * Market logic: When dealers are short gamma, their hedging amplifies
 * price moves. Low-beta assets have stronger gamma feedback because
 * their price moves are less diversified away.
 */
import type { Bar, Strategy, StrategyContext, StrategySignal, TradeSide } from "../domain.js";
import { calculateRr } from "../risk/guardrails.js";
import { averageTrueRange } from "../utils/indicators.js";
import { inferBarIntervalMinutes } from "../utils/time.js";

const TARGET_SYMBOLS = ["ES", "NQ", "CL", "GC"];
const BETA_LOOKBACK = 50; // bars for beta estimation
const GAMMA_LOOKBACK = 20; // bars for gamma exposure estimation
const STABILITY_BUFFER = 0.15; // buffer below stability threshold

/**
 * Compute rolling beta vs ES benchmark.
 * beta = Cov(asset_returns, benchmark_returns) / Var(benchmark_returns)
 */
function computeBeta(
  returns: number[],
  benchmarkReturns: number[],
  lookback: number,
): number | null {
  if (returns.length < lookback || benchmarkReturns.length < lookback) return null;

  const assetWindow = returns.slice(-lookback);
  const benchWindow = benchmarkReturns.slice(-lookback);

  const meanA = assetWindow.reduce((a, b) => a + b, 0) / lookback;
  const meanB = benchWindow.reduce((a, b) => a + b, 0) / lookback;

  let cov = 0;
  let varB = 0;
  for (let i = 0; i < lookback; i++) {
    cov += (assetWindow[i]! - meanA) * (benchWindow[i]! - meanB);
    varB += (benchWindow[i]! - meanB) ** 2;
  }

  return varB > 0 ? cov / varB : null;
}

/**
 * Estimate gamma exposure from price-volume dynamics.
 * Proxy: gamma ~ Δvol / Δprice (convexity of vol surface).
 * Negative gamma = vol increases as price moves away (dealers short gamma).
 */
function estimateGammaExposure(history: Bar[], lookback: number): number | null {
  if (history.length < lookback + 1) return null;

  const window = history.slice(-lookback);
  const returns: number[] = [];
  const volChanges: number[] = [];

  for (let i = 1; i < window.length; i++) {
    const ret = Math.log(window[i]!.close / window[i - 1]!.close);
    returns.push(ret);

    // Vol change proxy: high-low range change
    const prevRange = (window[i - 1]!.high - window[i - 1]!.low) / window[i - 1]!.close;
    const currRange = (window[i]!.high - window[i]!.low) / window[i]!.close;
    volChanges.push(currRange - prevRange);
  }

  if (returns.length < 3) return null;

  // Gamma proxy: correlation between returns^2 and vol changes
  // Positive: dealers long gamma (stabilizing)
  // Negative: dealers short gamma (destabilizing)
  const retSq = returns.map((r) => r * r);
  const meanRetSq = retSq.reduce((a, b) => a + b, 0) / retSq.length;
  const meanVolCh = volChanges.reduce((a, b) => a + b, 0) / volChanges.length;

  let cov = 0;
  let varRetSq = 0;
  for (let i = 0; i < retSq.length; i++) {
    cov += (retSq[i]! - meanRetSq) * (volChanges[i]! - meanVolCh);
    varRetSq += (retSq[i]! - meanRetSq) ** 2;
  }

  if (varRetSq <= 0) return null;
  return cov / varRetSq; // Gamma proxy: >0 = long gamma, <0 = short gamma
}

/**
 * Compute stability condition.
 * Return: "stable" | "amplifying_up" | "amplifying_down"
 */
function computeStability(
  gammaProxy: number,
  beta: number,
  atr: number,
  price: number,
): { regime: string; severity: number } {
  // Beta-normalized gamma
  const betaNorm = Math.max(beta, 0.1);
  const normalizedGamma = gammaProxy / betaNorm;

  // Stability threshold: normalized gamma must be small relative to liquidity
  // Lower beta → higher normalized gamma → more unstable
  const volRatio = atr / price; // Normalized volatility
  const stabilityThreshold = volRatio * (1 + Math.abs(normalizedGamma));

  // Severity: how far beyond threshold
  const severity = Math.abs(normalizedGamma) / (volRatio + 0.001);

  if (Math.abs(normalizedGamma) < stabilityThreshold * (1 - STABILITY_BUFFER)) {
    return { regime: "stable", severity };
  }

  if (normalizedGamma < 0) {
    return { regime: "amplifying_down", severity }; // Short gamma → sell-off amplification
  }
  return { regime: "amplifying_up", severity }; // Long gamma → rally amplification
}

export class GammaStabilityStrategy implements Strategy {
  public readonly id = "gamma-stability";
  public readonly description =
    "Beta-normalized gamma feedback stability detection. " +
    "Signals when dealer gamma positioning creates amplification risk. " +
    "Trades WITH the amplification flow. Source: Dai 2025 arXiv:2511.22766.";

  private readonly symbolHistory: Map<string, Bar[]> = new Map();
  private readonly esHistory: Bar[] = []; // ES as benchmark for beta

  public generateSignal(context: StrategyContext): StrategySignal | null {
    if (!TARGET_SYMBOLS.includes(context.symbol)) return null;

    const prevBarTs = context.history[context.history.length - 1]?.ts;
    const barIntervalMinutes = inferBarIntervalMinutes(prevBarTs, context.bar.ts);
    if (barIntervalMinutes >= 240) return null; // Skip daily bars

    // Track ES for beta computation
    if (context.symbol === "ES") {
      this.esHistory.push(context.bar);
      if (this.esHistory.length > 300) this.esHistory.splice(0, 1);
    }

    // Internal history
    let history = this.symbolHistory.get(context.symbol) ?? [];
    history = [...history, context.bar];
    if (history.length > 200) history = history.slice(-200);
    this.symbolHistory.set(context.symbol, history);

    if (history.length < BETA_LOOKBACK || this.esHistory.length < BETA_LOOKBACK) return null;

    // Compute returns for beta
    const assetReturns = computeReturns(history);
    const esReturns = computeReturns(this.esHistory);
    if (!assetReturns.length || !esReturns.length) return null;

    // Beta vs ES
    const beta = computeBeta(assetReturns, esReturns, BETA_LOOKBACK);
    if (beta === null) return null;

    // Gamma exposure proxy
    const gammaProxy = estimateGammaExposure(history, GAMMA_LOOKBACK);
    if (gammaProxy === null) return null;

    const atr = averageTrueRange(context.sessionHistory, 14);
    if (atr <= 0) return null;

    // Stability assessment
    const { regime, severity } = computeStability(gammaProxy, beta, atr, context.bar.close);

    // Don't trade stable regimes
    if (regime === "stable") return null;

    // Only trade significant amplification (severity > threshold)
    if (severity < 1.5) return null;

    // Trade direction: go WITH the amplification flow
    // Amplifying down → short (dealers selling into weakness)
    // Amplifying up → long (dealers buying into strength)
    const side: TradeSide = regime === "amplifying_down" ? "short" : "long";

    const risk = atr * 1.5;
    const targetRr = Math.max(context.config.guardrails.minRr, 2.0);

    const entry = context.bar.close;
    const stop = side === "long" ? entry - risk : entry + risk;
    const target = side === "long" ? entry + risk * targetRr : entry - risk * targetRr;

    const rr = calculateRr(entry, stop, target, side);
    if (rr <= 0) return null;

    // Confidence scales with severity and beta normalization
    const confidence = Math.min(0.75, 0.45 + severity * 0.1);

    return {
      symbol: context.symbol,
      strategyId: "gamma-stability",
      side,
      entry,
      stop,
      target,
      rr,
      confidence,
      contracts: 1,
      maxHoldMinutes: 15, // Short hold — gamma effects are intraday
      meta: {
        beta: Math.round(beta * 100) / 100,
        gammaProxy: Math.round(gammaProxy * 1000) / 1000,
        stabilityRegime: regime,
        severity: Math.round(severity * 100) / 100,
        paper: "arXiv:2511.22766",
      },
    };
  }
}

function computeReturns(history: Bar[]): number[] {
  const returns: number[] = [];
  for (let i = 1; i < history.length; i++) {
    returns.push(Math.log(history[i]!.close / history[i - 1]!.close));
  }
  return returns;
}
