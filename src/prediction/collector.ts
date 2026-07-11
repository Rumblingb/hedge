import { readFile } from "node:fs/promises";
import { resolve } from "node:path";
import { fetchKalshiLiveSnapshot } from "./adapters/kalshi.js";
import { fetchManifoldLiveSnapshot } from "./adapters/manifold.js";
import { fetchPolymarketLiveSnapshot } from "./adapters/polymarket.js";
import { buildPredictionSourcePolicyFromEnv } from "./policy.js";
import type { PredictionMarketSnapshot, PredictionSourcePolicy } from "./types.js";

export interface PredictionCollectSourceDiagnostic {
  source: string;
  status: "live" | "fallback" | "disabled" | "empty";
  count: number;
  fallbackPath?: string;
  error?: string;
}

export interface PredictionCollectResult {
  markets: PredictionMarketSnapshot[];
  diagnostics: PredictionCollectSourceDiagnostic[];
  policy: PredictionSourcePolicy;
}

async function readSnapshotFallback(filePath: string): Promise<PredictionMarketSnapshot[]> {
  try {
    const raw = await readFile(resolve(filePath), "utf8");
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? (parsed as PredictionMarketSnapshot[]) : [];
  } catch {
    return [];
  }
}

async function collectOne(args: {
  source: string;
  enabled: boolean;
  fallbackPath: string;
  legacyFallbackPath?: string;
  fetcher: () => Promise<PredictionMarketSnapshot[]>;
}): Promise<{ rows: PredictionMarketSnapshot[]; diagnostic: PredictionCollectSourceDiagnostic }> {
  const { source, enabled, fallbackPath, legacyFallbackPath, fetcher } = args;
  if (!enabled) {
    return {
      rows: [],
      diagnostic: { source, status: "disabled", count: 0, fallbackPath },
    };
  }

  try {
    const rows = await fetcher();
    return {
      rows,
      diagnostic: {
        source,
        status: rows.length > 0 ? "live" : "empty",
        count: rows.length,
        fallbackPath,
      },
    };
  } catch (error) {
    const fallbackRows = await readSnapshotFallback(fallbackPath);
    const rows = fallbackRows.length > 0 || !legacyFallbackPath
      ? fallbackRows
      : await readSnapshotFallback(legacyFallbackPath);
    return {
      rows,
      diagnostic: {
        source,
        status: rows.length > 0 ? "fallback" : "empty",
        count: rows.length,
        fallbackPath,
        error: error instanceof Error ? error.message : String(error),
      },
    };
  }
}

export async function collectPredictionSnapshots(args: {
  source: string;
  limit: number;
  env?: NodeJS.ProcessEnv;
}): Promise<PredictionCollectResult> {
  const source = args.source.toLowerCase();
  const limit = args.limit;
  const env = args.env ?? process.env;
  const policy = buildPredictionSourcePolicyFromEnv(env);
  const enabled = new Set(policy.enabledSources);

  switch (source) {
    case "polymarket": {
      const result = await collectOne({
        source: "polymarket",
        enabled: true,
        fallbackPath: ".rumbling-hedge/runtime/prediction/polymarket-live-snapshot.json",
        legacyFallbackPath: "data/prediction/polymarket-live-snapshot.json",
        fetcher: () => fetchPolymarketLiveSnapshot(limit),
      });
      return { markets: result.rows, diagnostics: [result.diagnostic], policy };
    }
    case "kalshi": {
      const result = await collectOne({
        source: "kalshi",
        enabled: true,
        fallbackPath: ".rumbling-hedge/runtime/prediction/kalshi-live-snapshot.json",
        legacyFallbackPath: "data/prediction/kalshi-live-snapshot.json",
        fetcher: () => fetchKalshiLiveSnapshot(limit),
      });
      return { markets: result.rows, diagnostics: [result.diagnostic], policy };
    }
    case "manifold": {
      const result = await collectOne({
        source: "manifold",
        enabled: true,
        fallbackPath: ".rumbling-hedge/runtime/prediction/manifold-live-snapshot.json",
        legacyFallbackPath: "data/prediction/manifold-live-snapshot.json",
        fetcher: () => fetchManifoldLiveSnapshot(limit),
      });
      return { markets: result.rows, diagnostics: [result.diagnostic], policy };
    }
    case "combined":
    case "all": {
      const [polymarketResult, kalshiResult] = await Promise.all([
        collectOne({
          source: "polymarket",
          enabled: enabled.has("polymarket"),
          fallbackPath: ".rumbling-hedge/runtime/prediction/polymarket-live-snapshot.json",
          legacyFallbackPath: "data/prediction/polymarket-live-snapshot.json",
          fetcher: () => fetchPolymarketLiveSnapshot(Math.max(limit, 25)),
        }),
        collectOne({
          source: "kalshi",
          enabled: enabled.has("kalshi"),
          fallbackPath: ".rumbling-hedge/runtime/prediction/kalshi-live-snapshot.json",
          legacyFallbackPath: "data/prediction/kalshi-live-snapshot.json",
          fetcher: () => fetchKalshiLiveSnapshot(Math.max(limit * 4, 100)),
        }),
      ]);

      const seedMarkets = [...polymarketResult.rows, ...kalshiResult.rows];
      const manifoldResult = await collectOne({
        source: "manifold",
        enabled: enabled.has("manifold"),
        fallbackPath: ".rumbling-hedge/runtime/prediction/manifold-live-snapshot.json",
        legacyFallbackPath: "data/prediction/manifold-live-snapshot.json",
        fetcher: () =>
          fetchManifoldLiveSnapshot(Math.max(limit * 4, 100), {
            seedMarkets,
            searchTermLimit: 8,
          }),
      });

      return {
        markets: [...polymarketResult.rows, ...kalshiResult.rows, ...manifoldResult.rows],
        diagnostics: [
          polymarketResult.diagnostic,
          kalshiResult.diagnostic,
          manifoldResult.diagnostic,
        ],
        policy,
      };
    }
    default:
      throw new Error(`Unsupported prediction source: ${source}`);
  }
}
