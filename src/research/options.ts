import path from "node:path";

export interface PolygonOptionSnapshot {
  contract: string;
  underlying: string;
  strike?: number;
  expirationDate?: string;
  contractType?: string;
  impliedVolatility?: number;
  openInterest?: number;
  delta?: number;
  gamma?: number;
  bid?: number;
  ask?: number;
}

function toNumber(value: unknown): number | undefined {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string") {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : undefined;
  }
  return undefined;
}

export function parsePolygonOptionSnapshots(args: { underlying: string; payload: unknown }): PolygonOptionSnapshot[] {
  const { underlying, payload } = args;
  const data = payload as {
    results?: Array<{
      details?: {
        ticker?: string;
        contract_type?: string;
        expiration_date?: string;
        strike_price?: number | string;
      };
      implied_volatility?: number | string;
      open_interest?: number | string;
      greeks?: {
        delta?: number | string;
        gamma?: number | string;
      };
      last_quote?: {
        bid?: number | string;
        ask?: number | string;
      };
    }>;
  };

  return (data.results ?? []).map((row) => ({
    contract: row.details?.ticker ?? "unknown-option",
    underlying,
    strike: toNumber(row.details?.strike_price),
    expirationDate: row.details?.expiration_date,
    contractType: row.details?.contract_type,
    impliedVolatility: toNumber(row.implied_volatility),
    openInterest: toNumber(row.open_interest),
    delta: toNumber(row.greeks?.delta),
    gamma: toNumber(row.greeks?.gamma),
    bid: toNumber(row.last_quote?.bid),
    ask: toNumber(row.last_quote?.ask)
  }));
}

export async function fetchPolygonOptionSnapshots(args: {
  underlying: string;
  apiKey: string;
  baseUrl?: string;
  limit?: number;
}): Promise<PolygonOptionSnapshot[]> {
  const baseUrl = (args.baseUrl ?? "https://api.polygon.io").replace(/\/$/, "");
  const url = new URL(`${baseUrl}/v3/snapshot/options/${encodeURIComponent(args.underlying)}`);
  url.searchParams.set("limit", String(args.limit ?? 25));
  url.searchParams.set("apiKey", args.apiKey);

  const response = await fetch(url, {
    headers: {
      accept: "application/json",
      "user-agent": "rumbling-hedge/0.1"
    },
    signal: AbortSignal.timeout(10_000)
  });
  if (!response.ok) {
    throw new Error(`Polygon options snapshot failed for ${args.underlying}: ${response.status} ${response.statusText}`);
  }

  return parsePolygonOptionSnapshots({
    underlying: args.underlying,
    payload: await response.json()
  });
}

export function defaultOptionsOutPath(underlying: string): string {
  return path.resolve(`data/research/options/${underlying}-polygon-snapshot.json`);
}
