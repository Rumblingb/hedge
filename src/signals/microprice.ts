/**
 * Microprice — Stoikov fair-price estimator.
 * 
 * microprice = (bid_price × ask_qty + ask_price × bid_qty) / (bid_qty + ask_qty)
 * 
 * With full L2 data: uses best bid/ask sizes directly.
 * With bar data (fallback): approximates bid_qty = bear volume, ask_qty = bull volume.
 */
export interface MicropriceInput {
  bidPrice: number;
  askPrice: number;
  bidQty: number;
  askQty: number;
}

export interface MicropriceResult {
  /** Fair price estimated from order flow imbalance */
  microprice: number;
  /** Mid price */
  mid: number;
  /** Microprice - Mid: positive = bid pressure, negative = ask pressure */
  spread: number;
  /** Normalized imbalance [-1, 1]: 1 = all bids, -1 = all asks */
  imbalance: number;
}

/**
 * Calculate microprice from L2 bid/ask data.
 * Positive spread + imbalance = buying pressure → upward microprice.
 */
export function calcMicroprice(input: MicropriceInput): MicropriceResult {
  const { bidPrice, askPrice, bidQty, askQty } = input;
  const mid = (bidPrice + askPrice) / 2;
  const totalQty = bidQty + askQty;

  if (totalQty === 0) {
    return { microprice: mid, mid, spread: 0, imbalance: 0 };
  }

  const microprice = (bidPrice * askQty + askPrice * bidQty) / totalQty;
  const imbalance = (bidQty - askQty) / totalQty; // [-1, 1]
  const spread = microprice - mid;

  return { microprice, mid, spread, imbalance };
}

/**
 * Estimate microprice from OHLCV bar data.
 * Uses bull/bear volume proxy when L2 data isn't available.
 */
export function calcMicropriceFromBar(bar: {
  open: number; high: number; low: number; close: number; volume: number;
}): MicropriceResult {
  const isBullish = bar.close > bar.open;
  const range = bar.high - bar.low;

  // Approximate bid/ask from bar structure
  // Bullish bar: closing pressure = buying → approximate ask volume
  // Bearish bar: closing pressure = selling → approximate bid volume
  const bullVol = isBullish ? bar.volume * 0.6 : bar.volume * 0.4;
  const bearVol = bar.volume - bullVol;

  // Approximate bid/ask prices from bar extremes
  const bidPrice = isBullish ? bar.low : bar.low + range * 0.1;
  const askPrice = isBullish ? bar.high - range * 0.1 : bar.high;

  return calcMicroprice({
    bidPrice, askPrice,
    bidQty: Math.round(bearVol),
    askQty: Math.round(bullVol),
  });
}
