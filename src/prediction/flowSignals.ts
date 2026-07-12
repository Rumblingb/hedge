import { mkdir, appendFile, readFile } from "node:fs/promises";
import { dirname } from "node:path";

const POLYMARKET_GAMMA = "https://gamma-api.polymarket.com/markets";
const KALSHI_API = "https://api.elections.kalshi.com/trade-api/v2/markets";
const FETCH_HEADERS = {
  accept: "application/json",
  "user-agent": "rumbling-hedge-flow/0.1"
} as const;

export const DEFAULT_FLOW_HISTORY_PATH = "journals/prediction-flow-history.jsonl";
export const DEFAULT_FLOW_SIGNALS_PATH = "journals/prediction-flow-signals.jsonl";
export const DEFAULT_MIN_COMPOSITE_SCORE = 0.6;

export interface MarketFlowSnapshot {
  venue: "polymarket" | "kalshi" | "manifold";
  marketId: string;
  slug?: string;
  title: string;
  outcome?: string;
  ts: string;
  price: number;
  volume24h?: number;
  volumeTotal?: number;
  liquidity?: number;
  traderCount24h?: number;
}

export interface FlowAccelerationScore {
  venue: string;
  marketId: string;
  title: string;
  windowHours: number;
  priceChange: number;
  volumeAccelerationRatio: number;
  oneSidednessScore: number;
  smartMoneyOverlap?: number;
  compositeScore: number;
  reasons: string[];
}

interface Bucket {
  ts: number;
  priceSum: number;
  priceCount: number;
  lastVolume24h?: number;
  lastVolumeTotal?: number;
  firstVolumeTotal?: number;
}

function parseNumber(value: unknown): number | undefined {
  if (value === null || value === undefined) return undefined;
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string") {
    const n = Number(value);
    if (Number.isFinite(n)) return n;
  }
  return undefined;
}

function bucketize(history: MarketFlowSnapshot[], nBuckets: number, windowHours: number): Bucket[] {
  if (history.length === 0) return [];
  const sorted = [...history].sort((a, b) => Date.parse(a.ts) - Date.parse(b.ts));
  const endMs = Date.parse(sorted[sorted.length - 1].ts);
  const windowMs = windowHours * 3_600_000;
  const startMs = endMs - windowMs;
  const bucketSize = windowMs / nBuckets;
  const buckets: Bucket[] = [];
  for (let i = 0; i < nBuckets; i++) {
    buckets.push({
      ts: startMs + i * bucketSize,
      priceSum: 0,
      priceCount: 0
    });
  }
  for (const snap of sorted) {
    const t = Date.parse(snap.ts);
    if (t < startMs || t > endMs) continue;
    let idx = Math.floor((t - startMs) / bucketSize);
    if (idx >= nBuckets) idx = nBuckets - 1;
    if (idx < 0) idx = 0;
    const b = buckets[idx];
    b.priceSum += snap.price;
    b.priceCount += 1;
    if (snap.volume24h !== undefined) b.lastVolume24h = snap.volume24h;
    if (snap.volumeTotal !== undefined) {
      if (b.firstVolumeTotal === undefined) b.firstVolumeTotal = snap.volumeTotal;
      b.lastVolumeTotal = snap.volumeTotal;
    }
  }
  return buckets;
}

export function computeFlowAcceleration(
  history: MarketFlowSnapshot[],
  opts: { windowHours?: number; nBuckets?: number } = {}
): FlowAccelerationScore | null {
  if (history.length < 3) return null;
  const windowHours = opts.windowHours ?? 12;
  const nBuckets = opts.nBuckets ?? 6;
  const first = history[0];
  const buckets = bucketize(history, nBuckets, windowHours);

  const priced: { idx: number; price: number }[] = [];
  for (let i = 0; i < buckets.length; i++) {
    const b = buckets[i];
    if (b.priceCount > 0) priced.push({ idx: i, price: b.priceSum / b.priceCount });
  }
  if (priced.length < 2) return null;

  const priceChange = priced[priced.length - 1].price - priced[0].price;

  const diffs: number[] = [];
  for (let i = 1; i < priced.length; i++) {
    diffs.push(priced[i].price - priced[i - 1].price);
  }
  let pos = 0;
  let neg = 0;
  let nonZero = 0;
  for (const d of diffs) {
    if (d > 0) {
      pos += 1;
      nonZero += 1;
    } else if (d < 0) {
      neg += 1;
      nonZero += 1;
    }
  }
  const oneSidednessScore = nonZero === 0 ? 0 : Math.max(pos, neg) / nonZero;

  const bucketVolumes: number[] = [];
  for (const b of buckets) {
    if (b.lastVolume24h !== undefined) {
      bucketVolumes.push(b.lastVolume24h);
    } else if (b.firstVolumeTotal !== undefined && b.lastVolumeTotal !== undefined) {
      bucketVolumes.push(Math.max(0, b.lastVolumeTotal - b.firstVolumeTotal));
    } else {
      bucketVolumes.push(0);
    }
  }
  let volumeAccelerationRatio = 1;
  if (bucketVolumes.length >= 2) {
    const last = bucketVolumes[bucketVolumes.length - 1];
    const priorSlice = bucketVolumes.slice(0, -1).filter((v) => v > 0);
    if (priorSlice.length > 0) {
      const priorMean = priorSlice.reduce((a, b) => a + b, 0) / priorSlice.length;
      if (priorMean > 0) volumeAccelerationRatio = last / priorMean;
    } else if (last > 0) {
      volumeAccelerationRatio = 5;
    }
  }

  const accelComponent = Math.max(0, Math.min((volumeAccelerationRatio - 1) / 4, 1));
  const priceComponent = Math.min(Math.abs(priceChange) / 0.2, 1);
  const compositeScore =
    0.5 * accelComponent + 0.3 * oneSidednessScore + 0.2 * priceComponent;

  const reasons: string[] = [];
  if (volumeAccelerationRatio > 3) reasons.push("volume-3x-prior");
  if (oneSidednessScore > 0.8) reasons.push("consistent-directional-push");
  if (Math.abs(priceChange) > 0.1) reasons.push("large-absolute-move");

  return {
    venue: first.venue,
    marketId: first.marketId,
    title: first.title,
    windowHours,
    priceChange,
    volumeAccelerationRatio,
    oneSidednessScore,
    compositeScore,
    reasons
  };
}

interface PolymarketGammaMarket {
  id?: string | number;
  conditionId?: string;
  slug?: string;
  question?: string;
  title?: string;
  outcomePrices?: string | string[];
  outcomes?: string | string[];
  lastTradePrice?: number | string;
  volume24hr?: number | string;
  volume?: number | string;
  liquidity?: number | string;
}

function parseStringList(value: unknown): string[] | undefined {
  if (Array.isArray(value)) return value.map((v) => String(v));
  if (typeof value === "string") {
    try {
      const parsed = JSON.parse(value);
      if (Array.isArray(parsed)) return parsed.map((v) => String(v));
    } catch {
      // fall through
    }
  }
  return undefined;
}

export async function fetchPolymarketActiveMarkets(
  opts: { limit?: number; minVolume24h?: number } = {}
): Promise<MarketFlowSnapshot[]> {
  const limit = opts.limit ?? 100;
  const minVolume = opts.minVolume24h ?? 0;
  const url = `${POLYMARKET_GAMMA}?active=true&closed=false&limit=${limit}&order=volume24hr&ascending=false`;
  const res = await fetch(url, {
    headers: FETCH_HEADERS,
    signal: AbortSignal.timeout(8000)
  });
  if (!res.ok) {
    throw new Error(`polymarket markets fetch failed: ${res.status}`);
  }
  const body: unknown = await res.json();
  const rows: PolymarketGammaMarket[] = Array.isArray(body)
    ? (body as PolymarketGammaMarket[])
    : Array.isArray((body as { data?: unknown }).data)
      ? ((body as { data: PolymarketGammaMarket[] }).data)
      : [];
  const ts = new Date().toISOString();
  const out: MarketFlowSnapshot[] = [];
  for (const m of rows) {
    const prices = parseStringList(m.outcomePrices);
    const outcomes = parseStringList(m.outcomes);
    const price =
      parseNumber(m.lastTradePrice) ??
      (prices && prices.length > 0 ? parseNumber(prices[0]) : undefined);
    const volume24h = parseNumber(m.volume24hr);
    const volumeTotal = parseNumber(m.volume);
    const liquidity = parseNumber(m.liquidity);
    const title = m.question ?? m.title ?? m.slug ?? "";
    const marketId = m.conditionId ?? (m.id !== undefined ? String(m.id) : undefined);
    if (!marketId || price === undefined || !title) continue;
    if (volume24h !== undefined && volume24h < minVolume) continue;
    out.push({
      venue: "polymarket",
      marketId,
      slug: m.slug,
      title,
      outcome: outcomes && outcomes.length > 0 ? outcomes[0] : undefined,
      ts,
      price,
      volume24h,
      volumeTotal,
      liquidity
    });
  }
  return out;
}

interface KalshiMarket {
  ticker?: string;
  event_ticker?: string;
  title?: string;
  yes_sub_title?: string;
  last_price?: number;
  yes_bid?: number;
  yes_ask?: number;
  volume_24h?: number;
  volume?: number;
  liquidity?: number;
  open_interest?: number;
  status?: string;
}

export async function fetchKalshiActiveMarkets(
  opts: { limit?: number } = {}
): Promise<MarketFlowSnapshot[]> {
  const limit = opts.limit ?? 100;
  const url = `${KALSHI_API}?limit=${limit}&status=open`;
  const res = await fetch(url, {
    headers: FETCH_HEADERS,
    signal: AbortSignal.timeout(8000)
  });
  if (!res.ok) {
    throw new Error(`kalshi markets fetch failed: ${res.status}`);
  }
  const body = (await res.json()) as { markets?: KalshiMarket[] };
  const rows = Array.isArray(body.markets) ? body.markets : [];
  const ts = new Date().toISOString();
  const out: MarketFlowSnapshot[] = [];
  for (const m of rows) {
    const ticker = m.ticker;
    if (!ticker) continue;
    const rawPrice =
      parseNumber(m.last_price) ??
      (m.yes_bid !== undefined && m.yes_ask !== undefined
        ? (m.yes_bid + m.yes_ask) / 2
        : parseNumber(m.yes_bid) ?? parseNumber(m.yes_ask));
    if (rawPrice === undefined) continue;
    const price = rawPrice > 1 ? rawPrice / 100 : rawPrice;
    out.push({
      venue: "kalshi",
      marketId: ticker,
      slug: ticker,
      title: m.title ?? m.yes_sub_title ?? ticker,
      outcome: "YES",
      ts,
      price,
      volume24h: parseNumber(m.volume_24h),
      volumeTotal: parseNumber(m.volume),
      liquidity: parseNumber(m.liquidity)
    });
  }
  return out;
}

export async function appendFlowSnapshots(
  path: string,
  rows: MarketFlowSnapshot[]
): Promise<void> {
  if (rows.length === 0) return;
  await mkdir(dirname(path), { recursive: true });
  const payload = rows.map((r) => JSON.stringify(r)).join("\n") + "\n";
  await appendFile(path, payload, "utf8");
}

export async function loadFlowHistory(
  path: string,
  opts: { maxAgeHours?: number } = {}
): Promise<Map<string, MarketFlowSnapshot[]>> {
  const map = new Map<string, MarketFlowSnapshot[]>();
  let raw: string;
  try {
    raw = await readFile(path, "utf8");
  } catch (err) {
    if ((err as NodeJS.ErrnoException).code === "ENOENT") return map;
    throw err;
  }
  const cutoff =
    opts.maxAgeHours !== undefined ? Date.now() - opts.maxAgeHours * 3_600_000 : undefined;
  for (const line of raw.split(/\r?\n/)) {
    const trimmed = line.trim();
    if (!trimmed) continue;
    let parsed: MarketFlowSnapshot;
    try {
      parsed = JSON.parse(trimmed) as MarketFlowSnapshot;
    } catch {
      continue;
    }
    if (!parsed || !parsed.venue || !parsed.marketId || !parsed.ts) continue;
    if (cutoff !== undefined && Date.parse(parsed.ts) < cutoff) continue;
    const key = `${parsed.venue}:${parsed.marketId}`;
    const list = map.get(key);
    if (list) list.push(parsed);
    else map.set(key, [parsed]);
  }
  return map;
}

export async function collectFlowSnapshots(opts: { limitPerVenue?: number; pacingMs?: number } = {}): Promise<MarketFlowSnapshot[]> {
  const limit = opts.limitPerVenue ?? 100;
  const pacing = opts.pacingMs ?? 200;
  const poly = await fetchPolymarketActiveMarkets({ limit });
  await new Promise((r) => setTimeout(r, pacing));
  const kalshi = await fetchKalshiActiveMarkets({ limit });
  return [...poly, ...kalshi];
}

export async function scanFlowAcceleration(args: {
  historyPath: string;
  outputPath: string;
  windowHours?: number;
  minCompositeScore?: number;
}): Promise<{ scored: number; flagged: number; topSignals: FlowAccelerationScore[] }> {
  const windowHours = args.windowHours ?? 12;
  const minScore = args.minCompositeScore ?? DEFAULT_MIN_COMPOSITE_SCORE;
  const history = await loadFlowHistory(args.historyPath, { maxAgeHours: windowHours * 2 });
  const scored: FlowAccelerationScore[] = [];
  for (const snaps of history.values()) {
    const s = computeFlowAcceleration(snaps, { windowHours });
    if (s) scored.push(s);
  }
  scored.sort((a, b) => b.compositeScore - a.compositeScore);
  const flagged = scored.filter((s) => s.compositeScore >= minScore);
  if (flagged.length > 0) {
    await mkdir(dirname(args.outputPath), { recursive: true });
    const ts = new Date().toISOString();
    const payload =
      flagged.map((s) => JSON.stringify({ ts, ...s })).join("\n") + "\n";
    await appendFile(args.outputPath, payload, "utf8");
  }
  return {
    scored: scored.length,
    flagged: flagged.length,
    topSignals: scored.slice(0, 10)
  };
}
