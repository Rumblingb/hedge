import { mkdir, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import type { Bar } from "../domain.js";
import { normalizeFuturesSymbol } from "../utils/markets.js";

export type FreeDataProvider = "auto" | "yahoo" | "stooq" | "polygon";
export type FreeInterval = "1m" | "2m" | "5m" | "15m" | "30m" | "60m" | "90m" | "1d";

export interface FetchFreeBarsArgs {
  symbol: string;
  interval: FreeInterval;
  range: string;
  provider?: FreeDataProvider;
  timeoutMs?: number;
}

export interface FetchFreeBarsResult {
  providerUsed: Exclude<FreeDataProvider, "auto">;
  providerSymbol: string;
  bars: Bar[];
  warnings: string[];
}

const DEFAULT_TIMEOUT_MS = 20_000;

const YAHOO_TICKER_BY_SYMBOL: Record<string, string> = {
  BTCUSD: "BTC-USD",
  ETHUSD: "ETH-USD",
  ES: "ES=F",
  NQ: "NQ=F",
  RTY: "RTY=F",
  YM: "YM=F",
  CL: "CL=F",
  NG: "NG=F",
  GC: "GC=F",
  SI: "SI=F",
  HG: "HG=F",
  ZN: "ZN=F",
  ZB: "ZB=F",
  ZF: "ZF=F",
  ZT: "ZT=F",
  "6E": "6E=F",
  "6J": "6J=F",
  "6B": "6B=F",
  "6A": "6A=F",
  "6C": "6C=F",
  "6S": "6S=F"
};

const STOOQ_SYMBOL_BY_ROOT: Record<string, string> = {
  ES: "es.f",
  NQ: "nq.f",
  CL: "cl.f",
  GC: "gc.f",
  ZN: "zn.f",
  ZB: "zb.f"
};

const POLYGON_TICKER_BY_SYMBOL: Record<string, string> = {
  BTCUSD: "X:BTCUSD",
  ETHUSD: "X:ETHUSD",
  ES: "I:ES1!",
  MES: "I:MES1!",
  NQ: "I:NQ1!",
  MNQ: "I:MNQ1!",
  CL: "I:CL1!",
  MCL: "I:MCL1!",
  GC: "I:GC1!",
  MGC: "I:MGC1!",
  "6E": "I:EURUSD",
  ZN: "I:ZN1!"
};

function buildProviderOrder(provider: FreeDataProvider, interval: FreeInterval): Exclude<FreeDataProvider, "auto">[] {
  if (provider !== "auto") {
    return [provider];
  }

  if (interval === "1d") {
    return ["polygon", "yahoo", "stooq"];
  }

  return ["polygon", "yahoo"];
}

function getYahooTicker(symbol: string): string {
  return YAHOO_TICKER_BY_SYMBOL[symbol] ?? `${symbol}=F`;
}

function getStooqTicker(symbol: string): string | null {
  return STOOQ_SYMBOL_BY_ROOT[symbol] ?? null;
}

function getPolygonTicker(symbol: string): string {
  return POLYGON_TICKER_BY_SYMBOL[symbol] ?? symbol;
}

function withTimeout(timeoutMs: number): AbortSignal {
  const controller = new AbortController();
  setTimeout(() => controller.abort(), timeoutMs);
  return controller.signal;
}

function parseFiniteNumber(value: unknown): number | null {
  if (typeof value !== "number") {
    return null;
  }
  return Number.isFinite(value) ? value : null;
}

export function parseYahooChartPayload(args: {
  payload: unknown;
  symbol: string;
}): Bar[] {
  const { payload, symbol } = args;
  const data = payload as {
    chart?: {
      result?: Array<{
        timestamp?: number[];
        indicators?: {
          quote?: Array<{
            open?: Array<number | null>;
            high?: Array<number | null>;
            low?: Array<number | null>;
            close?: Array<number | null>;
            volume?: Array<number | null>;
          }>;
        };
      }>;
      error?: { description?: string } | null;
    };
  };

  if (data.chart?.error) {
    throw new Error(`Yahoo returned an error: ${data.chart.error.description ?? "unknown error"}`);
  }

  const first = data.chart?.result?.[0];
  const quote = first?.indicators?.quote?.[0];
  if (!first?.timestamp || !quote) {
    throw new Error("Yahoo response missing timestamp/quote arrays.");
  }

  const bars: Bar[] = [];

  first.timestamp.forEach((epoch, index) => {
    const open = parseFiniteNumber(quote.open?.[index]);
    const high = parseFiniteNumber(quote.high?.[index]);
    const low = parseFiniteNumber(quote.low?.[index]);
    const close = parseFiniteNumber(quote.close?.[index]);
    const volume = parseFiniteNumber(quote.volume?.[index]) ?? 0;

    if (open === null || high === null || low === null || close === null) {
      return;
    }

    bars.push({
      ts: new Date(epoch * 1000).toISOString(),
      symbol,
      open,
      high,
      low,
      close,
      volume
    });
  });

  return bars;
}

export function parseStooqDailyCsv(args: {
  csv: string;
  symbol: string;
}): Bar[] {
  const { csv, symbol } = args;
  const lines = csv
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter((line) => line.length > 0);

  if (lines.length <= 1) {
    return [];
  }

  const bars: Bar[] = [];

  for (const line of lines.slice(1)) {
    const [date, openRaw, highRaw, lowRaw, closeRaw, volumeRaw] = line.split(",");
    const open = Number(openRaw);
    const high = Number(highRaw);
    const low = Number(lowRaw);
    const close = Number(closeRaw);
    const volume = Number(volumeRaw ?? "0");

    if (!date || [open, high, low, close].some((value) => !Number.isFinite(value))) {
      continue;
    }

    bars.push({
      ts: new Date(`${date}T00:00:00.000Z`).toISOString(),
      symbol,
      open,
      high,
      low,
      close,
      volume: Number.isFinite(volume) ? volume : 0
    });
  }

  return bars;
}

async function fetchYahooBars(args: {
  symbol: string;
  interval: FreeInterval;
  range: string;
  timeoutMs: number;
}): Promise<FetchFreeBarsResult> {
  const { symbol, interval, range, timeoutMs } = args;
  const yahooSymbol = getYahooTicker(symbol);
  const url = new URL(`https://query1.finance.yahoo.com/v8/finance/chart/${encodeURIComponent(yahooSymbol)}`);
  url.searchParams.set("interval", interval);
  url.searchParams.set("range", range);
  url.searchParams.set("includePrePost", "true");

  const response = await fetch(url, { signal: withTimeout(timeoutMs) });
  if (!response.ok) {
    throw new Error(`Yahoo request failed: HTTP ${response.status}`);
  }

  const payload = await response.json();
  const bars = parseYahooChartPayload({ payload, symbol });

  if (bars.length === 0) {
    throw new Error("Yahoo returned no valid bars.");
  }

  return {
    providerUsed: "yahoo",
    providerSymbol: yahooSymbol,
    bars,
    warnings: []
  };
}

async function fetchStooqBars(args: {
  symbol: string;
  interval: FreeInterval;
  timeoutMs: number;
}): Promise<FetchFreeBarsResult> {
  const { symbol, interval, timeoutMs } = args;
  if (interval !== "1d") {
    throw new Error("Stooq fallback supports only 1d interval.");
  }

  const stooqSymbol = getStooqTicker(symbol);
  if (!stooqSymbol) {
    throw new Error(`Stooq mapping not available for symbol ${symbol}.`);
  }

  const url = `https://stooq.com/q/d/l/?s=${encodeURIComponent(stooqSymbol)}&i=d`;
  const response = await fetch(url, { signal: withTimeout(timeoutMs) });
  if (!response.ok) {
    throw new Error(`Stooq request failed: HTTP ${response.status}`);
  }

  const csv = await response.text();
  const bars = parseStooqDailyCsv({ csv, symbol });
  if (bars.length === 0) {
    throw new Error("Stooq returned no valid bars.");
  }

  return {
    providerUsed: "stooq",
    providerSymbol: stooqSymbol,
    bars,
    warnings: ["Stooq fallback currently provides daily bars only."]
  };
}

function mapIntervalToPolygonMultiplier(interval: FreeInterval): { multiplier: number; timespan: "minute" | "hour" | "day" } {
  switch (interval) {
    case "1m":
      return { multiplier: 1, timespan: "minute" };
    case "2m":
      return { multiplier: 2, timespan: "minute" };
    case "5m":
      return { multiplier: 5, timespan: "minute" };
    case "15m":
      return { multiplier: 15, timespan: "minute" };
    case "30m":
      return { multiplier: 30, timespan: "minute" };
    case "60m":
      return { multiplier: 1, timespan: "hour" };
    case "90m":
      return { multiplier: 90, timespan: "minute" };
    case "1d":
      return { multiplier: 1, timespan: "day" };
    default:
      return { multiplier: 1, timespan: "minute" };
  }
}

function parsePolygonRange(range: string): { amount: number; unit: "day" | "month" | "year" } {
  const match = range.trim().toLowerCase().match(/^(\d+)([dmy])$/);
  if (!match) {
    return { amount: 5, unit: "day" };
  }

  const amount = Math.max(1, Number(match[1]));
  const suffix = match[2];
  if (suffix === "m") {
    return { amount, unit: "month" };
  }
  if (suffix === "y") {
    return { amount, unit: "year" };
  }
  return { amount, unit: "day" };
}

function subtractRangeFromNow(range: string): { fromIso: string; toIso: string } {
  const now = new Date();
  const from = new Date(now.getTime());
  const parsed = parsePolygonRange(range);

  if (parsed.unit === "day") {
    from.setUTCDate(from.getUTCDate() - parsed.amount);
  } else if (parsed.unit === "month") {
    from.setUTCMonth(from.getUTCMonth() - parsed.amount);
  } else {
    from.setUTCFullYear(from.getUTCFullYear() - parsed.amount);
  }

  return {
    fromIso: from.toISOString().slice(0, 10),
    toIso: now.toISOString().slice(0, 10)
  };
}

async function fetchPolygonBars(args: {
  symbol: string;
  interval: FreeInterval;
  range: string;
  timeoutMs: number;
}): Promise<FetchFreeBarsResult> {
  const { symbol, interval, range, timeoutMs } = args;
  const apiKey = process.env.RH_POLYGON_API_KEY;
  if (!apiKey) {
    throw new Error("Polygon requires RH_POLYGON_API_KEY.");
  }

  const baseUrl = process.env.RH_POLYGON_BASE_URL ?? "https://api.polygon.io";
  const polygonTicker = getPolygonTicker(symbol);
  const { multiplier, timespan } = mapIntervalToPolygonMultiplier(interval);
  const { fromIso, toIso } = subtractRangeFromNow(range);
  const url = new URL(`${baseUrl.replace(/\/$/, "")}/v2/aggs/ticker/${encodeURIComponent(polygonTicker)}/range/${multiplier}/${timespan}/${fromIso}/${toIso}`);
  url.searchParams.set("adjusted", "true");
  url.searchParams.set("sort", "asc");
  url.searchParams.set("limit", "50000");
  url.searchParams.set("apiKey", apiKey);

  const response = await fetch(url, { signal: withTimeout(timeoutMs) });
  if (!response.ok) {
    throw new Error(`Polygon request failed: HTTP ${response.status}`);
  }

  const payload = await response.json() as {
    status?: string;
    results?: Array<{ t: number; o: number; h: number; l: number; c: number; v?: number }>;
    error?: string;
    message?: string;
  };

  if (payload.status !== "OK") {
    throw new Error(payload.error ?? payload.message ?? "Polygon returned non-OK status.");
  }

  const bars: Bar[] = (payload.results ?? [])
    .filter((row) => Number.isFinite(row.o) && Number.isFinite(row.h) && Number.isFinite(row.l) && Number.isFinite(row.c))
    .map((row) => ({
      ts: new Date(row.t).toISOString(),
      symbol,
      open: row.o,
      high: row.h,
      low: row.l,
      close: row.c,
      volume: Number.isFinite(row.v) ? (row.v ?? 0) : 0
    }));

  if (bars.length === 0) {
    throw new Error("Polygon returned no valid bars.");
  }

  return {
    providerUsed: "polygon",
    providerSymbol: polygonTicker,
    bars,
    warnings: ["Polygon ticker mapping may need verification for your entitlement."]
  };
}

export async function fetchFreeBars(args: FetchFreeBarsArgs): Promise<FetchFreeBarsResult> {
  const symbol = normalizeFuturesSymbol(args.symbol);
  if (!symbol) {
    throw new Error("Symbol is required.");
  }

  const interval = args.interval;
  const range = args.range;
  const provider = args.provider ?? "auto";
  const timeoutMs = args.timeoutMs ?? DEFAULT_TIMEOUT_MS;
  const providers = buildProviderOrder(provider, interval);
  const failures: string[] = [];

  for (const candidate of providers) {
    try {
      if (candidate === "yahoo") {
        return await fetchYahooBars({ symbol, interval, range, timeoutMs });
      }

      if (candidate === "stooq") {
        return await fetchStooqBars({ symbol, interval, timeoutMs });
      }

      if (candidate === "polygon") {
        return await fetchPolygonBars({ symbol, interval, range, timeoutMs });
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      failures.push(`${candidate}: ${message}`);
    }
  }

  throw new Error(`All free providers failed for ${symbol} (${interval}, ${range}). ${failures.join(" | ")}`);
}

export function toCsvContent(bars: Bar[]): string {
  const header = "ts,symbol,open,high,low,close,volume";
  const rows = bars
    .slice()
    .sort((left, right) => Date.parse(left.ts) - Date.parse(right.ts))
    .map((bar) => [
      bar.ts,
      bar.symbol,
      bar.open,
      bar.high,
      bar.low,
      bar.close,
      bar.volume
    ].join(","));

  return `${header}\n${rows.join("\n")}\n`;
}

export async function writeBarsCsv(args: {
  bars: Bar[];
  outPath: string;
}): Promise<string> {
  const outPath = resolve(args.outPath);
  await mkdir(dirname(outPath), { recursive: true });
  await writeFile(outPath, toCsvContent(args.bars), "utf8");
  return outPath;
}
