import { mkdir, readFile, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";

export interface GengarSignalRecord {
  ts: string;
  period?: string;
  side: "UP" | "DOWN";
  marketPrice: number;
  recommendedBet?: number;
  secondsElapsed: number;
  secondsRemaining: number;
  btcOpen: number;
}

export interface ResolvedGengarSignal extends GengarSignalRecord {
  windowStartMs: number;
  windowEndMs: number;
  btcClose: number | null;
  won: boolean | null;
  unitPnl: number | null;
  stakePnl: number | null;
}

export interface GengarEdgeAuditBucket {
  key: string;
  count: number;
  resolved: number;
  winRate: number;
  avgUnitPnl: number;
  avgStakePnl: number;
  totalStakePnl: number;
}

export interface GengarEdgeAuditReport {
  command: "gengar-edge-audit";
  generatedAt: string;
  inputPath: string;
  outputPath?: string;
  totalSignals: number;
  resolvedSignals: number;
  pendingSignals: number;
  duplicateWindowSignals: number;
  overall: GengarEdgeAuditBucket;
  firstSignalPerWindow: GengarEdgeAuditBucket;
  byPeriod: GengarEdgeAuditBucket[];
  bySide: GengarEdgeAuditBucket[];
  byPriceBucket: GengarEdgeAuditBucket[];
  bySecondsRemainingBucket: GengarEdgeAuditBucket[];
  latestResolved: ResolvedGengarSignal[];
  warnings: string[];
}

function parseJsonl(raw: string): GengarSignalRecord[] {
  return raw
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => JSON.parse(line) as GengarSignalRecord)
    .filter((row) => (row.side === "UP" || row.side === "DOWN") && Number.isFinite(row.marketPrice) && Number.isFinite(row.btcOpen));
}

function periodSeconds(record: GengarSignalRecord): number {
  if (record.period === "15m") return 900;
  if (record.period === "1h") return 3_600;
  return Math.max(60, Math.round((record.secondsElapsed + record.secondsRemaining) || 300));
}

function windowTimes(record: GengarSignalRecord): { startMs: number; endMs: number } {
  const tsMs = Date.parse(record.ts);
  const periodMs = periodSeconds(record) * 1_000;
  const estimatedStartMs = tsMs - Math.round(record.secondsElapsed * 1_000);
  const startMs = Math.floor(estimatedStartMs / periodMs) * periodMs;
  return {
    startMs,
    endMs: startMs + periodMs
  };
}

async function fetchBinanceCloseAt(endMs: number): Promise<number | null> {
  const startTime = Math.max(0, endMs - 60_000);
  const url = new URL("https://api.binance.com/api/v3/klines");
  url.searchParams.set("symbol", "BTCUSDT");
  url.searchParams.set("interval", "1m");
  url.searchParams.set("startTime", String(startTime));
  url.searchParams.set("endTime", String(endMs + 120_000));
  url.searchParams.set("limit", "3");
  const resp = await fetch(url, { signal: AbortSignal.timeout(8_000) });
  if (!resp.ok) return null;
  const rows = await resp.json() as unknown[];
  if (!Array.isArray(rows) || rows.length === 0) return null;
  const eligible = rows
    .filter((row): row is unknown[] => Array.isArray(row) && Number(row[6]) <= endMs + 90_000)
    .sort((a, b) => Math.abs(Number(a[6]) - endMs) - Math.abs(Number(b[6]) - endMs));
  const close = Number(eligible[0]?.[4]);
  return Number.isFinite(close) ? close : null;
}

function bucketPrice(price: number): string {
  if (price < 0.6) return "<0.60";
  if (price < 0.7) return "0.60-0.70";
  if (price < 0.8) return "0.70-0.80";
  if (price < 0.9) return "0.80-0.90";
  return ">=0.90";
}

function bucketSeconds(seconds: number): string {
  if (seconds < 60) return "<60s";
  if (seconds < 120) return "60-120s";
  if (seconds < 180) return "120-180s";
  if (seconds < 240) return "180-240s";
  return ">=240s";
}

function summarize(key: string, rows: ResolvedGengarSignal[]): GengarEdgeAuditBucket {
  const resolved = rows.filter((row) => row.unitPnl !== null);
  const wins = resolved.filter((row) => row.won === true).length;
  const unitPnl = resolved.reduce((sum, row) => sum + (row.unitPnl ?? 0), 0);
  const stakePnl = resolved.reduce((sum, row) => sum + (row.stakePnl ?? 0), 0);
  return {
    key,
    count: rows.length,
    resolved: resolved.length,
    winRate: resolved.length > 0 ? Number((wins / resolved.length).toFixed(4)) : 0,
    avgUnitPnl: resolved.length > 0 ? Number((unitPnl / resolved.length).toFixed(4)) : 0,
    avgStakePnl: resolved.length > 0 ? Number((stakePnl / resolved.length).toFixed(4)) : 0,
    totalStakePnl: Number(stakePnl.toFixed(4))
  };
}

function groupBy(rows: ResolvedGengarSignal[], keyFn: (row: ResolvedGengarSignal) => string): GengarEdgeAuditBucket[] {
  const groups = new Map<string, ResolvedGengarSignal[]>();
  for (const row of rows) {
    const key = keyFn(row);
    groups.set(key, [...(groups.get(key) ?? []), row]);
  }
  return Array.from(groups.entries())
    .map(([key, group]) => summarize(key, group))
    .sort((a, b) => b.resolved - a.resolved || b.avgUnitPnl - a.avgUnitPnl);
}

export async function buildGengarEdgeAudit(args: {
  inputPath?: string;
  outputPath?: string;
  maxSignals?: number;
} = {}): Promise<GengarEdgeAuditReport> {
  const inputPath = resolve(args.inputPath ?? ".rumbling-hedge/journal/gengar-signals.jsonl");
  const raw = await readFile(inputPath, "utf8").catch(() => "");
  const signals = parseJsonl(raw).slice(-(args.maxSignals ?? 2_000));
  const closeByWindow = new Map<number, number | null>();
  const resolved: ResolvedGengarSignal[] = [];

  for (const signal of signals) {
    const { startMs, endMs } = windowTimes(signal);
    const now = Date.now();
    let btcClose: number | null = null;
    if (now >= endMs + 90_000) {
      if (!closeByWindow.has(endMs)) {
        closeByWindow.set(endMs, await fetchBinanceCloseAt(endMs));
      }
      btcClose = closeByWindow.get(endMs) ?? null;
    }
    const won = btcClose === null ? null : signal.side === "UP" ? btcClose > signal.btcOpen : btcClose <= signal.btcOpen;
    const unitPnl = won === null ? null : won ? 1 - signal.marketPrice : -signal.marketPrice;
    const stake = Number.isFinite(signal.recommendedBet) ? Number(signal.recommendedBet) : 1;
    const stakePnl = unitPnl === null ? null : unitPnl * stake;
    resolved.push({
      ...signal,
      windowStartMs: startMs,
      windowEndMs: endMs,
      btcClose,
      won,
      unitPnl: unitPnl === null ? null : Number(unitPnl.toFixed(4)),
      stakePnl: stakePnl === null ? null : Number(stakePnl.toFixed(4))
    });
  }

  const resolvedRows = resolved.filter((row) => row.unitPnl !== null);
  const seenWindows = new Set<string>();
  const firstSignalsPerWindow: ResolvedGengarSignal[] = [];
  let duplicateWindowSignals = 0;
  for (const row of resolved) {
    const key = `${row.period ?? "5m"}:${row.windowStartMs}:${row.side}`;
    if (seenWindows.has(key)) {
      duplicateWindowSignals += 1;
    } else {
      firstSignalsPerWindow.push(row);
    }
    seenWindows.add(key);
  }

  const report: GengarEdgeAuditReport = {
    command: "gengar-edge-audit",
    generatedAt: new Date().toISOString(),
    inputPath,
    outputPath: args.outputPath ? resolve(args.outputPath) : undefined,
    totalSignals: resolved.length,
    resolvedSignals: resolvedRows.length,
    pendingSignals: resolved.length - resolvedRows.length,
    duplicateWindowSignals,
    overall: summarize("overall", resolved),
    firstSignalPerWindow: summarize("first-signal-per-window", firstSignalsPerWindow),
    byPeriod: groupBy(resolved, (row) => row.period ?? "5m"),
    bySide: groupBy(resolved, (row) => row.side),
    byPriceBucket: groupBy(resolved, (row) => bucketPrice(row.marketPrice)),
    bySecondsRemainingBucket: groupBy(resolved, (row) => bucketSeconds(row.secondsRemaining)),
    latestResolved: resolvedRows.slice(-20),
    warnings: [
      ...(duplicateWindowSignals > 0 ? [`${duplicateWindowSignals} repeated signals share the same period/window/side; use first-signal-per-window before estimating deployable capacity.`] : []),
      ...(resolvedRows.length < 30 ? ["resolved sample is still too small for live sizing"] : []),
      "this audit resolves BTC direction only; it does not prove Polymarket fillability, fees, or adverse selection"
    ]
  };

  if (args.outputPath) {
    const outputPath = resolve(args.outputPath);
    await mkdir(dirname(outputPath), { recursive: true });
    await writeFile(outputPath, `${JSON.stringify(report, null, 2)}\n`, "utf8");
  }

  return report;
}
