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
const SERIES_CATEGORY_PRIORITY = ["Financials", "Economics", "Crypto", "Companies", "Elections", "Politics", "World", "Sports", "Technology", "Entertainment"] as const;
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

function logAdapterWarning(stage: string, error: unknown): void {
  const message = error instanceof Error ? error.message : String(error);
  console.error(`[kalshi-adapter] ${stage} failed: ${message}`);
}

async function fetchKalshiSeries(limit: number): Promise<KalshiSeries[]> {
  const url = new URL(`${KALSHI_BASE_URL}/series`);
  url.searchParams.set("limit", String(Math.max(limit, 25)));
  try {
    const payload = await fetchJson<{ series?: KalshiSeries[] }>(url);
    return (payload.series ?? [])
      .filter(isPreferredSeries)
      .sort((left, right) => categoryRank(left.category) - categoryRank(right.category) || (left.title ?? "").localeCompare(right.title ?? ""));
  } catch (error) {
    logAdapterWarning("series-index", error);
    return [];
  }
}

async function fetchKalshiSeriesMarkets(seriesTicker: string): Promise<KalshiMarket[]> {
  const url = new URL(`${KALSHI_BASE_URL}/markets`);
  url.searchParams.set("status", "open");
  url.searchParams.set("series_ticker", seriesTicker);
  url.searchParams.set("limit", "50");
  const payload = await fetchJson<{ markets?: KalshiMarket[] }>(url);
  return (payload.markets ?? []).sort((left, right) => comparableSize(right) - comparableSize(left));
}

async function fetchKalshiFallbackMarkets(limit: number): Promise<KalshiMarket[]> {
  const url = new URL(`${KALSHI_BASE_URL}/markets`);
  url.searchParams.set("status", "open");
  url.searchParams.set("limit", String(Math.max(limit * 20, 500)));
  try {
    const payload = await fetchJson<{ markets?: KalshiMarket[] }>(url);
    return (payload.markets ?? []).sort((left, right) => comparableSize(right) - comparableSize(left));
  } catch (error) {
    logAdapterWarning("markets-fallback", error);
    return [];
  }
}

export interface KalshiAdapterDiagnostics {
  seriesConsidered: number;
  seriesFetchErrors: number;
  marketsInspected: number;
  marketsRejectedCombo: number;
  marketsRejectedNonComparableTitle: number;
  marketsRejectedNoPrice: number;
  marketsAccepted: number;
  fallbackUsed: boolean;
}

export async function fetchKalshiLiveSnapshotWithDiagnostics(
  limit = 25
): Promise<{ snapshots: PredictionMarketSnapshot[]; diagnostics: KalshiAdapterDiagnostics }> {
  const snapshots: PredictionMarketSnapshot[] = [];
  const seen = new Set<string>();
  const diagnostics: KalshiAdapterDiagnostics = {
    seriesConsidered: 0,
    seriesFetchErrors: 0,
    marketsInspected: 0,
    marketsRejectedCombo: 0,
    marketsRejectedNonComparableTitle: 0,
    marketsRejectedNoPrice: 0,
    marketsAccepted: 0,
    fallbackUsed: false
  };
  const allowlist = (process.env.BILL_PREDICTION_KALSHI_SERIES_ALLOWLIST ?? "")
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
  const series = (await fetchKalshiSeries(Math.max(limit * 2, 18)))
    .filter((entry) => allowlist.length === 0 || allowlist.includes(entry.ticker ?? ""));
  diagnostics.seriesConsidered = series.length;

  const tryAccept = (market: KalshiMarket): void => {
    diagnostics.marketsInspected += 1;
    if (isComboLike(market)) {
      diagnostics.marketsRejectedCombo += 1;
      return;
    }
    const title = market.title ?? market.subtitle;
    if (!isComparableQuestion(title)) {
      diagnostics.marketsRejectedNonComparableTitle += 1;
      return;
    }
    const snapshot = toSnapshot(market);
    if (!snapshot) {
      diagnostics.marketsRejectedNoPrice += 1;
      return;
    }
    if (seen.has(snapshot.externalId)) return;
    seen.add(snapshot.externalId);
    snapshots.push(snapshot);
    diagnostics.marketsAccepted += 1;
  };

  const pacingMs = Number.parseInt(process.env.BILL_PREDICTION_KALSHI_PACING_MS ?? "150", 10);
  let firstRequest = true;
  for (const entry of series) {
    if (snapshots.length >= limit) break;
    if (!firstRequest && pacingMs > 0) {
      await new Promise((r) => setTimeout(r, pacingMs));
    }
    firstRequest = false;
    let markets: KalshiMarket[] = [];
    try {
      markets = await fetchKalshiSeriesMarkets(entry.ticker!);
    } catch (error) {
      diagnostics.seriesFetchErrors += 1;
      logAdapterWarning(`series-markets:${entry.ticker}`, error);
      continue;
    }
    for (const market of markets) {
      if (snapshots.length >= limit) break;
      tryAccept(market);
    }
  }

  if (snapshots.length < limit) {
    diagnostics.fallbackUsed = true;
    const fallbackMarkets = await fetchKalshiFallbackMarkets(limit);
    for (const market of fallbackMarkets) {
      if (snapshots.length >= limit) break;
      tryAccept(market);
    }
  }

  if (snapshots.length === 0) {
    console.error(
      `[kalshi-adapter] produced 0 snapshots diagnostics=${JSON.stringify(diagnostics)}. ` +
        `Likely causes: API unreachable, all open markets untraded, or filter too strict.`
    );
  }

  return { snapshots: snapshots.slice(0, limit), diagnostics };
}

export async function fetchKalshiLiveSnapshot(limit = 25): Promise<PredictionMarketSnapshot[]> {
  const { snapshots } = await fetchKalshiLiveSnapshotWithDiagnostics(limit);
  return snapshots;
}
