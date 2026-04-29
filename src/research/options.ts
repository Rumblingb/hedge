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
  lastPrice?: number;
  source?: "polygon" | "alpaca" | "yahoo";
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

function parseOccDate(compactDate: string): string | undefined {
  if (!/^\d{6}$/.test(compactDate)) return undefined;
  const year = Number(compactDate.slice(0, 2));
  const month = Number(compactDate.slice(2, 4));
  const day = Number(compactDate.slice(4, 6));
  const fullYear = year >= 70 ? 1900 + year : 2000 + year;
  return `${fullYear.toString().padStart(4, "0")}-${month.toString().padStart(2, "0")}-${day.toString().padStart(2, "0")}`;
}

function parseOccStrike(compactStrike: string): number | undefined {
  if (!/^\d{8}$/.test(compactStrike)) return undefined;
  const parsed = Number(compactStrike);
  return Number.isFinite(parsed) ? parsed / 1000 : undefined;
}

function parseOccContractSymbol(contract: string): {
  expirationDate?: string;
  contractType?: string;
  strike?: number;
} {
  const match = contract.match(/^[A-Z]+(?<date>\d{6})(?<type>[CP])(?<strike>\d{8})$/);
  if (!match?.groups) {
    return {};
  }

  return {
    expirationDate: parseOccDate(match.groups.date),
    contractType: match.groups.type === "C" ? "call" : match.groups.type === "P" ? "put" : undefined,
    strike: parseOccStrike(match.groups.strike)
  };
}

interface AlpacaOptionSnapshotPayload {
  next_page_token?: string | null;
  snapshots?: Record<string, {
    greeks?: {
      delta?: number | string;
      gamma?: number | string;
      iv?: number | string;
    };
    latestQuote?: {
      bp?: number | string;
      ap?: number | string;
    };
    latestTrade?: {
      p?: number | string;
    };
    openInterest?: number | string;
  }>;
}

export async function fetchAlpacaOptionSnapshots(args: {
  underlying: string;
  apiKey: string;
  secretKey: string;
  feed?: "indicative" | "opra";
  limit?: number;
  pageToken?: string;
}): Promise<{
  nextPageToken?: string;
  snapshots: PolygonOptionSnapshot[];
}> {
  const url = new URL(`https://data.alpaca.markets/v1beta1/options/snapshots/${encodeURIComponent(args.underlying)}`);
  url.searchParams.set("feed", args.feed ?? "indicative");
  url.searchParams.set("limit", String(args.limit ?? 100));
  if (args.pageToken) {
    url.searchParams.set("page_token", args.pageToken);
  }

  const response = await fetch(url, {
    headers: {
      accept: "application/json",
      "APCA-API-KEY-ID": args.apiKey,
      "APCA-API-SECRET-KEY": args.secretKey,
      "user-agent": "rumbling-hedge/0.1"
    },
    signal: AbortSignal.timeout(10_000)
  });
  if (!response.ok) {
    throw new Error(`Alpaca options snapshot failed for ${args.underlying}: ${response.status} ${response.statusText}`);
  }

  const payload = await response.json() as AlpacaOptionSnapshotPayload;
  const snapshots = Object.entries(payload.snapshots ?? {}).map(([contract, row]) => {
    const parsed = parseOccContractSymbol(contract);
    return {
      contract,
      underlying: args.underlying,
      strike: parsed.strike,
      expirationDate: parsed.expirationDate,
      contractType: parsed.contractType,
      impliedVolatility: toNumber(row.greeks?.iv),
      openInterest: toNumber(row.openInterest),
      delta: toNumber(row.greeks?.delta),
      gamma: toNumber(row.greeks?.gamma),
      bid: toNumber(row.latestQuote?.bp),
      ask: toNumber(row.latestQuote?.ap),
      lastPrice: toNumber(row.latestTrade?.p),
      source: "alpaca"
    } satisfies PolygonOptionSnapshot;
  });

  return {
    nextPageToken: payload.next_page_token ?? undefined,
    snapshots
  };
}

export async function fetchAlpacaUnderlyingPrice(args: {
  underlying: string;
  apiKey: string;
  secretKey: string;
}): Promise<number | undefined> {
  const url = `https://data.alpaca.markets/v2/stocks/${encodeURIComponent(args.underlying)}/snapshot`;
  const response = await fetch(url, {
    headers: {
      accept: "application/json",
      "APCA-API-KEY-ID": args.apiKey,
      "APCA-API-SECRET-KEY": args.secretKey,
      "user-agent": "rumbling-hedge/0.1"
    },
    signal: AbortSignal.timeout(10_000)
  });
  if (!response.ok) {
    throw new Error(`Alpaca underlying snapshot failed for ${args.underlying}: ${response.status} ${response.statusText}`);
  }

  const payload = await response.json() as {
    latestTrade?: { p?: number | string };
    latestQuote?: { bp?: number | string; ap?: number | string };
    minuteBar?: { c?: number | string };
    dailyBar?: { c?: number | string };
  };

  return toNumber(payload.latestTrade?.p)
    ?? (() => {
      const bid = toNumber(payload.latestQuote?.bp);
      const ask = toNumber(payload.latestQuote?.ap);
      if (bid !== undefined && ask !== undefined) {
        return Number(((bid + ask) / 2).toFixed(4));
      }
      return undefined;
    })()
    ?? toNumber(payload.minuteBar?.c)
    ?? toNumber(payload.dailyBar?.c);
}

interface YahooOptionContract {
  contractSymbol?: string;
  strike?: number;
  expiration?: number;
  impliedVolatility?: number;
  openInterest?: number;
  bid?: number;
  ask?: number;
  lastPrice?: number;
}

interface YahooOptionResult {
  optionChain?: {
    result?: Array<{
      expirationDates?: number[];
      quote?: {
        regularMarketPrice?: number;
      };
      options?: Array<{
        calls?: YahooOptionContract[];
        puts?: YahooOptionContract[];
      }>;
    }>;
  };
}

function toIsoDate(epochSeconds: number | undefined): string | undefined {
  if (!epochSeconds || !Number.isFinite(epochSeconds)) return undefined;
  return new Date(epochSeconds * 1000).toISOString().slice(0, 10);
}

function normalizeYahooContracts(args: {
  underlying: string;
  contracts: YahooOptionContract[] | undefined;
  contractType: "call" | "put";
}): PolygonOptionSnapshot[] {
  return (args.contracts ?? []).map((row) => ({
    contract: row.contractSymbol ?? "unknown-option",
    underlying: args.underlying,
    strike: toNumber(row.strike),
    expirationDate: toIsoDate(row.expiration),
    contractType: args.contractType,
    impliedVolatility: toNumber(row.impliedVolatility),
    openInterest: toNumber(row.openInterest),
    bid: toNumber(row.bid),
    ask: toNumber(row.ask),
    lastPrice: toNumber(row.lastPrice),
    source: "yahoo"
  }));
}

export async function fetchYahooOptionSnapshots(args: {
  underlying: string;
  expirationDate?: string;
}): Promise<{
  underlyingPrice?: number;
  selectedExpirationDate?: string;
  snapshots: PolygonOptionSnapshot[];
}> {
  const baseUrl = new URL(`https://query2.finance.yahoo.com/v7/finance/options/${encodeURIComponent(args.underlying)}`);
  if (args.expirationDate) {
    const epoch = Math.floor(Date.parse(`${args.expirationDate}T00:00:00Z`) / 1000);
    if (Number.isFinite(epoch)) {
      baseUrl.searchParams.set("date", String(epoch));
    }
  }

  const response = await fetch(baseUrl, {
    headers: {
      accept: "application/json",
      "user-agent": "rumbling-hedge/0.1"
    },
    signal: AbortSignal.timeout(10_000)
  });
  if (!response.ok) {
    throw new Error(`Yahoo options snapshot failed for ${args.underlying}: ${response.status} ${response.statusText}`);
  }

  const payload = await response.json() as YahooOptionResult;
  const result = payload.optionChain?.result?.[0];
  const optionSet = result?.options?.[0];
  const calls = normalizeYahooContracts({
    underlying: args.underlying,
    contracts: optionSet?.calls,
    contractType: "call"
  });
  const puts = normalizeYahooContracts({
    underlying: args.underlying,
    contracts: optionSet?.puts,
    contractType: "put"
  });
  const selectedExpirationDate = optionSet?.calls?.[0]?.expiration
    ? toIsoDate(optionSet.calls[0].expiration)
    : optionSet?.puts?.[0]?.expiration
      ? toIsoDate(optionSet.puts[0].expiration)
      : undefined;

  return {
    underlyingPrice: toNumber(result?.quote?.regularMarketPrice),
    selectedExpirationDate,
    snapshots: [...calls, ...puts]
  };
}

export function defaultOptionsOutPath(underlying: string): string {
  return path.resolve(`data/research/options/${underlying}-options-snapshot.json`);
}

export interface OneDayToExpiryOptionReport {
  underlying: string;
  source: "polygon" | "alpaca" | "yahoo";
  selectedExpirationDate?: string;
  dteCalendarDays?: number;
  underlyingPrice?: number;
  contractCount: number;
  callCount: number;
  putCount: number;
  avgImpliedVolatility?: number;
  atmStrike?: number;
  atmCallAsk?: number;
  atmPutAsk?: number;
  atmStraddleAsk?: number;
  highestOpenInterest?: Array<{
    contract: string;
    contractType?: string;
    strike?: number;
    openInterest?: number;
    bid?: number;
    ask?: number;
  }>;
}

export function buildOneDayToExpiryOptionReport(args: {
  underlying: string;
  snapshots: PolygonOptionSnapshot[];
  source: "polygon" | "alpaca" | "yahoo";
  selectedExpirationDate?: string;
  underlyingPrice?: number;
  now?: Date;
}): OneDayToExpiryOptionReport {
  const now = args.now ?? new Date();
  const selectedExpirationDate = args.selectedExpirationDate
    ?? args.snapshots
      .map((row) => row.expirationDate)
      .filter((value): value is string => Boolean(value))
      .sort()[0];
  const snapshots = selectedExpirationDate
    ? args.snapshots.filter((row) => row.expirationDate === selectedExpirationDate)
    : [...args.snapshots];
  const callCount = snapshots.filter((row) => row.contractType === "call").length;
  const putCount = snapshots.filter((row) => row.contractType === "put").length;
  const ivs = snapshots.map((row) => row.impliedVolatility).filter((value): value is number => value !== undefined && Number.isFinite(value));
  const atmStrike = args.underlyingPrice === undefined
    ? undefined
    : snapshots
      .map((row) => row.strike)
      .filter((value): value is number => value !== undefined && Number.isFinite(value))
      .sort((left, right) => Math.abs(left - args.underlyingPrice!) - Math.abs(right - args.underlyingPrice!))[0];
  const atmCall = snapshots.find((row) => row.contractType === "call" && row.strike === atmStrike);
  const atmPut = snapshots.find((row) => row.contractType === "put" && row.strike === atmStrike);
  const dteCalendarDays = selectedExpirationDate
    ? Math.max(0, Math.round((Date.parse(`${selectedExpirationDate}T23:59:59.999Z`) - now.getTime()) / 86_400_000))
    : undefined;

  return {
    underlying: args.underlying,
    source: args.source,
    selectedExpirationDate,
    dteCalendarDays,
    underlyingPrice: args.underlyingPrice,
    contractCount: snapshots.length,
    callCount,
    putCount,
    avgImpliedVolatility: ivs.length > 0 ? Number((ivs.reduce((sum, value) => sum + value, 0) / ivs.length).toFixed(4)) : undefined,
    atmStrike,
    atmCallAsk: atmCall?.ask,
    atmPutAsk: atmPut?.ask,
    atmStraddleAsk: atmCall?.ask !== undefined && atmPut?.ask !== undefined
      ? Number((atmCall.ask + atmPut.ask).toFixed(4))
      : undefined,
    highestOpenInterest: snapshots
      .filter((row) => row.openInterest !== undefined)
      .sort((left, right) => (right.openInterest ?? 0) - (left.openInterest ?? 0))
      .slice(0, 5)
      .map((row) => ({
        contract: row.contract,
        contractType: row.contractType,
        strike: row.strike,
        openInterest: row.openInterest,
        bid: row.bid,
        ask: row.ask
      }))
  };
}
