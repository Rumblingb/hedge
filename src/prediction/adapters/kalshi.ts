import type { PredictionMarketSnapshot } from "../types.js";

interface KalshiSeries {
  ticker?: string;
  title?: string;
  category?: string;
  frequency?: string;
}

interface KalshiMarket {
  ticker?: string;
  event_ticker?: string;
  series_ticker?: string;
  title?: string;
  subtitle?: string;
  yes_sub_title?: string;
  close_time?: string;
  expiration_time?: string;
  yes_bid_dollars?: string | number;
  yes_ask_dollars?: string | number;
  last_price_dollars?: string | number;
  liquidity_dollars?: string | number;
  volume_24h_fp?: string | number;
  open_interest?: string | number;
  rules_primary?: string;
  rules_secondary?: string;
}

const KALSHI_BASE_URL = "https://api.elections.kalshi.com/trade-api/v2";
const SERIES_CATEGORY_PRIORITY = ["Financials", "Economics", "Crypto", "Companies", "Elections", "Politics", "World"] as const;
const SERIES_CATEGORY_SET = new Set<string>(SERIES_CATEGORY_PRIORITY);

function toNumber(value: unknown): number | undefined {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string") {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : undefined;
  }
  return undefined;
}

function isComparableQuestion(title?: string): boolean {
  if (!title) return false;
  const trimmed = title.trim();
  if (!trimmed) return false;
  if (trimmed.length > 140) return false;
  if (trimmed.includes(",")) return false;
  return true;
}

function categoryRank(category?: string): number {
  const index = category ? SERIES_CATEGORY_PRIORITY.indexOf(category as (typeof SERIES_CATEGORY_PRIORITY)[number]) : -1;
  return index >= 0 ? index : 99;
}

function isPreferredSeries(series: KalshiSeries): boolean {
  return Boolean(series.ticker) && Boolean(series.title) && Boolean(series.category && SERIES_CATEGORY_SET.has(series.category));
}

function isComboLike(market: KalshiMarket): boolean {
  const ticker = market.ticker ?? "";
  const title = (market.title ?? market.subtitle ?? "").trim();
  return ticker.startsWith("KXMVE") || title.includes(",");
}

function comparablePrice(market: KalshiMarket): number | undefined {
  const last = toNumber(market.last_price_dollars);
  if (last !== undefined && last > 0 && last < 1) return last;
  const yesBid = toNumber(market.yes_bid_dollars);
  const yesAsk = toNumber(market.yes_ask_dollars);
  if (yesBid !== undefined && yesAsk !== undefined && yesBid > 0 && yesAsk < 1 && yesBid <= yesAsk) {
    return Number((((yesBid + yesAsk) / 2)).toFixed(4));
  }
  if (yesBid !== undefined && yesBid > 0 && yesBid < 1) return yesBid;
  return undefined;
}

function comparableSize(market: KalshiMarket): number {
  return Math.max(
    toNumber(market.volume_24h_fp) ?? 0,
    toNumber(market.liquidity_dollars) ?? 0,
    toNumber(market.open_interest) ?? 0
  );
}

function toSnapshot(market: KalshiMarket): PredictionMarketSnapshot | null {
  if (isComboLike(market)) return null;
  const title = market.title ?? market.subtitle;
  if (!isComparableQuestion(title)) return null;
  const price = comparablePrice(market);
  if (price === undefined) return null;

  return {
    venue: "kalshi",
    externalId: market.ticker ?? market.event_ticker ?? "unknown-market",
    eventTitle: title ?? market.event_ticker ?? "unknown-event",
    marketQuestion: title ?? market.event_ticker ?? "unknown-question",
    outcomeLabel: market.yes_sub_title ?? "Yes",
    side: "yes",
    expiry: market.expiration_time ?? market.close_time,
    settlementText: [market.rules_primary, market.rules_secondary].filter(Boolean).join("\n\n") || title,
    price,
    displayedSize: comparableSize(market)
  };
}

async function fetchJson<T>(url: URL): Promise<T> {
  const response = await fetch(url, {
    headers: {
      accept: "application/json",
      "user-agent": "rumbling-hedge/0.1"
    },
    signal: AbortSignal.timeout(10_000)
  });

  if (!response.ok) {
    throw new Error(`Kalshi fetch failed: ${response.status} ${response.statusText}`);
  }

  return response.json() as Promise<T>;
}

async function fetchKalshiSeries(limit: number): Promise<KalshiSeries[]> {
  const url = new URL(`${KALSHI_BASE_URL}/series`);
  url.searchParams.set("limit", String(Math.max(limit, 25)));
  try {
    const payload = await fetchJson<{ series?: KalshiSeries[] }>(url);
    return (payload.series ?? [])
      .filter(isPreferredSeries)
      .sort((left, right) => categoryRank(left.category) - categoryRank(right.category) || (left.title ?? "").localeCompare(right.title ?? ""));
  } catch {
    return [];
  }
}

async function fetchKalshiSeriesMarkets(seriesTicker: string): Promise<KalshiMarket[]> {
  const url = new URL(`${KALSHI_BASE_URL}/markets`);
  url.searchParams.set("status", "open");
  url.searchParams.set("series_ticker", seriesTicker);
  url.searchParams.set("limit", "50");
  const payload = await fetchJson<{ markets?: KalshiMarket[] }>(url);
  return payload.markets ?? [];
}

async function fetchKalshiFallbackMarkets(limit: number): Promise<KalshiMarket[]> {
  const url = new URL(`${KALSHI_BASE_URL}/markets`);
  url.searchParams.set("status", "open");
  url.searchParams.set("limit", String(Math.max(limit * 12, 250)));
  try {
    const payload = await fetchJson<{ markets?: KalshiMarket[] }>(url);
    return payload.markets ?? [];
  } catch {
    return [];
  }
}

export async function fetchKalshiLiveSnapshot(limit = 25): Promise<PredictionMarketSnapshot[]> {
  const snapshots: PredictionMarketSnapshot[] = [];
  const seen = new Set<string>();
  const series = await fetchKalshiSeries(Math.max(limit * 2, 18));

  for (const entry of series) {
    if (snapshots.length >= limit) break;
    let markets: KalshiMarket[] = [];
    try {
      markets = await fetchKalshiSeriesMarkets(entry.ticker!);
    } catch {
      continue;
    }
    for (const market of markets) {
      const snapshot = toSnapshot(market);
      if (!snapshot || seen.has(snapshot.externalId)) continue;
      seen.add(snapshot.externalId);
      snapshots.push(snapshot);
      if (snapshots.length >= limit) break;
    }
  }

  if (snapshots.length < limit) {
    const fallbackMarkets = await fetchKalshiFallbackMarkets(limit);
    for (const market of fallbackMarkets) {
      const snapshot = toSnapshot(market);
      if (!snapshot || seen.has(snapshot.externalId)) continue;
      seen.add(snapshot.externalId);
      snapshots.push(snapshot);
      if (snapshots.length >= limit) break;
    }
  }

  return snapshots.slice(0, limit);
}
