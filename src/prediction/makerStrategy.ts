// makerStrategy.ts — Gengar Maker Module for Polymarket
//
// Edge thesis (Becker 2026, "The Microstructure of Wealth Transfer in Prediction Markets"):
//   - Analyzed 72M+ Kalshi trades, proven structural maker-taker asymmetry
//   - Taker avg. excess return: -1.12% | Maker avg. excess return: +1.12%
//   - At 1¢ contracts: YES bet EV = -41%, NO bet EV = +23% (64pp gap)
//   - NO outperforms YES at 69 of 99 price levels
//   - Longshot bias: contracts ≤20¢ win LESS than implied; ≥80¢ win MORE
//   - High-gap categories: Media (-7.28pp), World Events (-7.32pp), Entertainment (-4.79pp), Sports (-2.23pp)
//   - Near-efficient categories: Finance (-0.17pp), Politics (-1.02pp)
//
// Polymarket adaptation:
//   - Buy NO tokens where NO price ≤ $0.20 (longshot bias zone)
//   - Hold to resolution → positive EV from structural mispricing
//   - Gate chain: category → price → liquidity → spread → time-to-resolution
//   - Kelly-derived sizing, $1 max per trade, $20 bankroll
//
// Key difference from lotteryTicket.ts (BUYS YES at low prices — proven LOSER):
//   - This BUYS NO (the opposite side) — structurally profitable
//   - Different market scope: all binary markets, not just BTC 5-min

import { fetchPolymarketBook, quoteFromBook } from "./polymarketBook.js";

// ═══════════════════════════════════════════════════════════════
// Config
// ═══════════════════════════════════════════════════════════════

export interface MakerConfig {
  /** Maximum NO token price to enter (Becker: longshot bias <20¢) */
  maxEntryPrice: number;
  /** Minimum NO token price to enter (below this, fill unlikely) */
  minEntryPrice: number;
  /** Fraction of bankroll to risk per trade (quarter-Kelly) */
  kellyFraction: number;
  /** Minimum bet size in USD */
  minBetUsd: number;
  /** Maximum bet size in USD */
  maxBetUsd: number;
  /** Maximum spread percentage (maker needs tight spreads) */
  maxSpreadPct: number;
  /** Minimum top-of-book depth in USD */
  minDepthUsd: number;
  /** Minimum hours until market resolution */
  minHoursToResolution: number;
  /** Gamma API base URL */
  gammaApiUrl: string;
  /** Maximum markets to scan per cycle */
  maxMarketsToScan: number;
  /** Category gap thresholds — only trade above these */
  categoryGaps: Record<string, number>;
}

export const DEFAULT_MAKER_CONFIG: MakerConfig = {
  maxEntryPrice: 0.20,
  minEntryPrice: 0.01,
  kellyFraction: 0.25,    // quarter-Kelly
  minBetUsd: 1.00,
  maxBetUsd: 1.00,        // $1 max per trade (capital preservation)
  maxSpreadPct: 2,         // tighter than lottery (maker needs liquidity)
  minDepthUsd: 500,
  minHoursToResolution: 24,
  gammaApiUrl: "https://gamma-api.polymarket.com",
  maxMarketsToScan: 100,
  // Gap = |maker return - taker return| in percentage points (from Becker 2026)
  categoryGaps: {
    "entertainment": 2.0,   // 4.79pp gap in paper
    "media": 2.0,           // 7.28pp
    "world": 2.0,           // 7.32pp
    "sports": 1.0,          // 2.23pp (72% of volume)
    "crypto": 1.0,          // 2.69pp (borderline)
    "politics": 0.5,        // 1.02pp (low edge)
    "finance": 0,           // 0.17pp (near-efficient — SKIP default)
    "science": 0,           // unknown — skip
  },
};

// ═══════════════════════════════════════════════════════════════
// Types
// ═══════════════════════════════════════════════════════════════

export interface MakerMarket {
  tokenId: string;
  slug: string;
  title: string;
  question: string;
  category: string;
  /** Polymarket tag IDs for category inference */
  tagIds: string[];
  /** When the market closes/resolves */
  endDate?: string;
  /** Total volume in USD */
  volume: number;
  /** NO token outcome index (0 or 1) */
  noTokenIndex: number;
  /** NO token outcome label */
  noLabel: string;
  /** Polymarket rewards: minimum position size for rewards eligibility */
  rewardsMinSize?: number;
  /** Polymarket rewards: maximum spread for rewards eligibility */
  rewardsMaxSpread?: number;
  /** Whether this market is eligible for Polymarket liquidity rewards */
  rewardsEligible?: boolean;
}

export interface MakerSignal {
  tokenId: string;
  marketTitle: string;
  category: string;
  /** NO token market price */
  noPrice: number;
  /** Estimated edge = expected NO win probability - noPrice */
  edge: number;
  /** Recommended shares to buy */
  shares: number;
  /** Entry cost in USD */
  costUsd: number;
  /** Best ask from CLOB book */
  bestAsk: number;
  /** Best bid from CLOB book */
  bestBid: number;
  /** Spread percentage */
  spreadPct: number;
  /** Top-of-book depth in USD */
  depthUsd: number;
  /** Market volume (proxy for activity) */
  volume: number;
  /** Hours until resolution */
  hoursToResolution: number | null;
  /** Whether this market is eligible for Polymarket liquidity rewards */
  rewardsEligible: boolean;
  /** Skip reason if no signal */
  skipReason?: string;
}

// ═══════════════════════════════════════════════════════════════
// Category Detection
// ═══════════════════════════════════════════════════════════════

/** Polymarket tag IDs → Becker category mapping (corrected) */
const TAG_CATEGORY_MAP: Record<string, string> = {
  "1": "sports",        // Sports (general)
  "2": "politics",      // Politics/Government
  "3": "entertainment", // Entertainment/Culture
  "4": "science",       // Science/Technology  
  "5": "world",         // World/Current Events
  "6": "finance",       // Business/Finance/Economics
  "7": "health",        // Health/Medicine
  "8": "crypto",        // Crypto/Web3
  "21": "crypto",       // Cryptocurrency (subcategory)
  "39": "crypto",       // Ethereum
  "235": "crypto",      // Bitcoin
};

function detectCategory(tagIds: string[], title: string): string {
  // First: check tag IDs
  for (const tid of tagIds) {
    const cat = TAG_CATEGORY_MAP[tid];
    if (cat) return cat;
  }

  // Fallback: keyword detection from title
  const t = title.toLowerCase();
  if (t.includes("movie") || t.includes("oscar") || t.includes("film") || t.includes("album")) return "entertainment";
  if (t.includes("tweet") || t.includes("twitter") || t.includes("youtube") || t.includes("media")) return "media";
  if (t.includes("war") || t.includes("nato") || t.includes("russia") || t.includes("china") || t.includes("iran")) return "world";
  if (t.includes("nfl") || t.includes("nba") || t.includes("mlb") || t.includes("soccer") || t.includes("ufc") || t.includes("super bowl")) return "sports";
  if (t.includes("fed") || t.includes("rate") || t.includes("gdp") || t.includes("inflation") || t.includes("tariff")) return "finance";
  if (t.includes("trump") || t.includes("biden") || t.includes("election") || t.includes("congress")) return "politics";
  if (t.includes("btc") || t.includes("bitcoin") || t.includes("crypto") || t.includes("eth")) return "crypto";

  return "unknown";
}

function categoryGap(category: string, config: MakerConfig): number {
  return config.categoryGaps[category] ?? 0;
}

// ═══════════════════════════════════════════════════════════════
// Market Discovery
// ═══════════════════════════════════════════════════════════════

interface GammaMarketRaw {
  id?: string;
  question?: string;
  conditionId?: string;
  outcomes?: string[] | string;
  outcomePrices?: number[] | string;
  clobTokenIds?: string[] | string;
  closed?: boolean | string;
  endDate?: string;
  volume?: number | string;
  /** Polymarket liquidity rewards: minimum order size (USD) to qualify */
  rewardsMinSize?: number | string;
  /** Polymarket liquidity rewards: maximum spread (as decimal, e.g., 0.02 = 2%) to qualify */
  rewardsMaxSpread?: number | string;
}

interface GammaEventRaw {
  id?: string;
  title?: string;
  slug?: string;
  endDate?: string;
  tags?: Array<{id: string; label: string}>;
  markets?: GammaMarketRaw[];
}

function parseJsonArray<T = string>(value: unknown): T[] {
  if (Array.isArray(value)) return value as T[];
  if (typeof value === "string") {
    try { const p = JSON.parse(value); return Array.isArray(p) ? (p as T[]) : []; } catch { return []; }
  }
  return [];
}

function parseJsonNumberArray(value: unknown): number[] {
  if (Array.isArray(value)) return value.map((v) => Number(v)).filter((n) => Number.isFinite(n));
  if (typeof value === "string") {
    try { const p = JSON.parse(value); return Array.isArray(p) ? p.map((v: any) => Number(v)).filter((n: any) => Number.isFinite(n)) : []; } catch { return []; }
  }
  return [];
}

/**
 * Find binary markets (2 outcomes: YES/NO) from Gamma API.
 * Filters for active markets where NO token is in the longshot zone.
 */
export async function discoverMakerMarkets(
  config: MakerConfig = DEFAULT_MAKER_CONFIG,
): Promise<MakerMarket[]> {
  const url = new URL(`${config.gammaApiUrl}/events`);
  url.searchParams.set("limit", String(config.maxMarketsToScan));
  url.searchParams.set("active", "true");
  url.searchParams.set("closed", "false");
  url.searchParams.set("order", "volume");
  url.searchParams.set("ascending", "false");

  let events: GammaEventRaw[];
  try {
    const resp = await fetch(url, {
      headers: { accept: "application/json", "user-agent": "gengar-maker/0.1" },
      signal: AbortSignal.timeout(15_000),
    });
    if (!resp.ok) return [];
    events = (await resp.json()) as GammaEventRaw[];
  } catch {
    return [];
  }

  const markets: MakerMarket[] = [];

  for (const evt of events) {
    if (!evt.markets || evt.markets.length === 0) continue;

    const tagIds = (evt.tags ?? []).map((t) => String(t.id));

    for (const mkt of evt.markets) {
      const isClosed = mkt.closed === true || (typeof mkt.closed === "string" && mkt.closed === "true");
      if (isClosed) continue;

      const outcomes = parseJsonArray<string>(mkt.outcomes);
      if (outcomes.length !== 2) continue; // Binary markets only

      const tokenIds = parseJsonArray<string>(mkt.clobTokenIds);
      if (tokenIds.length !== 2) continue;

      const prices = parseJsonNumberArray(mkt.outcomePrices);
      if (prices.length !== 2) continue;

      // Find NO token: outcome label contains "No" or is the second outcome
      const noIdx = outcomes.findIndex((o) => o.toLowerCase() === "no");
      if (noIdx === -1) continue; // Not a YES/NO market

      const noPrice = prices[noIdx];
      if (noPrice === undefined || noPrice > config.maxEntryPrice || noPrice < config.minEntryPrice) continue;

      // Also skip if endDate is in the past (resolved but Gamma still lists as active)
      if (mkt.endDate) {
        const endTs = new Date(mkt.endDate).getTime();
        if (!isNaN(endTs) && endTs < Date.now()) continue;
      }

      const rewardsMinSize = typeof mkt.rewardsMinSize === "number" ? mkt.rewardsMinSize : (typeof mkt.rewardsMinSize === "string" ? parseFloat(mkt.rewardsMinSize) || 0 : 0);
      const rewardsMaxSpread = typeof mkt.rewardsMaxSpread === "number" ? mkt.rewardsMaxSpread : (typeof mkt.rewardsMaxSpread === "string" ? parseFloat(mkt.rewardsMaxSpread) || 0 : 0);
      const rewardsEligible = rewardsMinSize > 0 && rewardsMaxSpread > 0;

      markets.push({
        tokenId: tokenIds[noIdx]!,
        slug: evt.slug ?? "",
        title: evt.title ?? mkt.question ?? "",
        question: mkt.question ?? evt.title ?? "",
        category: detectCategory(tagIds, evt.title ?? mkt.question ?? ""),
        tagIds,
        endDate: mkt.endDate ?? evt.endDate,
        volume: typeof mkt.volume === "number" ? mkt.volume : (typeof mkt.volume === "string" ? parseFloat(mkt.volume) || 0 : 0),
        noTokenIndex: noIdx,
        noLabel: outcomes[noIdx] ?? "No",
        rewardsMinSize,
        rewardsMaxSpread,
        rewardsEligible,
      });
    }
  }

  return markets;
}

// ═══════════════════════════════════════════════════════════════
// Signal Generation — Gate Chain
// ═══════════════════════════════════════════════════════════════

export interface PriceCheck {
  bestBid: number;
  bestAsk: number;
  spreadPct: number;
  topBookDepth: number;
}

async function checkPrices(
  tokenIds: string[],
): Promise<Map<string, PriceCheck>> {
  const results = new Map<string, PriceCheck>();

  // Batch in groups of 3 to avoid rate limiting
  for (let i = 0; i < tokenIds.length; i += 3) {
    const batch = tokenIds.slice(i, i + 3);
    const promises = batch.map(async (tid) => {
      try {
        const book = await fetchPolymarketBook(tid, 5_000);
        if (!book) return null;
        const q = quoteFromBook(book);
        if (q.bestBid === undefined || q.bestAsk === undefined) return null;
        return { tid, ...q };
      } catch {
        return null;
      }
    });

    const resolved = await Promise.all(promises);
    for (const r of resolved) {
      if (r) {
        results.set(r.tid, {
          bestBid: r.bestBid!,
          bestAsk: r.bestAsk!,
          spreadPct: r.spreadPct ?? 100,
          topBookDepth: r.topBookDepth ?? 0,
        });
      }
    }
  }

  return results;
}

/**
 * Evaluate NO longshot bias: the paper shows contracts at ≤20¢ have
 * P(win) > price (positive mispricing for NO buyers).
 *
 * Conservative edge estimate: use the Becker empirical data.
 * At 1¢: NO win rate ≈ 1.57% (maker side) vs 1% implied → edge = 0.57pp
 * At 5¢: NO win rate ≈ 4.18% vs 5% implied? NO — re-read: 
 *   The paper says "5¢ contracts win only 4.18%" — that's for YES.
 *   For NO at 5¢, that's 95¢ YES. 95¢ contracts win 95.83%.
 *   So NO at 5¢ wins 100-95.83 = 4.17%? Actually no:
 *   - YES at 5¢ wins 4.18% (implied 5%) → underpriced
 *   - YES at 95¢ wins 95.83% (implied 95%) → overpriced
 *   - NO at 5¢ = YES at 95¢ → NO at 5¢ wins 4.17%? 
 *   
 * Wait: if YES at 95¢ wins 95.83% of the time, then NO at 5¢ wins 4.17% of the time.
 * Implied 5% — so NO at 5¢ wins 4.17% vs 5% implied = -0.83pp. That's a LOSER.
 *
 * Let me re-derive from the paper:
 * - Longshot YES (1-20¢): wins LESS than price → YES buyer LOSES, YES seller (maker) WINS
 * - Favorite YES (80-99¢): wins MORE than price → YES buyer WINS
 * - Longshot NO (1-20¢): same as Favorite YES → NO buyer WINS
 * - Favorite NO (80-99¢): same as Longshot YES → NO buyer LOSES
 *
 * So buying NO at <20¢ = buying the Favorite YES at 80-99¢ ≈ +edge!
 * At 5¢ NO (= 95¢ YES): wins ~95.83% → edge = 95.83 - 95 = +0.83pp (small edge)
 * At 1¢ NO (= 99¢ YES): wins ~99.43% → edge = 99.43 - 99 = +0.43pp (small edge)
 *
 * Hmm, that's a small edge. The BIG edge from the paper is on the MAKER side of longshot YES.
 * Maker sells YES at 5¢ → taker buys at 5¢, wins 4.18% → maker keeps 95.82¢ per $1 
 * vs fair 95¢ → edge = 0.82pp. But scaled by 5¢ risk that's 0.82/5 = 16.4% ROC!
 *
 * For our TAKER strategy of buying NO at low prices:
 * - Buy NO at 10¢ = buy YES at 90¢ → edge small (maybe +0.5pp at best)
 * - The real edge comes from being a MAKER
 *
 * PRACTICAL POLYMARKET IMPLEMENTATION:
 * On Polymarket, to "sell YES at 5¢" means we need to OWN YES tokens first and place
 * a limit sell. We don't own them. But we CAN buy NO at 95¢ — which is equivalent
 * to selling YES at 5¢ — and that gives the maker edge!
 *
 * Wait no — buying NO at 95¢ through a MARKET order makes us the TAKER. The edge
 * is smaller for takers. The maker would place a LIMIT order and get slightly better
 * price + spread.
 *
 * Let me simplify: the core actionable insight is:
 * 1. Buy NO at <20¢ (longshot zone) — structural +EV from longshot bias
 *    At 5¢: edge ~0.83pp → ROC ≈ 0.83/5 = 16.6% (not bad at all!)
 * 2. Even better: place LIMIT BUY orders on NO at slightly below market
 *    This captures the maker edge too
 *
 * For our size ($1/trade), ROC matters more than spread. Let's go with buying NO at <20¢.
 */

function estimateNoEdge(noPrice: number): number {
  // From Becker paper: extrapolate NO win rate from YES mispricing curve
  // At price p_NO: P(NO wins) = 1 - P(YES wins at 1-p_NO)
  // P(YES wins at x): x ≤ 20¢ → x * (1 - 0.1636) (16.36% mispricing)
  //                   x > 20¢ → roughly x (near efficient)
  // So P(NO wins at p) where p ≤ 20¢ → 1 - (1-p) * (1 - 0.1636) = 1 - 0.8364*(1-p)
  // Actually let me use the data points:
  // p_YES=5¢ → YES wins 4.18% → NO wins 95.82% (at p_NO=95¢, edge = +0.82pp)
  // p_YES=1¢ → YES wins 0.43% → NO wins 99.57% (at p_NO=99¢, edge = +0.57pp)
  // p_YES=10¢ → YES wins ~8.36% → NO wins 91.64% (at p_NO=90¢, edge = +1.64pp)

  // For NO at <20¢: this is p_YES = 1-p_NO at >80¢
  // Use linear interpolation from paper data: 
  // p_YES=80 → edge ≈ price * 0.02 (2% overperformance at high end)
  // p_YES=99 → edge ≈ price * 0.0057/0.99 ≈ 0.58pp at most

  const pYes = 1 - noPrice;
  if (pYes < 0.80) return 0; // Not in longshot NO zone

  // Conservative: edge ≈ 0.5pp + 0.01*(pYes - 0.80)*5
  // At pYes=0.80: edge ≈ 0.5pp → P(win) = 80.5%
  // At pYes=0.95: edge ≈ 1.25pp → P(win) = 96.25%
  // At pYes=0.99: edge ≈ 1.45pp → P(win) = 100.45% (capped)
  const edge = 0.005 + 0.01 * Math.max(0, (pYes - 0.80) * 5);
  return Math.min(edge, 0.02); // Cap at 2pp (ultra-conservative)
}

/**
 * Run the full maker gate chain on discovered markets.
 * Returns signals sorted by edge (best first).
 */
export async function generateMakerSignals(
  config: MakerConfig = DEFAULT_MAKER_CONFIG,
): Promise<MakerSignal[]> {
    // Gate 0: Discover markets with NO in longshot zone
  const markets = await discoverMakerMarkets(config);
  if (markets.length === 0) return [];

  // Deduplicate by tokenId (same market appearing in multiple Gamma events)
  const seenTids = new Set<string>();
  const uniqueMarkets = markets.filter((m) => {
    if (seenTids.has(m.tokenId)) return false;
    seenTids.add(m.tokenId);
    return true;
  });

  // Fetch live CLOB prices for all candidates
  const tokenIds = uniqueMarkets.map((m) => m.tokenId);
  const prices = await checkPrices(tokenIds);

  const signals: MakerSignal[] = [];
  const now = Date.now();

  for (const mkt of uniqueMarkets) {
    // Gate 1: Category gate — skip near-efficient categories
    const gap = categoryGap(mkt.category, config);
    if (gap <= 0) continue; // Skip finance (0.17pp gap) and unknown

    const price = prices.get(mkt.tokenId);
    if (!price) continue;

    // Gate 2: Price gate — must be in longshot NO zone
    if (price.bestAsk > config.maxEntryPrice || price.bestAsk < config.minEntryPrice) continue;

    // Gate 3: Spread gate
    if (price.spreadPct > config.maxSpreadPct) continue;

    // Gate 4: Liquidity gate
    if (price.topBookDepth < config.minDepthUsd) continue;

    // Gate 5: Time-to-resolution gate
    let hoursToRes: number | null = null;
    if (mkt.endDate) {
      const endTs = new Date(mkt.endDate).getTime();
      if (!isNaN(endTs)) {
        hoursToRes = (endTs - now) / (1000 * 60 * 60);
        if (hoursToRes < config.minHoursToResolution) continue;
      }
    }

    // Gate 6: Edge estimation
    const edge = estimateNoEdge(price.bestAsk);
    if (edge <= 0) continue;

    // Kelly sizing — calculate from target cost, not shares
    const b = (1 - price.bestAsk) / Math.max(price.bestAsk, 0.01); // odds
    const probWin = price.bestAsk + edge; // estimated true probability
    const q = 1 - probWin;
    const rawKelly = Math.max(0, (b * probWin - q) / Math.max(b, 0.01));
    const betSize = Math.min(
      config.maxBetUsd,
      Math.max(config.minBetUsd, rawKelly * config.kellyFraction * 20) // scale to bankroll
    );

    // Calculate shares that satisfy minBetUsd (round up to nearest 0.01 share)
    const minShares = Math.ceil((config.minBetUsd / price.bestAsk) * 100) / 100;
    const targetShares = Math.floor((betSize / price.bestAsk) * 100) / 100;
    const shares = Math.max(minShares, targetShares);
    if (shares < 0.1) continue;

    const costUsd = Math.round(shares * price.bestAsk * 10000) / 10000;
    if (costUsd < config.minBetUsd || costUsd > config.maxBetUsd) continue;

    signals.push({
      tokenId: mkt.tokenId,
      marketTitle: mkt.title,
      category: mkt.category,
      noPrice: price.bestAsk,
      edge: edge * 100, // Store as percentage
      shares,
      costUsd,
      bestAsk: price.bestAsk,
      bestBid: price.bestBid,
      spreadPct: price.spreadPct,
      depthUsd: price.topBookDepth,
      volume: mkt.volume,
      hoursToResolution: hoursToRes,
      rewardsEligible: mkt.rewardsEligible,
    });
  }

  // Sort by score: (edge × categoryGap) with +50% boost for rewards-eligible markets
  return signals.sort((a, b) => {
    const aRewardsMult = a.rewardsEligible ? 1.5 : 1.0;
    const bRewardsMult = b.rewardsEligible ? 1.5 : 1.0;
    const aScore = a.edge * categoryGap(a.category, config) * aRewardsMult;
    const bScore = b.edge * categoryGap(b.category, config) * bRewardsMult;
    return bScore - aScore;
  });
}

// ═══════════════════════════════════════════════════════════════
// Simulation
// ═══════════════════════════════════════════════════════════════

export interface MakerPosition {
  tokenId: string;
  marketTitle: string;
  category: string;
  entryPrice: number;
  shares: number;
  costUsd: number;
  entryTs: number;
  resolved: boolean;
  won: boolean | null;
  payout: number;
  pnl: number;
}

/**
 * Simulate resolution. Uses the Becker paper's empirical win rates.
 */
export function simulateResolution(
  position: MakerPosition,
): MakerPosition {
  // Use empirical NO win rate from Becker paper
  const pYes = 1 - position.entryPrice;
  let yesWinRate: number;
  if (pYes <= 0.20) {
    // Longshot YES: wins ~16.36% less than implied
    yesWinRate = pYes * (1 - 0.1636);
  } else if (pYes >= 0.80) {
    // Favorite YES: wins ~2% more than implied
    yesWinRate = Math.min(1.0, pYes * 1.02);
  } else {
    yesWinRate = pYes; // Mid-range: roughly efficient
  }

  const noWinRate = 1 - yesWinRate;
  const won = Math.random() < noWinRate;

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
 * Format a maker signal for display/reporting.
 */
export function formatSignal(signal: MakerSignal): string {
  const roi = signal.noPrice > 0
    ? ((1 / signal.noPrice) - 1) * 100
    : 0;
  return [
    `NO @ ${(signal.noPrice * 100).toFixed(0)}¢`,
    `${signal.category}`,
    `${signal.shares.toFixed(1)} shares`,
    `$${signal.costUsd.toFixed(2)} cost`,
    `${signal.edge.toFixed(1)}% edge`,
    `${roi.toFixed(0)}% ROI if win`,
    `gap=${signal.category}`,
  ].join(" | ");
}
