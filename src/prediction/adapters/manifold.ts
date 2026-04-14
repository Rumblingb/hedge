import type { PredictionMarketSnapshot } from "../types.js";

interface ManifoldMarket {
  id?: string;
  question?: string;
  outcomeType?: string;
  probability?: number;
  closeTime?: number;
  volume?: number;
  isResolved?: boolean;
  mechanism?: string;
}

function toIso(value?: number): string | undefined {
  if (typeof value !== "number" || !Number.isFinite(value)) return undefined;
  return new Date(value).toISOString();
}

export async function fetchManifoldLiveSnapshot(limit = 25): Promise<PredictionMarketSnapshot[]> {
  const url = new URL("https://api.manifold.markets/v0/markets");
  url.searchParams.set("limit", String(Math.max(limit * 4, 100)));

  const response = await fetch(url, {
    headers: {
      accept: "application/json",
      "user-agent": "rumbling-hedge/0.1"
    },
    signal: AbortSignal.timeout(10_000)
  });

  if (!response.ok) {
    throw new Error(`Manifold market fetch failed: ${response.status} ${response.statusText}`);
  }

  const payload = (await response.json()) as ManifoldMarket[];
  return payload
    .filter((market) => market.outcomeType === "BINARY" && market.isResolved === false)
    .filter((market) => typeof market.probability === "number" && market.probability > 0 && market.probability < 1)
    .sort((left, right) => (right.volume ?? 0) - (left.volume ?? 0))
    .slice(0, limit)
    .map((market) => ({
      venue: "manifold",
      externalId: market.id ?? "unknown-market",
      eventTitle: market.question ?? "unknown-event",
      marketQuestion: market.question ?? "unknown-question",
      outcomeLabel: "Yes",
      side: "yes" as const,
      expiry: toIso(market.closeTime),
      settlementText: market.question ?? "unknown-question",
      price: market.probability as number,
      displayedSize: market.volume ?? 0
    }));
}
