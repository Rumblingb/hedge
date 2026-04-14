export interface FredObservation {
  date: string;
  value?: number;
}

function toNumber(value: unknown): number | undefined {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string") {
    const trimmed = value.trim();
    if (!trimmed || trimmed === ".") return undefined;
    const parsed = Number(trimmed);
    return Number.isFinite(parsed) ? parsed : undefined;
  }
  return undefined;
}

export function parseFredObservations(payload: unknown): FredObservation[] {
  const data = payload as {
    observations?: Array<{ date?: string; value?: unknown }>;
  };

  return (data.observations ?? [])
    .filter((row) => typeof row.date === "string" && row.date.length > 0)
    .map((row) => ({
      date: row.date as string,
      value: toNumber(row.value)
    }));
}

export async function fetchFredSeries(args: {
  seriesId: string;
  apiKey: string;
  baseUrl?: string;
  limit?: number;
}): Promise<FredObservation[]> {
  const baseUrl = (args.baseUrl ?? "https://api.stlouisfed.org").replace(/\/$/, "");
  const url = new URL(`${baseUrl}/fred/series/observations`);
  url.searchParams.set("series_id", args.seriesId);
  url.searchParams.set("api_key", args.apiKey);
  url.searchParams.set("file_type", "json");
  url.searchParams.set("sort_order", "desc");
  url.searchParams.set("limit", String(args.limit ?? 60));

  const response = await fetch(url, {
    headers: {
      accept: "application/json",
      "user-agent": "rumbling-hedge/0.1"
    },
    signal: AbortSignal.timeout(10_000)
  });
  if (!response.ok) {
    throw new Error(`FRED series fetch failed for ${args.seriesId}: ${response.status} ${response.statusText}`);
  }

  return parseFredObservations(await response.json());
}
