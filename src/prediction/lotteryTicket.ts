// lotteryTicket.ts — Lottery ticket edge for Gengar PM Bot
//
// Edge thesis: BTC 5-min UP/DOWN markets systematically underprice extreme
// low-probability outcomes (long-shot bias). By buying UP tokens at 3-30¢
// with micro-sized bets, we capture this structural mispricing.
//
// Based on @marketing101 Polymarket profile analysis:
//   - +$382,512 ALL-time P&L (~2 months)
//   - 3,649 predictions, 100% BTC Up/Down 5-min, 100% UP side
//   - Lottery entries: 3-29¢, 0.2-0.8 shares
//   - Win examples: 14¢ +614%, 29¢ +244%
//
// Key difference from Gengar oracleLagScalper:
//   - Gengar: high-prob (80%+), medium prices (50-90¢)
//   - Lottery: any prob, extreme low prices (3-30¢)
//   - Both trade same BTC 5-min markets, different regimes

import type { Bar } from "../domain.js";
import { fetchPolymarketBook, quoteFromBook } from "./polymarketBook.js";

// ═══════════════════════════════════════════════════════════════
// Config
// ═══════════════════════════════════════════════════════════════

export interface LotteryTicketConfig {
  /** Maximum market price to enter (cents). Above this, it's not a lottery ticket. */
  maxEntryPrice: number;
  /** Minimum market price to enter. Below this, too illiquid. */
  minEntryPrice: number;
  /** Fraction of bankroll to risk per trade */
  kellyFraction: number;
  /** Minimum bet size in USD */
  minBetUsd: number;
  /** Maximum bet size in USD */
  maxBetUsd: number;
  /** Only consider markets with spread below this percentage */
  maxSpreadPct: number;
  /** Minimum depth (USD) on the ask side */
  minDepthUsd: number;
  /** How many recent BTC 5-min bars to use for unconditional UP probability */
  lookbackBars: number;
}

export const DEFAULT_LOTTERY_CONFIG: LotteryTicketConfig = {
  maxEntryPrice: 0.30,
  minEntryPrice: 0.01,
  kellyFraction: 0.005,    // 0.5% of bankroll — extremely conservative
  minBetUsd: 0.02,
  maxBetUsd: 1.00,
  maxSpreadPct: 15,         // Wider spread acceptable for extreme tails
  minDepthUsd: 10,          // Tiny depth is fine — we're buying 0.2-0.8 shares
  lookbackBars: 288,        // 24 hours of 5-min bars
};

// ═══════════════════════════════════════════════════════════════
// Types
// ═══════════════════════════════════════════════════════════════

export interface LotteryMarket {
  tokenId: string;
  slug: string;
  title: string;
  conditionId?: string;
}

export interface LotterySignal {
  tokenId: string;
  marketTitle: string;
  /** UP unconditional probability from BTC historical data */
  estimatedProb: number;
  /** Market ask price (Polymarket implied probability) */
  marketPrice: number;
  /** Edge = estimatedProb - marketPrice (must be positive to enter) */
  edge: number;
  /** Recommended shares to buy */
  shares: number;
  /** Entry cost in USD */
  costUsd: number;
  /** Expected value in USD */
  expectedValue: number;
  /** Whether this market is eligible for Polymarket liquidity rewards */
  rewardsEligible: boolean;
}

export interface LotteryPosition {
  tokenId: string;
  marketTitle: string;
  entryPrice: number;
  shares: number;
  costUsd: number;
  entryTs: number;
  resolved: boolean;
  won: boolean | null;
  payout: number;
  pnl: number;
}

// ═══════════════════════════════════════════════════════════════
// BTC UP Probability Estimation
// ═══════════════════════════════════════════════════════════════

/**
 * Compute unconditional UP probability from recent BTC 5-min bars.
 * UP = bar close > bar open. This is a simple, assumption-free estimate.
 * 
 * BTC has a natural upward drift over time, making P(UP) slightly > 0.50
 * in any given 5-min window.
 */
export function estimateUpProbability(bars: Bar[]): number {
  if (bars.length === 0) return 0.51; // Slightly bullish prior
  
  const upCount = bars.filter((bar) => bar.close > bar.open).length;
  const downCount = bars.filter((bar) => bar.close < bar.open).length;
  const total = upCount + downCount;
  
  if (total === 0) return 0.51;
  
  // Add Laplace smoothing (+1 pseudo-count each) to avoid 0 or 1
  return (upCount + 1) / (total + 2);
}

// ═══════════════════════════════════════════════════════════════
// Market Discovery — BTC Up/Down 5-min markets
// ═══════════════════════════════════════════════════════════════

/**
 * Generate slugs for upcoming BTC Up/Down 5-min markets.
 * Pattern: btc-updown-5m-{unix_timestamp} where timestamps align to 5-min boundaries.
 * 
 * Polymarket creates markets ~1 hour ahead. We look at the next 12 windows
 * (60 minutes) and the previous 12 windows (already created, may still be active).
 */
function generateMarketSlugs(count: number = 24): string[] {
  const now = Math.floor(Date.now() / 1000);
  const windowSec = 300; // 5 minutes
  const currentWindow = now - (now % windowSec);
  
  const slugs: string[] = [];
  // Look ahead and behind: next 12 windows + previous 12 windows
  for (let i = -12; i < count - 12; i++) {
    const ts = currentWindow + i * windowSec;
    slugs.push(`btc-updown-5m-${ts}`);
  }
  return slugs;
}

/**
 * Fetch market data for a single slug from Polymarket's event API.
 * Returns UP token ID, condition ID, and title if found.
 */
async function fetchMarketFromSlug(slug: string): Promise<LotteryMarket | null> {
  try {
    const resp = await fetch(`https://polymarket.com/api/event/slug/${slug}`, {
      headers: { 
        accept: "application/json",
        "user-agent": "lottery-ticket/0.1",
      },
      signal: AbortSignal.timeout(5_000),
    });
    
    if (!resp.ok) return null;
    const data = (await resp.json()) as any;
    
    const markets = data.markets ?? [];
    if (markets.length === 0) return null;
    
    const m = markets[0];
    let tokenIds: string[] = [];
    if (Array.isArray(m.clobTokenIds)) {
      tokenIds = m.clobTokenIds;
    } else if (typeof m.clobTokenIds === "string") {
      try { tokenIds = JSON.parse(m.clobTokenIds); } catch { tokenIds = []; }
    }
    
    const outcomes: string[] = Array.isArray(m.outcomes)
      ? m.outcomes
      : typeof m.outcomes === "string"
        ? (() => { try { return JSON.parse(m.outcomes); } catch { return []; } })()
        : [];
    
    // UP token is index 0
    if (tokenIds.length === 0 || outcomes.length === 0) return null;
    const isUp = outcomes[0]?.toLowerCase() === "up";
    if (!isUp) return null;
    
    return {
      tokenId: tokenIds[0]!,
      slug,
      title: m.question ?? data.title ?? slug,
      conditionId: m.conditionId ?? data.conditionId ?? undefined,
    };
  } catch {
    return null;
  }
}

/**
 * Discover active BTC Up/Down 5-min markets by generating slugs
 * and fetching market data from Polymarket's event API.
 */
export async function discoverLotteryMarkets(
  maxMarkets: number = 20,
): Promise<LotteryMarket[]> {
  // Try slug-based discovery first
  const slugs = generateMarketSlugs(24);
  const markets: LotteryMarket[] = [];
  
  // Fetch in batches of 4 to avoid rate limiting
  for (let i = 0; i < slugs.length && markets.length < maxMarkets; i += 4) {
    const batch = slugs.slice(i, i + 4);
    const results = await Promise.all(batch.map(fetchMarketFromSlug));
    
    for (const r of results) {
      if (r && markets.length < maxMarkets) {
        markets.push(r);
      }
    }
  }
  
  // Fallback: use static token store (extracted from browser sessions)
  if (markets.length === 0) {
    try {
      const fs = await import("node:fs/promises");
      const path = await import("node:path");
      const tokenPath = path.join(
        process.cwd(),
        ".rumbling-hedge/state/btc-5min-tokens.json",
      );
      const raw = await fs.readFile(tokenPath, "utf8");
      const store = JSON.parse(raw);
      const tokens = store.tokens ?? [];
      for (const t of tokens.slice(0, maxMarkets)) {
        if (t.outcome?.toLowerCase() === "up" && t.tokenId) {
          markets.push({
            tokenId: t.tokenId,
            slug: t.source ?? "static",
            title: t.title ?? "BTC Up/Down 5m",
            conditionId: t.conditionId ?? undefined,
          });
        }
      }
    } catch {
      // No static tokens available — return empty
    }
  }
  
  return markets;
}

/**
 * Batch-check Gamma API for rewards eligibility.
 * Returns a Set of token IDs that have rewardsMinSize > 0 and rewardsMaxSpread > 0.
 */
async function fetchRewardsEligible(tokenIds: string[]): Promise<Set<string>> {
  const eligible = new Set<string>();
  if (tokenIds.length === 0) return eligible;

  // Gamma /markets endpoint supports multiple clob_token_ids via comma-separated param
  const url = new URL("https://gamma-api.polymarket.com/markets");
  // Batch in groups of 10 to avoid URL length limits
  for (let i = 0; i < tokenIds.length; i += 10) {
    const batch = tokenIds.slice(i, i + 10);
    url.searchParams.set("clob_token_ids", batch.join(","));
    try {
      const resp = await fetch(url, {
        headers: { accept: "application/json", "user-agent": "lottery-ticket/0.1" },
        signal: AbortSignal.timeout(8_000),
      });
      if (!resp.ok) continue;
      const markets = (await resp.json()) as any[];
      for (const m of markets) {
        const minSize = typeof m.rewardsMinSize === "number" ? m.rewardsMinSize : (typeof m.rewardsMinSize === "string" ? parseFloat(m.rewardsMinSize) || 0 : 0);
        const maxSpread = typeof m.rewardsMaxSpread === "number" ? m.rewardsMaxSpread : (typeof m.rewardsMaxSpread === "string" ? parseFloat(m.rewardsMaxSpread) || 0 : 0);
        if (minSize > 0 && maxSpread > 0) {
          // Find which tokenId this market corresponds to
          const tids: string[] = Array.isArray(m.clobTokenIds) ? m.clobTokenIds : (typeof m.clobTokenIds === "string" ? (() => { try { return JSON.parse(m.clobTokenIds); } catch { return []; } })() : []);
          for (const tid of tids) {
            if (batch.includes(tid)) eligible.add(tid);
          }
        }
      }
    } catch {
      // Gamma unavailable — no rewards info
    }
  }
  return eligible;
}

// ═══════════════════════════════════════════════════════════════
// Signal Generation
// ═══════════════════════════════════════════════════════════════

interface PriceCheck {
  bestAsk: number;
  spreadPct: number;
  askDepth: number;
}

async function checkLotteryPrices(
  tokenIds: string[],
): Promise<Map<string, PriceCheck>> {
  const results = new Map<string, PriceCheck>();

  for (let i = 0; i < tokenIds.length; i += 3) {
    const batch = tokenIds.slice(i, i + 3);
    const promises = batch.map(async (tid) => {
      try {
        const book = await fetchPolymarketBook(tid, 5_000);
        if (!book) return null;
        const q = quoteFromBook(book);
        return {
          tid,
          bestAsk: q.bestAsk,
          spreadPct: q.spreadPct ?? 100,
          askDepth: (q.askSize ?? 0) * (q.bestAsk ?? 0),
        };
      } catch {
        return null;
      }
    });

    const resolved = await Promise.all(promises);
    for (const r of resolved) {
      if (r && r.bestAsk !== undefined && r.bestAsk > 0) {
        results.set(r.tid, {
          bestAsk: r.bestAsk,
          spreadPct: r.spreadPct,
          askDepth: r.askDepth,
        });
      }
    }
  }

  return results;
}

/**
 * Generate lottery ticket signals for all qualifying markets.
 * Returns signals sorted by edge (best first).
 */
export async function generateLotterySignals(
  upProbability: number,
  config: LotteryTicketConfig = DEFAULT_LOTTERY_CONFIG,
): Promise<LotterySignal[]> {
  const markets = await discoverLotteryMarkets(30);
  if (markets.length === 0) return [];

  const tokenIds = markets.map((m) => m.tokenId);
  const prices = await checkLotteryPrices(tokenIds);

  // Fetch rewards eligibility from Gamma (non-blocking — proceed without on failure)
  const rewardsEligible = await fetchRewardsEligible(tokenIds);

  const signals: LotterySignal[] = [];

  for (const m of markets) {
    const q = prices.get(m.tokenId);
    if (!q) continue;

    // Filter: must be in lottery zone
    if (q.bestAsk > config.maxEntryPrice || q.bestAsk < config.minEntryPrice) continue;
    if (q.spreadPct > config.maxSpreadPct) continue;
    if (q.askDepth < config.minDepthUsd) continue;

    // Edge = estimated probability - market price
    const edge = upProbability - q.bestAsk;

    // Only enter if positive edge
    if (edge <= 0) continue;

    // Kelly sizing: f* = edge / (odds - 1), but for binary: f* = edge
    // We use a micro-fraction for safety
    const kellyFrac = config.kellyFraction;
    const betSize = Math.min(
      config.maxBetUsd,
      Math.max(config.minBetUsd, edge * kellyFrac * 100), // scale to reasonable size
    );

    const shares = Math.floor((betSize / q.bestAsk) * 100) / 100;
    if (shares < 0.1) continue; // Too small to execute

    const costUsd = Math.round(shares * q.bestAsk * 10000) / 10000;
    if (costUsd < config.minBetUsd) continue;

    // EV = P(win) * payout - cost = upProb * shares - cost
    const expectedValue = upProbability * shares - costUsd;

    const isRewardsEligible = rewardsEligible.has(m.tokenId);

    signals.push({
      tokenId: m.tokenId,
      marketTitle: m.title,
      estimatedProb: upProbability,
      marketPrice: q.bestAsk,
      edge,
      shares,
      costUsd,
      expectedValue,
      rewardsEligible: isRewardsEligible,
    });
  }

  // Sort by edge descending, with +50% boost for rewards-eligible markets
  return signals.sort((a, b) => {
    const aScore = a.edge * (a.rewardsEligible ? 1.5 : 1.0);
    const bScore = b.edge * (b.rewardsEligible ? 1.5 : 1.0);
    return bScore - aScore;
  });
}

// ═══════════════════════════════════════════════════════════════
// Simulation helpers
// ═══════════════════════════════════════════════════════════════

/**
 * Simulate resolution of a lottery position.
 * Uses the entry price as probability estimate for the outcome.
 * In production, this would query the actual Polymarket resolution.
 */
export function simulateResolution(
  position: LotteryPosition,
  resolutionProbability?: number,
): LotteryPosition {
  const winProb = resolutionProbability ?? position.entryPrice;
  const won = Math.random() < winProb;

  const payout = won ? position.shares * 1.0 : 0;
  const pnl = payout - position.costUsd;

  return {
    ...position,
    resolved: true,
    won,
    payout,
    pnl,
  };
}

/**
 * Format a lottery signal for display.
 */
export function formatSignal(signal: LotterySignal): string {
  const roi = signal.expectedValue > 0 
    ? ((1 / signal.marketPrice) - 1) * 100 
    : 0;
  return [
    `UP @ ${(signal.marketPrice * 100).toFixed(0)}¢`,
    `${signal.shares.toFixed(1)} shares`,
    `$${signal.costUsd.toFixed(2)} cost`,
    `${signal.edge.toFixed(1)}% edge`,
    `${roi.toFixed(0)}% ROI if win`,
  ].join(" | ");
}
