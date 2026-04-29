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

// Economic search terms to broaden Polymarket into Kalshi-overlapping territory
const ECONOMIC_SEARCH_TERMS = ["GDP", "CPI", "inflation", "Federal Reserve", "Fed rate", "unemployment", "recession", "tariff"];

async function fetchPolymarketEvents(params: Record<string, string>): Promise<GammaEvent[]> {
  const url = new URL("https://gamma-api.polymarket.com/events");
  for (const [k, v] of Object.entries(params)) url.searchParams.set(k, v);
  const response = await fetch(url, {
    headers: { accept: "application/json", "user-agent": "rumbling-hedge/0.1" },
    signal: AbortSignal.timeout(10_000)
  });
  if (!response.ok) throw new Error(`Polymarket gamma fetch failed: ${response.status} ${response.statusText}`);
  return response.json() as Promise<GammaEvent[]>;
}

function eventsToSnapshots(events: GammaEvent[]): PredictionMarketSnapshot[] {
  const snapshots: PredictionMarketSnapshot[] = [];
  for (const event of events) {
    for (const market of event.markets ?? []) {
      const outcomes = parseJsonArray<string>(market.outcomes);
      const prices = parseJsonArray<number | string>(market.outcomePrices).map((value) => Number(value));
      // Treat explicit 0 as missing — fall through to volume as liquidity proxy
      const rawLiquidity = toNumber(market.liquidity);
      const marketLiquidity = (rawLiquidity != null && rawLiquidity > 0 ? rawLiquidity : undefined)
        ?? (toNumber(market.volume24h) || undefined)
        ?? toNumber(market.volume24hr);

      outcomes.forEach((outcomeLabel, index) => {
        if (String(outcomeLabel).trim().toLowerCase() !== "yes") return;
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

export async function fetchPolymarketLiveSnapshot(limit = 10): Promise<PredictionMarketSnapshot[]> {
  // Primary fetch: top by volume (geopolitical, sports, entertainment)
  const primaryEvents = await fetchPolymarketEvents({
    limit: String(limit),
    closed: "false",
    order: "volume24hr",
    ascending: "false"
  });

  const snapshots = eventsToSnapshots(primaryEvents);
  const seen = new Set(snapshots.map((s) => s.externalId));

  // Secondary fetch: economic/financial topics (for Kalshi cross-venue matching)
  // Only run if we have room or environment enables it
  const enableEconomicSearch = process.env.BILL_POLYMARKET_ECONOMIC_SEARCH !== "false";
  if (enableEconomicSearch) {
    const econFetches = ECONOMIC_SEARCH_TERMS.slice(0, 4).map((term) =>
      fetchPolymarketEvents({ limit: "5", closed: "false", search: term }).catch(() => [] as GammaEvent[])
    );
    const econResults = await Promise.all(econFetches);
    for (const events of econResults) {
      for (const s of eventsToSnapshots(events)) {
        if (!seen.has(s.externalId)) {
          seen.add(s.externalId);
          snapshots.push(s);
        }
      }
    }
  }

  return snapshots;
}
