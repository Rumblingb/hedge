import type { PredictionMarketSnapshot } from "../types.js";

interface KalshiMarket {
  ticker?: string;
  event_ticker?: string;
  title?: string;
  subtitle?: string;
  yes_sub_title?: string;
  close_time?: string;
  expiration_time?: string;
  yes_bid_dollars?: string | number;
  last_price_dollars?: string | number;
  liquidity_dollars?: string | number;
  volume_24h_fp?: string | number;
  rules_primary?: string;
  rules_secondary?: string;
}

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

export async function fetchKalshiLiveSnapshot(limit = 25): Promise<PredictionMarketSnapshot[]> {
  const url = new URL("https://api.elections.kalshi.com/trade-api/v2/markets");
  url.searchParams.set("status", "open");
  url.searchParams.set("limit", String(Math.max(limit * 10, 200)));

  const response = await fetch(url, {
    headers: {
      accept: "application/json",
      "user-agent": "rumbling-hedge/0.1"
    }
  });

  if (!response.ok) {
    throw new Error(`Kalshi market fetch failed: ${response.status} ${response.statusText}`);
  }

  const payload = (await response.json()) as { markets?: KalshiMarket[] };
  const snapshots: PredictionMarketSnapshot[] = [];

  for (const market of payload.markets ?? []) {
    if (!isComparableQuestion(market.title ?? market.subtitle)) continue;
    const price = toNumber(market.last_price_dollars) ?? toNumber(market.yes_bid_dollars);
    if (price === undefined || !Number.isFinite(price)) continue;
    if (price <= 0 || price >= 1) continue;
    const displayedSize = toNumber(market.volume_24h_fp) ?? toNumber(market.liquidity_dollars);
    if (displayedSize === undefined || displayedSize <= 0) continue;

    snapshots.push({
      venue: "kalshi",
      externalId: market.ticker ?? market.event_ticker ?? "unknown-market",
      eventTitle: market.title ?? market.subtitle ?? market.event_ticker ?? "unknown-event",
      marketQuestion: market.title ?? market.subtitle ?? market.event_ticker ?? "unknown-question",
      outcomeLabel: market.yes_sub_title ?? "Yes",
      side: "yes",
      expiry: market.expiration_time ?? market.close_time,
      settlementText: [market.rules_primary, market.rules_secondary].filter(Boolean).join("\n\n") || market.title,
      price,
      displayedSize
    });
  }

  return snapshots.slice(0, limit);
}
