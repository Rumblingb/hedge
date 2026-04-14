import type { PredictionMarketSnapshot } from "../types.js";

interface GammaEvent {
  id?: string;
  title?: string;
  slug?: string;
  endDate?: string;
  markets?: Array<{
    id?: string;
    question?: string;
    description?: string;
    outcomes?: string[] | string;
    outcomePrices?: number[] | string;
    clobTokenIds?: string[] | string;
    active?: boolean;
    closed?: boolean;
    volume24hr?: number | string;
    volume24h?: number | string;
    liquidity?: number | string;
  }>;
}

function parseJsonArray<T = unknown>(value: unknown): T[] {
  if (Array.isArray(value)) return value as T[];
  if (typeof value === "string") {
    try {
      const parsed = JSON.parse(value);
      return Array.isArray(parsed) ? (parsed as T[]) : [];
    } catch {
      return [];
    }
  }
  return [];
}

function toNumber(value: unknown): number | undefined {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string") {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : undefined;
  }
  return undefined;
}

export async function fetchPolymarketLiveSnapshot(limit = 10): Promise<PredictionMarketSnapshot[]> {
  const url = new URL("https://gamma-api.polymarket.com/events");
  url.searchParams.set("limit", String(limit));
  url.searchParams.set("closed", "false");
  url.searchParams.set("order", "volume24hr");
  url.searchParams.set("ascending", "false");

  const response = await fetch(url, {
    headers: {
      accept: "application/json",
      "user-agent": "rumbling-hedge/0.1"
    }
  });

  if (!response.ok) {
    throw new Error(`Polymarket gamma fetch failed: ${response.status} ${response.statusText}`);
  }

  const events = (await response.json()) as GammaEvent[];
  const snapshots: PredictionMarketSnapshot[] = [];

  for (const event of events) {
    for (const market of event.markets ?? []) {
      const outcomes = parseJsonArray<string>(market.outcomes);
      const prices = parseJsonArray<number | string>(market.outcomePrices).map((value) => Number(value));
      const marketLiquidity = toNumber(market.liquidity) ?? toNumber(market.volume24h) ?? toNumber(market.volume24hr);

      outcomes.forEach((outcomeLabel, index) => {
        const price = Number(prices[index]);
        if (!Number.isFinite(price)) return;
        snapshots.push({
          venue: "polymarket",
          externalId: market.id ?? `${event.id ?? event.slug ?? "event"}:${index}`,
          eventTitle: event.title ?? market.question ?? "unknown-event",
          marketQuestion: market.question ?? event.title ?? "unknown-question",
          outcomeLabel,
          side: "yes",
          expiry: event.endDate,
          settlementText: market.description ?? market.question ?? event.title,
          price,
          displayedSize: marketLiquidity
        });
      });
    }
  }

  return snapshots;
}
