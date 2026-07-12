import { readdir } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fetchFreeBars, type FreeDataProvider, type FreeInterval, writeBarsCsv } from "../data/freeSources.js";
import { inspectBarsFromCsv, loadBarsFromCsv, type CsvInspection } from "../data/csv.js";
import { normalizeUniverseByInnerTimestamp } from "../data/normalize.js";
import { chicagoDateKey } from "../utils/time.js";

export const DEFAULT_FUTURES_LOOP_SYMBOLS = ["NQ", "ES", "CL", "GC", "6E", "ZN"] as const;

export interface FuturesLoopRefreshConfig {
  enabled: boolean;
  interval: FreeInterval;
  range: string;
  provider: FreeDataProvider;
  requestTimeoutMs: number;
  maxStaleHours: number;
  minDistinctDays: number;
  symbols: string[];
  outDir?: string;
}

export interface FuturesDatasetStatus {
  path: string;
  exists: boolean;
  inspection: CsvInspection | null;
  distinctDays: number;
  staleHours: number | null;
  shouldRefresh: boolean;
  reasons: string[];
}

export interface FuturesDatasetRefreshReport {
  rawPath: string;
  normalizedPath: string;
  successfulSymbols: number;
  failedSymbols: number;
  outputs: Array<{
    symbol: string;
    providerUsed?: string;
    bars?: number;
    error?: string;
  }>;
}

interface PartialRefreshMergeResult {
  path: string;
  carriedSymbols: string[];
  missingSymbols: string[];
  staleSymbols: string[];
}

export interface PreparedFuturesDataset {
  selectedPath: string;
  status: FuturesDatasetStatus;
  refreshed: boolean;
  refreshReport: FuturesDatasetRefreshReport | null;
  warnings: string[];
}

interface RankedDatasetCandidate {
  path: string;
  status: FuturesDatasetStatus;
  score: number;
}

type RefreshSuccess = {
  symbol: string;
  providerUsed: Awaited<ReturnType<typeof fetchFreeBars>>["providerUsed"];
  bars: number;
  result: Awaited<ReturnType<typeof fetchFreeBars>>;
};

type RefreshFailure = {
  symbol: string;
  error: string;
};

function parsePositiveInt(value: string | undefined, fallback: number): number {
  const parsed = Number.parseInt(value ?? "", 10);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : fallback;
}

export function buildFuturesLoopRefreshConfigFromEnv(env: NodeJS.ProcessEnv = process.env): FuturesLoopRefreshConfig {
  const rawSymbols = (env.BILL_FUTURES_SYMBOLS ?? DEFAULT_FUTURES_LOOP_SYMBOLS.join(","))
    .split(",")
    .map((value) => value.trim().toUpperCase())
    .filter(Boolean);

  return {
    enabled: (env.BILL_FUTURES_LOOP_REFRESH_ENABLED ?? "true").toLowerCase() !== "false",
    interval: (env.BILL_FUTURES_LOOP_REFRESH_INTERVAL ?? "1m") as FreeInterval,
    range: env.BILL_FUTURES_LOOP_REFRESH_RANGE ?? "10d",
    provider: (env.BILL_FUTURES_LOOP_REFRESH_PROVIDER ?? "auto") as FreeDataProvider,
    requestTimeoutMs: parsePositiveInt(env.BILL_FUTURES_LOOP_REFRESH_TIMEOUT_MS, 5_000),
    maxStaleHours: parsePositiveInt(env.BILL_FUTURES_LOOP_REFRESH_MAX_STALE_HOURS, 6),
    minDistinctDays: parsePositiveInt(env.BILL_FUTURES_LOOP_MIN_DISTINCT_DAYS, 7),
    symbols: rawSymbols.length > 0 ? rawSymbols : [...DEFAULT_FUTURES_LOOP_SYMBOLS],
    outDir: env.BILL_FUTURES_LOOP_REFRESH_OUT_DIR
  };
}

export async function assessFuturesDatasetStatus(args: {
  csvPath: string;
  now?: Date;
  maxStaleHours: number;
  minDistinctDays: number;
}): Promise<FuturesDatasetStatus> {
  const targetPath = resolve(args.csvPath);
  const now = args.now ?? new Date();

  try {
    const inspection = await inspectBarsFromCsv(targetPath);
    const bars = await loadBarsFromCsv(targetPath);
    const distinctDays = new Set(bars.map((bar) => chicagoDateKey(bar.ts))).size;
    const endMs = inspection.endTs ? Date.parse(inspection.endTs) : Number.NaN;
    const staleHours = Number.isFinite(endMs)
      ? Number((((now.getTime() - endMs) / 3_600_000)).toFixed(2))
      : null;
    const reasons: string[] = [];

    if ((inspection.dataRows ?? 0) === 0) {
      reasons.push("dataset is empty");
    }
    if (inspection.issues.length > 0) {
      reasons.push(`csv inspection found ${inspection.issues.length} issue(s)`);
    }
    if (distinctDays < args.minDistinctDays) {
      reasons.push(`dataset has only ${distinctDays} distinct day(s), below the ${args.minDistinctDays}-day minimum`);
    }
    if (staleHours !== null && staleHours > args.maxStaleHours) {
      reasons.push(`dataset end timestamp is ${staleHours} hour(s) old`);
    }

    return {
      path: targetPath,
      exists: true,
      inspection,
      distinctDays,
      staleHours,
      shouldRefresh: reasons.length > 0,
      reasons
    };
  } catch (error) {
    return {
      path: targetPath,
      exists: false,
      inspection: null,
      distinctDays: 0,
      staleHours: null,
      shouldRefresh: true,
      reasons: [
        error instanceof Error
          ? `dataset is unreadable: ${error.message}`
          : "dataset is unreadable"
      ]
    };
  }
}

export async function refreshFuturesDataset(args: {
  config: FuturesLoopRefreshConfig;
  outDir: string;
}): Promise<FuturesDatasetRefreshReport> {
  const outputs: Array<RefreshSuccess | RefreshFailure> = await Promise.all(args.config.symbols.map(async (symbol) => {
    try {
      const result = await fetchFreeBars({
        symbol,
        interval: args.config.interval,
        range: args.config.range,
        provider: args.config.provider,
        timeoutMs: args.config.requestTimeoutMs
      });
      return {
        symbol,
        providerUsed: result.providerUsed,
        bars: result.bars.length,
        result
      };
    } catch (error) {
      return {
        symbol,
        error: error instanceof Error ? error.message : String(error)
      };
    }
  }));

  const failed = outputs.filter((output): output is RefreshFailure => "error" in output);
  const successful = outputs.filter((output): output is RefreshSuccess => "result" in output);
  if (successful.length === 0) {
    throw new Error(failed.map((entry) => `${entry.symbol}: ${entry.error}`).join(" | "));
  }

  const combined = successful.flatMap((output) => output.result.bars);
  const rawPath = resolve(args.outDir, `ALL-${args.config.symbols.length}MARKETS-${args.config.interval}-${args.config.range}.csv`);
  const normalizedPath = rawPath.replace(/\.csv$/i, "-normalized.csv");
  await writeBarsCsv({ bars: combined, outPath: rawPath });
  const normalized = normalizeUniverseByInnerTimestamp(combined);
  await writeBarsCsv({ bars: normalized.bars, outPath: normalizedPath });

  return {
    rawPath,
    normalizedPath,
    successfulSymbols: successful.length,
    failedSymbols: failed.length,
    outputs: outputs.map((output) => "result" in output
      ? {
          symbol: output.symbol,
          providerUsed: output.providerUsed,
          bars: output.bars
        }
      : {
          symbol: output.symbol,
          error: output.error
        })
  };
}

async function mergePartialRefreshWithExistingDataset(args: {
  refreshReport: FuturesDatasetRefreshReport;
  existingPath: string;
  maxStaleHours: number;
  now?: Date;
}): Promise<PartialRefreshMergeResult | null> {
  const failedSymbols = args.refreshReport.outputs
    .filter((output) => typeof output.error === "string")
    .map((output) => output.symbol);
  if (failedSymbols.length === 0) {
    return null;
  }

  const freshBars = await loadBarsFromCsv(args.refreshReport.normalizedPath).catch(() => []);
  const existingBars = await loadBarsFromCsv(args.existingPath).catch(() => []);
  if (freshBars.length === 0 || existingBars.length === 0) {
    return null;
  }

  const nowMs = (args.now ?? new Date()).getTime();
  const maxStaleMs = args.maxStaleHours * 3_600_000;
  const failedSet = new Set(failedSymbols);
  const latestTsBySymbol = new Map<string, number>();
  for (const bar of existingBars) {
    if (!failedSet.has(bar.symbol)) {
      continue;
    }
    const ts = Date.parse(bar.ts);
    if (!Number.isFinite(ts)) {
      continue;
    }
    latestTsBySymbol.set(bar.symbol, Math.max(latestTsBySymbol.get(bar.symbol) ?? 0, ts));
  }

  const carryableSymbols = failedSymbols.filter((symbol) => {
    const latestTs = latestTsBySymbol.get(symbol);
    return latestTs !== undefined && (nowMs - latestTs) <= maxStaleMs;
  });
  const staleSymbols = failedSymbols.filter((symbol) => {
    const latestTs = latestTsBySymbol.get(symbol);
    return latestTs !== undefined && (nowMs - latestTs) > maxStaleMs;
  });
  const carryableSet = new Set(carryableSymbols);
  const carriedBars = existingBars.filter((bar) => carryableSet.has(bar.symbol));
  const carriedSymbols = Array.from(new Set(carriedBars.map((bar) => bar.symbol))).sort();
  if (carriedSymbols.length === 0) {
    return {
      path: args.refreshReport.normalizedPath,
      carriedSymbols: [],
      missingSymbols: failedSymbols.filter((symbol) => !latestTsBySymbol.has(symbol)),
      staleSymbols
    };
  }

  const merged = normalizeUniverseByInnerTimestamp([...freshBars, ...carriedBars]);
  await writeBarsCsv({
    bars: merged.bars,
    outPath: args.refreshReport.normalizedPath
  });

  return {
    path: args.refreshReport.normalizedPath,
    carriedSymbols,
    missingSymbols: failedSymbols.filter((symbol) => !carriedSymbols.includes(symbol) && !staleSymbols.includes(symbol)),
    staleSymbols
  };
}

async function listNormalizedDatasetCandidates(dir: string): Promise<string[]> {
  try {
    const names = await readdir(dir);
    return names
      .filter((name) => name.endsWith("-normalized.csv"))
      .map((name) => resolve(dir, name));
  } catch {
    return [];
  }
}

function rankDatasetCandidate(status: FuturesDatasetStatus, config: FuturesLoopRefreshConfig): number {
  const presentSymbols = new Set(status.inspection?.symbols ?? []);
  const matchedSymbols = config.symbols.filter((symbol) => presentSymbols.has(symbol)).length;
  const symbolCoverageScore = matchedSymbols * 1_000_000_000;
  const freshnessScore = status.shouldRefresh ? 0 : 1_000_000;
  const distinctDayScore = status.distinctDays * 1_000_000;
  const stalePenalty = status.staleHours === null ? -10_000_000 : -Math.round(status.staleHours * 100);
  const endTsScore = status.inspection?.endTs ? Date.parse(status.inspection.endTs) : 0;
  const existenceScore = status.exists ? 10_000_000_000_000 : -10_000_000_000_000;
  return existenceScore + symbolCoverageScore + freshnessScore + endTsScore + distinctDayScore + stalePenalty;
}

async function selectBestExistingDataset(args: {
  requestedPath: string;
  now?: Date;
  config: FuturesLoopRefreshConfig;
}): Promise<RankedDatasetCandidate | null> {
  const dir = dirname(args.requestedPath);
  const candidates = Array.from(new Set([
    args.requestedPath,
    ...(await listNormalizedDatasetCandidates(dir))
  ]));
  const ranked = (await Promise.all(candidates.map(async (candidatePath) => {
    const status = await assessFuturesDatasetStatus({
      csvPath: candidatePath,
      now: args.now,
      maxStaleHours: args.config.maxStaleHours,
      minDistinctDays: args.config.minDistinctDays
    });
    return {
      path: candidatePath,
      status,
      score: rankDatasetCandidate(status, args.config)
    } satisfies RankedDatasetCandidate;
  })))
    .filter((candidate) => candidate.status.exists)
    .sort((left, right) => right.score - left.score);

  return ranked[0] ?? null;
}

export async function prepareFuturesLoopDataset(args: {
  csvPath: string;
  env?: NodeJS.ProcessEnv;
  now?: Date;
}): Promise<PreparedFuturesDataset> {
  const env = args.env ?? process.env;
  const config = buildFuturesLoopRefreshConfigFromEnv(env);
  const csvPath = resolve(args.csvPath);
  const status = await assessFuturesDatasetStatus({
    csvPath,
    now: args.now,
    maxStaleHours: config.maxStaleHours,
    minDistinctDays: config.minDistinctDays
  });

  if (!config.enabled || !status.shouldRefresh) {
    return {
      selectedPath: csvPath,
      status,
      refreshed: false,
      refreshReport: null,
      warnings: []
    };
  }

  const outDir = resolve(config.outDir ?? dirname(csvPath));

  try {
    const refreshReport = await refreshFuturesDataset({
      config,
      outDir
    });
    const partialRefresh = refreshReport.failedSymbols > 0;
    const selectedCandidate = partialRefresh
      ? await selectBestExistingDataset({
          requestedPath: csvPath,
          now: args.now,
          config
        })
      : null;
    const mergedPartial = partialRefresh && selectedCandidate
      ? await mergePartialRefreshWithExistingDataset({
          refreshReport,
          existingPath: selectedCandidate.path,
          maxStaleHours: config.maxStaleHours,
          now: args.now
        })
      : null;
    const refreshedStatus = await assessFuturesDatasetStatus({
      csvPath: refreshReport.normalizedPath,
      now: args.now,
      maxStaleHours: config.maxStaleHours,
      minDistinctDays: config.minDistinctDays
    });
    const partialStatus = partialRefresh ? refreshedStatus : null;
    const mergedStatus = mergedPartial
      ? await assessFuturesDatasetStatus({
          csvPath: mergedPartial.path,
          now: args.now,
          maxStaleHours: config.maxStaleHours,
          minDistinctDays: config.minDistinctDays
        })
      : null;
    const degradedToPartial = Boolean(
      partialRefresh
      && partialStatus?.exists
      && partialStatus.shouldRefresh === false
      && (
        mergedPartial?.carriedSymbols.length === 0
        || (mergedStatus?.shouldRefresh ?? true)
      )
    );
    const refreshWarnings = [
      ...(partialRefresh
        ? degradedToPartial
          ? [`futures refresh completed for ${refreshReport.successfulSymbols}/${config.symbols.length} symbols; routing around degraded symbols and keeping the fresh active subset in service.`]
          : mergedPartial && mergedPartial.carriedSymbols.length > 0
          ? [`futures refresh completed for ${refreshReport.successfulSymbols}/${config.symbols.length} symbols; merged the last good bars for ${mergedPartial.carriedSymbols.join(", ")} into the fresh dataset.`]
          : [`futures refresh completed only for ${refreshReport.successfulSymbols}/${config.symbols.length} symbols; keeping the best available dataset in service.`]
        : []),
      ...(mergedPartial && mergedPartial.missingSymbols.length > 0
        ? [`partial refresh still lacks ${mergedPartial.missingSymbols.join(", ")} because no prior bars were available to carry forward.`]
        : []),
      ...(mergedPartial && mergedPartial.staleSymbols.length > 0
        ? [`partial refresh routed ${mergedPartial.staleSymbols.join(", ")} out of the active dataset because the last good carried bars were beyond the stale-hours threshold.`]
        : []),
      ...refreshReport.outputs
        .filter((output) => typeof output.error === "string")
        .map((output) => `${output.symbol}: ${output.error as string}`)
    ];

    const selectedPath = degradedToPartial
      ? refreshReport.normalizedPath
      : mergedPartial?.path ?? selectedCandidate?.path ?? refreshReport.normalizedPath;
    const selectedStatus = degradedToPartial
      ? partialStatus ?? refreshedStatus
      : mergedStatus ?? selectedCandidate?.status ?? refreshedStatus;

    return {
      selectedPath,
      status: selectedStatus,
      refreshed: true,
      refreshReport,
      warnings: refreshWarnings
    };
  } catch (error) {
    const warning = error instanceof Error ? error.message : String(error);
    const fallback = await selectBestExistingDataset({
      requestedPath: csvPath,
      now: args.now,
      config
    });
    if (!status.exists) {
      throw error;
    }

    return {
      selectedPath: fallback?.path ?? csvPath,
      status: fallback?.status ?? status,
      refreshed: false,
      refreshReport: null,
      warnings: [
        `futures data refresh failed, falling back to existing dataset: ${warning}`,
        ...(fallback && fallback.path !== csvPath ? [`using the freshest existing normalized dataset at ${fallback.path}`] : [])
      ]
    };
  }
}
