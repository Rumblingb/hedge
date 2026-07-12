// oracleLagScalper.ts — Gengar-style Brownian Motion Oracle Lag Scalper
//
// Edge: Polymarket reprices BTC 5-min UP/DOWN markets with a lag behind Binance.
// When BTC moves significantly, we buy the correct side before the order book catches up.
//
// Calibrated from gengar bot v13 (+55% ROC, 100% WR on clean data):
//   vol = 0.12 (percentage points = 12 bps 5-min vol)
//   min_prob = 0.80, min_edge = 0.05, min_btc_delta = 0.06%
//   max_price = 0.90, min_price = 0.50
//   entry window: 240s to 10s remaining
//   quarter-Kelly sizing, min $5 / max $25 bet

export interface ScalperConfig {
  /** BTC 5-min volatility in percentage points (0.12 = 12 bps) */
  vol: number;
  /** Minimum model probability to consider entry */
  minProb: number;
  /** Minimum edge (prob - marketPrice) */
  minEdge: number;
  /** Minimum BTC delta in percentage points (0.06 = 0.06%) */
  minBtcDelta: number;
  /** Maximum market price to buy (Polymarket cents) */
  maxPrice: number;
  /** Minimum market price to buy */
  minPrice: number;
  /** Entry window: seconds remaining must be <= this to enter */
  entryWindowStart: number;
  /** Entry window: seconds remaining must be >= this to enter */
  entryWindowEnd: number;
  /** Kelly fraction (0.25 = quarter-Kelly) */
  kellyFraction: number;
  /** Minimum bet size in USD */
  minBet: number;
  /** Maximum bet size in USD */
  maxBet: number;
}

export const DEFAULT_SCALPER_CONFIG: ScalperConfig = {
  vol: 0.12,
  minProb: 0.80,
  minEdge: 0.05,
  minBtcDelta: 0.06,
  maxPrice: 0.90,
  minPrice: 0.50,
  entryWindowStart: 240,
  entryWindowEnd: 10,
  kellyFraction: 0.25,
  minBet: 7,
  maxBet: 25,
};

export interface ScalperTick {
  /** Binance BTC price at window open */
  btcOpen: number;
  /** Binance BTC price right now */
  btcNow: number;
  /** Polymarket UP token price (0-1) */
  upPrice: number;
  /** Polymarket DOWN token price (0-1) */
  downPrice: number;
  /** Seconds elapsed since window open */
  secondsElapsed: number;
  /** Total window seconds (300 for 5-min) */
  secondsTotal: number;
  /** Unix timestamp */
  ts: number;
}

export interface ScalperSignal {
  side: "UP" | "DOWN";
  /** Estimated true probability */
  prob: number;
  /** Edge = prob - marketPrice */
  edge: number;
  /** Market price of the token we're buying */
  marketPrice: number;
  /** BTC delta in percentage points (0.05 = 0.05%) */
  deltaBps: number;
  /** Kelly fraction (before fraction multiplier) */
  kellyFraction: number;
  /** Recommended bet in USD (capped at min/max) */
  recommendedBet: number;
  /** Seconds remaining in the window */
  secondsRemaining: number;
  /** Skip reason if no signal */
  skipReason?: SkipReason;
}

export type SkipReason =
  | "outside_window"
  | "delta_too_small"
  | "price_out_of_range"
  | "prob_below_min"
  | "edge_below_min"
  | "kelly_not_positive";

/**
 * Error function approximation (Abramowitz & Stegun 7.1.26).
 */
function erf(x: number): number {
  const sign = x >= 0 ? 1 : -1;
  const absX = Math.abs(x);
  const a1 = 0.254829592;
  const a2 = -0.284496736;
  const a3 = 1.421413741;
  const a4 = -1.453152027;
  const a5 = 1.061405429;
  const p = 0.3275911;
  const t = 1 / (1 + p * absX);
  const y = 1 - (((((a5 * t + a4) * t) + a3) * t + a2) * t + a1) * t * Math.exp(-absX * absX);
  return sign * y;
}

/**
 * Gengar's exact probability formula:
 *   timeFactor = secondsRemaining / 300
 *   effectiveVol = vol * sqrt(timeFactor)
 *   z = |deltaBps| / effectiveVol
 *   prob = 0.5 * (1 + erf(z / sqrt(2)))
 */
export function estimateProb(deltaBps: number, secondsRemaining: number, vol: number): number {
  const timeFactor = Math.max(secondsRemaining, 1) / 300;
  const effectiveVol = vol * Math.sqrt(timeFactor);
  if (effectiveVol <= 0) {
    return deltaBps > 0 ? 1 : 0;
  }
  const z = Math.abs(deltaBps) / effectiveVol;
  const prob = 0.5 * (1 + erf(z / Math.sqrt(2)));
  return Math.max(0.01, Math.min(0.99, prob));
}

/**
 * Run the full gengar gate chain on a tick.
 * Returns a signal if all gates pass, or null with a skip reason.
 */
export function evaluateTick(
  tick: ScalperTick,
  config: ScalperConfig = DEFAULT_SCALPER_CONFIG
): ScalperSignal | null {
  const remaining = Math.max(0, tick.secondsTotal - tick.secondsElapsed);

  // Gate 0: Entry window
  if (remaining > config.entryWindowStart || remaining < config.entryWindowEnd) {
    return { side: "UP", prob: 0, edge: 0, marketPrice: 0, deltaBps: 0, kellyFraction: 0, recommendedBet: 0, secondsRemaining: remaining, skipReason: "outside_window" };
  }

  // BTC delta in percentage points (matching gengar convention)
  const deltaBps = tick.btcOpen > 0
    ? ((tick.btcNow - tick.btcOpen) / tick.btcOpen) * 100
    : 0;

  // Gate 1: Minimum BTC delta
  if (Math.abs(deltaBps) < config.minBtcDelta) {
    return { side: "UP", prob: 0, edge: 0, marketPrice: 0, deltaBps, kellyFraction: 0, recommendedBet: 0, secondsRemaining: remaining, skipReason: "delta_too_small" };
  }

  // Gate 2: Price in range
  const side: "UP" | "DOWN" = deltaBps > 0 ? "UP" : "DOWN";
  const marketPrice = deltaBps > 0 ? tick.upPrice : tick.downPrice;
  if (marketPrice > config.maxPrice || marketPrice < config.minPrice) {
    return { side, prob: 0, edge: 0, marketPrice, deltaBps, kellyFraction: 0, recommendedBet: 0, secondsRemaining: remaining, skipReason: "price_out_of_range" };
  }

  // Gate 3: Probability
  // Gengar's prob_up computes P(trend continues) = P(close > open | delta > 0) for UP
  // AND P(close < open | delta < 0) for DOWN — same formula, uses abs(delta) internally.
  // Because P(N(-δ, σ²) < 0) = P(N(+δ, σ²) > 0) by symmetry.
  const prob = estimateProb(deltaBps, remaining, config.vol);
  if (prob < config.minProb) {
    return { side, prob, edge: 0, marketPrice, deltaBps, kellyFraction: 0, recommendedBet: 0, secondsRemaining: remaining, skipReason: "prob_below_min" };
  }

  // Gate 4: Minimum edge
  const edge = prob - marketPrice;
  if (edge < config.minEdge) {
    return { side, prob, edge, marketPrice, deltaBps, kellyFraction: 0, recommendedBet: 0, secondsRemaining: remaining, skipReason: "edge_below_min" };
  }

  // Kelly sizing
  const b = (1 - marketPrice) / Math.max(marketPrice, 0.01);
  const q = 1 - prob;
  const kelly = (b * prob - q) / Math.max(b, 0.01);
  if (kelly <= 0) {
    return { side, prob, edge, marketPrice, deltaBps, kellyFraction: 0, recommendedBet: 0, secondsRemaining: remaining, skipReason: "kelly_not_positive" };
  }

  const kellyFraction = kelly * config.kellyFraction;
  const recommendedBet = Math.max(config.minBet, Math.min(config.maxBet, config.maxBet * kellyFraction));

  return {
    side,
    prob,
    edge,
    marketPrice,
    deltaBps,
    kellyFraction,
    recommendedBet,
    secondsRemaining: remaining,
  };
}

/**
 * Backtest the scalper over historical BTC 5-min bars.
 * Each bar represents one 5-min window.
 * Simulates Polymarket prices with a lag (simplified).
 */
export interface BacktestBar {
  ts: string;
  open: number;
  high: number;
  low: number;
  close: number;
  /** Hypothetical Polymarket UP price at bar close (0-1) */
  upPrice?: number;
  /** Hypothetical Polymarket DOWN price at bar close */
  downPrice?: number;
}

export interface BacktestTrade {
  ts: string;
  side: "UP" | "DOWN";
  entryPrice: number;
  exitPrice: number;
  profit: number;
  resolved: boolean;
}

export interface BacktestResult {
  trades: BacktestTrade[];
  totalTrades: number;
  wins: number;
  losses: number;
  winRate: number;
  totalProfit: number;
  totalReturnPct: number;
  maxDrawdownPct: number;
  sharpeRatio: number;
  profitFactor: number;
}

/**
 * Simplified backtest: evaluate each bar as if we entered at the close.
 * For a real backtest you'd need tick-level data and live Polymarket order book.
 */
export function backtestScalper(
  bars: BacktestBar[],
  config: ScalperConfig = DEFAULT_SCALPER_CONFIG
): BacktestResult {
  const trades: BacktestTrade[] = [];

  for (const bar of bars) {
    const tick: ScalperTick = {
      btcOpen: bar.open,
      btcNow: bar.close,
      upPrice: bar.upPrice ?? 0.50,
      downPrice: bar.downPrice ?? 0.50,
      secondsElapsed: 290, // Near end of window (inside gate: 240→10)
      secondsTotal: 300,
      ts: Date.parse(bar.ts),
    };

    const signal = evaluateTick(tick, config);
    if (!signal || signal.skipReason) continue;

    // Determine resolution: UP wins if close > open, DOWN wins if close <= open
    // prob already correctly handles both directions (uses abs(delta) internally)
    const won = signal.side === "UP" ? bar.close > bar.open : bar.close <= bar.open;
    const exitPrice = won ? 1.0 : 0.0;
    const profit = won ? 1.0 - signal.marketPrice : -signal.marketPrice;

    trades.push({
      ts: bar.ts,
      side: signal.side,
      entryPrice: signal.marketPrice,
      exitPrice,
      profit,
      resolved: true,
    });
  }

  const totalTrades = trades.length;
  const wins = trades.filter((t) => t.profit > 0).length;
  const losses = trades.filter((t) => t.profit <= 0).length;
  const winRate = totalTrades > 0 ? wins / totalTrades : 0;
  const totalProfit = trades.reduce((sum, t) => sum + t.profit, 0);

  // Running equity for drawdown
  let equity = totalTrades > 0 ? trades[0]!.profit : 0;
  let peak = equity;
  let maxDD = 0;
  for (let i = 1; i < trades.length; i++) {
    equity += trades[i]!.profit;
    peak = Math.max(peak, equity);
    maxDD = Math.min(maxDD, equity - peak);
  }

  const avgTrade = totalTrades > 0 ? totalProfit / totalTrades : 0;
  const tradeReturns = trades.map((t) => t.profit);
  const variance = totalTrades > 1
    ? tradeReturns.reduce((sum, r) => sum + (r - avgTrade) ** 2, 0) / (totalTrades - 1)
    : 0;
  const stdDev = Math.sqrt(variance);

  return {
    trades,
    totalTrades,
    wins,
    losses,
    winRate,
    totalProfit,
    totalReturnPct: trades.length > 0 ? (totalProfit / trades.length) * 100 : 0,
    maxDrawdownPct: maxDD,
    sharpeRatio: stdDev > 0 ? (avgTrade / stdDev) * Math.sqrt(totalTrades) : 0,
    profitFactor: losses > 0 ? wins / losses : Infinity,
  };
}
