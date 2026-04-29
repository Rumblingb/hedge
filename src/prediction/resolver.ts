import { appendFile, mkdir, readFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { setTimeout as sleep } from "node:timers/promises";
import type { PredictionCandidate } from "./types.js";

export interface VenueResolution {
  resolved: boolean;
  outcome?: string;
  closedAt?: string;
  raw?: unknown;
}

export interface CandidateIdParts {
  venueA: string;
  externalIdA: string;
  venueB: string;
  externalIdB: string;
}

export interface ResolvedJournalRow extends PredictionCandidate {
  resolvedAt: string;
  venueAOutcome?: string;
  venueBOutcome?: string;
  venueAClosedAt?: string;
  venueBClosedAt?: string;
  settlementMismatch: boolean;
  realizedGrossEdgePct: number;
  realizedNetEdgePct: number;
  calibrationBucket: string;
}

export interface CalibrationBucket {
  predictedEdgeBucket: string;
  n: number;
  realizedEdgePctMean: number;
}

export interface CalibrationReport {
  generatedAt: string;
  totalResolved: number;
  hitRatePct: number;
  meanRealizedEdgePct: number;
  settlementMismatches: number;
  buckets: CalibrationBucket[];
}

const POLYMARKET_GAMMA = "https://gamma-api.polymarket.com/markets";
const KALSHI_BASE = "https://api.elections.kalshi.com/trade-api/v2/markets";
const MANIFOLD_BASE = "https://api.manifold.markets/v0/market";

function safeFetchJson(url: string, timeoutMs = 8000): Promise<unknown | null> {
  return fetch(url, { signal: AbortSignal.timeout(timeoutMs) })
    .then(async (r) => (r.ok ? r.json() : null))
    .catch(() => null);
}

export function parseCandidateId(id: string): CandidateIdParts | null {
  const halves = id.split("__");
  if (halves.length !== 2) return null;
  const [a, b] = halves.map((h) => {
    const idx = h.indexOf(":");
    if (idx <= 0) return null;
    return { venue: h.slice(0, idx), externalId: h.slice(idx + 1) };
  });
  if (!a || !b) return null;
  return { venueA: a.venue, externalIdA: a.externalId, venueB: b.venue, externalIdB: b.externalId };
}

export async function resolvePolymarketMarket(marketId: string): Promise<VenueResolution> {
  const url = `${POLYMARKET_GAMMA}?id=${encodeURIComponent(marketId)}`;
  const payload = (await safeFetchJson(url)) as unknown;
  if (!payload) return { resolved: false };
  const record = Array.isArray(payload) ? payload[0] : payload;
  if (!record || typeof record !== "object") return { resolved: false };
  const r = record as Record<string, unknown>;
  const closed = r.closed === true;
  if (!closed) return { resolved: false };
  let outcomeLabel: string | undefined;
  try {
    const prices = typeof r.outcomePrices === "string" ? (JSON.parse(r.outcomePrices) as unknown) : r.outcomePrices;
    const labels = typeof r.outcomes === "string" ? (JSON.parse(r.outcomes) as unknown) : r.outcomes;
    if (Array.isArray(prices) && Array.isArray(labels) && prices.length === labels.length) {
      let winIdx = -1;
      let winVal = -1;
      prices.forEach((p, i) => {
        const v = typeof p === "number" ? p : typeof p === "string" ? Number.parseFloat(p) : NaN;
        if (Number.isFinite(v) && v > winVal) {
          winVal = v;
          winIdx = i;
        }
      });
      if (winIdx >= 0 && typeof labels[winIdx] === "string") outcomeLabel = labels[winIdx] as string;
    }
  } catch {
    // ignore
  }
  const closedAt = typeof r.closedTime === "string" ? r.closedTime : typeof r.endDate === "string" ? r.endDate : undefined;
  return { resolved: true, outcome: outcomeLabel, closedAt, raw: record };
}

export async function resolveKalshiMarket(ticker: string): Promise<VenueResolution> {
  const payload = (await safeFetchJson(`${KALSHI_BASE}/${encodeURIComponent(ticker)}`)) as unknown;
  if (!payload || typeof payload !== "object") return { resolved: false };
  const wrapped = (payload as { market?: unknown }).market ?? payload;
  if (!wrapped || typeof wrapped !== "object") return { resolved: false };
  const m = wrapped as Record<string, unknown>;
  const status = typeof m.status === "string" ? m.status.toLowerCase() : "";
  const finalized = status === "finalized" || status === "settled" || status === "resolved";
  if (!finalized) return { resolved: false };
  const result = typeof m.result === "string" ? m.result.toLowerCase() : undefined;
  const closedAt = typeof m.close_time === "string" ? m.close_time : typeof m.expiration_time === "string" ? m.expiration_time : undefined;
  return { resolved: true, outcome: result, closedAt, raw: wrapped };
}

export async function resolveManifoldMarket(idOrSlug: string): Promise<VenueResolution> {
  const payload = (await safeFetchJson(`${MANIFOLD_BASE}/${encodeURIComponent(idOrSlug)}`)) as unknown;
  if (!payload || typeof payload !== "object") return { resolved: false };
  const m = payload as Record<string, unknown>;
  if (m.isResolved !== true) return { resolved: false };
  const outcome = typeof m.resolution === "string" ? m.resolution.toLowerCase() : undefined;
  const t = typeof m.resolutionTime === "number" ? new Date(m.resolutionTime).toISOString() : undefined;
  return { resolved: true, outcome, closedAt: t, raw: m };
}

export async function resolveVenue(venue: string, externalId: string): Promise<VenueResolution> {
  switch (venue.toLowerCase()) {
    case "polymarket":
      return resolvePolymarketMarket(externalId);
    case "kalshi":
      return resolveKalshiMarket(externalId);
    case "manifold":
      return resolveManifoldMarket(externalId);
    default:
      return { resolved: false };
  }
}

function normalizeOutcomeLabel(label: string | undefined): string | undefined {
  if (!label) return undefined;
  const s = label.trim().toLowerCase();
  if (s === "yes" || s === "true" || s === "y") return "yes";
  if (s === "no" || s === "false" || s === "n") return "no";
  return s;
}

function edgeBucket(edgePct: number): string {
  if (!Number.isFinite(edgePct)) return "nan";
  if (edgePct < 0) return "<0";
  if (edgePct < 2) return "0-2";
  if (edgePct < 5) return "2-5";
  return "5+";
}

function computeRealizedEdge(row: PredictionCandidate, a: VenueResolution, b: VenueResolution): { gross: number; net: number; mismatch: boolean } {
  const aOut = normalizeOutcomeLabel(a.outcome);
  const bOut = normalizeOutcomeLabel(b.outcome);
  const predicted = normalizeOutcomeLabel(row.normalizedOutcomeKey) ?? normalizeOutcomeLabel(row.outcomeA);
  const mismatch = Boolean(aOut && bOut && aOut !== bOut);
  if (mismatch) {
    return { gross: -row.feeDragPct, net: -row.feeDragPct, mismatch: true };
  }
  const settled = aOut ?? bOut;
  if (!settled || !predicted) {
    return { gross: 0, net: 0, mismatch: false };
  }
  if (settled === predicted) {
    const gross = row.grossEdgePct;
    return { gross, net: gross - row.feeDragPct, mismatch: false };
  }
  const gross = -Math.max(row.grossEdgePct, 1);
  return { gross, net: gross - row.feeDragPct, mismatch: false };
}

async function readJsonl<T>(path: string): Promise<T[]> {
  const buf = await readFile(path, "utf8");
  const out: T[] = [];
  for (const line of buf.split("\n")) {
    const t = line.trim();
    if (!t) continue;
    try {
      out.push(JSON.parse(t) as T);
    } catch {
      // skip malformed
    }
  }
  return out;
}

async function appendJsonl(path: string, rows: unknown[]): Promise<void> {
  if (rows.length === 0) return;
  await mkdir(dirname(path), { recursive: true });
  const body = rows.map((r) => JSON.stringify(r)).join("\n") + "\n";
  await appendFile(path, body, "utf8");
}

export async function resolvePredictionJournal(args: {
  journalPath: string;
  outputPath: string;
  maxAgeDays?: number;
  pacingMs?: number;
  now?: Date;
}): Promise<{ inspected: number; resolved: number; skipped: number; mismatches: number }> {
  const now = args.now ?? new Date();
  const pacingMs = args.pacingMs ?? 150;
  const maxAgeMs = (args.maxAgeDays ?? 60) * 86_400_000;
  const journalPath = resolve(args.journalPath);
  const outputPath = resolve(args.outputPath);

  const rows = await readJsonl<PredictionCandidate>(journalPath);
  const alreadyResolved = new Set<string>();
  try {
    const existing = await readJsonl<ResolvedJournalRow>(outputPath);
    for (const e of existing) alreadyResolved.add(`${e.candidateId}:${e.ts}`);
  } catch {
    // no existing file is fine
  }

  const resolvedRows: ResolvedJournalRow[] = [];
  let inspected = 0;
  let skipped = 0;
  let mismatches = 0;

  for (const row of rows) {
    inspected += 1;
    const key = `${row.candidateId}:${row.ts}`;
    if (alreadyResolved.has(key)) {
      skipped += 1;
      continue;
    }
    const rowTs = Date.parse(row.ts);
    if (Number.isFinite(rowTs) && now.getTime() - rowTs > maxAgeMs) {
      skipped += 1;
      continue;
    }
    const expiry = row.expiryA ?? row.expiryB;
    if (expiry) {
      const expiryMs = Date.parse(expiry);
      if (Number.isFinite(expiryMs) && expiryMs > now.getTime()) {
        skipped += 1;
        continue;
      }
    } else {
      skipped += 1;
      continue;
    }

    const parts = parseCandidateId(row.candidateId);
    if (!parts) {
      skipped += 1;
      continue;
    }
    const a = await resolveVenue(parts.venueA, parts.externalIdA);
    if (pacingMs) await sleep(pacingMs);
    const b = await resolveVenue(parts.venueB, parts.externalIdB);
    if (pacingMs) await sleep(pacingMs);

    if (!a.resolved && !b.resolved) {
      skipped += 1;
      continue;
    }
    const edges = computeRealizedEdge(row, a, b);
    if (edges.mismatch) mismatches += 1;
    const resolvedRow: ResolvedJournalRow = {
      ...row,
      resolvedAt: new Date().toISOString(),
      venueAOutcome: a.outcome,
      venueBOutcome: b.outcome,
      venueAClosedAt: a.closedAt,
      venueBClosedAt: b.closedAt,
      settlementMismatch: edges.mismatch,
      realizedGrossEdgePct: edges.gross,
      realizedNetEdgePct: edges.net,
      calibrationBucket: edgeBucket(row.netEdgePct)
    };
    resolvedRows.push(resolvedRow);
  }

  await appendJsonl(outputPath, resolvedRows);
  return { inspected, resolved: resolvedRows.length, skipped, mismatches };
}

export function buildCalibrationReport(rows: ResolvedJournalRow[]): CalibrationReport {
  const total = rows.length;
  if (total === 0) {
    return { generatedAt: new Date().toISOString(), totalResolved: 0, hitRatePct: 0, meanRealizedEdgePct: 0, settlementMismatches: 0, buckets: [] };
  }
  const mismatches = rows.filter((r) => r.settlementMismatch).length;
  const wins = rows.filter((r) => r.realizedNetEdgePct > 0).length;
  const meanRealized = rows.reduce((acc, r) => acc + r.realizedNetEdgePct, 0) / total;
  const buckets = new Map<string, { n: number; sum: number }>();
  for (const r of rows) {
    const b = r.calibrationBucket;
    const existing = buckets.get(b) ?? { n: 0, sum: 0 };
    existing.n += 1;
    existing.sum += r.realizedNetEdgePct;
    buckets.set(b, existing);
  }
  const bucketOrder = ["<0", "0-2", "2-5", "5+", "nan"];
  const bucketArr: CalibrationBucket[] = [];
  for (const key of bucketOrder) {
    const b = buckets.get(key);
    if (!b) continue;
    bucketArr.push({ predictedEdgeBucket: key, n: b.n, realizedEdgePctMean: b.sum / b.n });
  }
  return {
    generatedAt: new Date().toISOString(),
    totalResolved: total,
    hitRatePct: (wins / total) * 100,
    meanRealizedEdgePct: meanRealized,
    settlementMismatches: mismatches,
    buckets: bucketArr
  };
}

export async function buildCalibrationReportFromJsonl(path: string): Promise<CalibrationReport> {
  const rows = await readJsonl<ResolvedJournalRow>(path);
  return buildCalibrationReport(rows);
}
