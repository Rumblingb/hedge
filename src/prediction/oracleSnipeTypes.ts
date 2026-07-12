// oracleSnipeTypes.ts — Shared types for the polykalshi-style oracle snipe strategy.
//
// Ported from 0xPr0f/polykalshi-bot/src/strategies/oracle_snipe.rs
// Uses tiered thresholds that become more aggressive as market close approaches:
//   - Tier 1 (60s-20s): require >= 0.2% price move, limit orders
//   - Tier 2 (20s-10s): require >= 0.1% price move, limit orders
//   - Tier 3 (10s-0s):  require >= 0.05% price move, IOC orders
//
// Polymarket crypto up/down markets use deterministic slugs:
//   {asset}-updown-{interval}-{window_ts}
// Supported intervals: 5-min, 15-min, 4-hour

export interface OracleSnipeConfig {
  /** How many seconds before market close to start sniping (outer window) */
  secondsBeforeClose: number;
  /** Minimum confidence level (0.0-1.0) for direction validation */
  minConfidence: number;
  /** Maximum position size per trade in USD */
  maxPositionSize: number;

  /** Tier 1 threshold: require >= this % price move (default 0.2%) */
  tier1ThresholdPct: number;
  /** Tier 2 threshold: require >= this % price move (default 0.1%) */
  tier2ThresholdPct: number;
  /** Tier 3 threshold: require >= this % price move (default 0.05%) */
  tier3ThresholdPct: number;

  /** Seconds before close to enter Tier 1 (default 60) */
  tier1Seconds: number;
  /** Seconds before close to enter Tier 2 (default 20) */
  tier2Seconds: number;
  /** Seconds before close to enter Tier 3 / IOC (default 10) */
  tier3Seconds: number;

  /** Polymarket taker fee rate (0.01 = 1%) */
  feeRate: number;
}

export const DEFAULT_SNIPE_CONFIG: OracleSnipeConfig = {
  secondsBeforeClose: 120,
  minConfidence: 0.60,
  maxPositionSize: 25,
  tier1ThresholdPct: 0.20,
  tier2ThresholdPct: 0.10,
  tier3ThresholdPct: 0.05,
  tier1Seconds: 60,
  tier2Seconds: 20,
  tier3Seconds: 10,
  feeRate: 0.01,
};

/** Supported assets */
export const SNIPE_ASSETS = ["btc", "eth", "sol"] as const;
export type SnipeAsset = (typeof SNIPE_ASSETS)[number];

/**
 * Supported intervals — must match Polymarket's deterministic slug convention.
 * Polymarket creates slugs like: btc-updown-5m-{window_ts}
 * Verified on-chain: 5-min, 15-min, 4-hour.
 * NOTE: 1-hour crypto markets do NOT exist on Polymarket.
 */
export const SNIPE_INTERVALS = ["5m", "15m"] as const;
export type SnipeInterval = (typeof SNIPE_INTERVALS)[number];

export function intervalSeconds(interval: SnipeInterval): number {
  switch (interval) {
    case "5m": return 300;
    case "15m": return 900;
    default: return 300;
  }
}

export function binanceSymbol(asset: SnipeAsset): string {
  return `${asset.toUpperCase()}USDT`;
}

export interface SnipeMarket {
  eventTitle: string;
  marketQuestion: string;
  conditionId: string;
  tokenIdUp: string;
  tokenIdDown: string;
  upPrice: number;
  downPrice: number;
  closesAt: number;  // Unix timestamp
  asset: SnipeAsset;
  interval: SnipeInterval;
}

export interface TickerSnapshot {
  /** Current Binance price */
  price: number;
  /** Kline open price */
  klineOpen: number;
  /** Price change % */
  priceChangePct: number;
  /** Predicted outcome "Up" or "Down" */
  predictedOutcome: "Up" | "Down";
  /** Simple confidence (absolute price change / avg vol estimate) */
  confidence: number;
  /** Kline close price */
  klineClose: number;
}

export interface SnipeSignal {
  ts: number;
  asset: SnipeAsset;
  interval: SnipeInterval;
  market: SnipeMarket;
  ticker: TickerSnapshot;
  timeTier: 1 | 2 | 3;
  useIoc: boolean;
  threshold: number;
  priceChangePct: number;
  predictedOutcome: "Up" | "Down";
  targetPrice: number;
  fee: number;
  totalCost: number;
  netProfit: number;
  isProfitable: boolean;
  passed: boolean;
  reason: string;
}

export interface SnipeResolution {
  conditionId: string;
  asset: SnipeAsset;
  interval: SnipeInterval;
  closesAt: number;
  prediction: "Up" | "Down";
  entryPrice: number;
  feeCents: number;
  foundAt: number;
  actualOutcome: "Up" | "Down" | null;
  won: boolean | null;
  actualPnlCents: number | null;
}
