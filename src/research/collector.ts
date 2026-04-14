import { mkdir, readFile, stat, writeFile } from "node:fs/promises";
import { existsSync } from "node:fs";
import os from "node:os";
import path, { dirname, resolve } from "node:path";
import { fetchFreeBars, writeBarsCsv } from "../data/freeSources.js";
import { fetchKalshiLiveSnapshot } from "../prediction/adapters/kalshi.js";
import { fetchManifoldLiveSnapshot } from "../prediction/adapters/manifold.js";
import { fetchPolymarketLiveSnapshot } from "../prediction/adapters/polymarket.js";

export type ResearchArtifactKind = "market-snapshot" | "market-bars" | "local-artifact" | "paper";
export type ResearchArtifactStatus = "keep" | "discard";

export interface ResearchArtifact {
  id: string;
  kind: ResearchArtifactKind;
  source: string;
  title: string;
  location: string;
  fetchedAt: string;
  status: ResearchArtifactStatus;
  reason: string;
  tags: string[];
  summary: string;
  metadata: Record<string, unknown>;
}

export interface ResearchCatalog {
  command: "research-agent-collect";
  timestamp: string;
  catalogPath: string;
  items: ResearchArtifact[];
}

const DEFAULT_SYMBOLS = ["NQ", "ES", "CL", "GC", "6E", "ZN"];
const DEFAULT_PAPER_QUERIES = [
  "prediction markets market making",
  "market microstructure limit order book",
  "kelly criterion position sizing",
  "options volatility arbitrage"
];

function catalogPathFromEnv(env: NodeJS.ProcessEnv): string {
  return resolve(env.BILL_RESEARCH_CATALOG_PATH ?? ".rumbling-hedge/research/catalog.json");
}

function normalizeKey(value: string): string {
  return value.toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();
}

function artifactId(kind: ResearchArtifactKind, source: string, title: string): string {
  return `${kind}:${source}:${normalizeKey(title)}`;
}

function summarizeLine(text: string, length = 180): string {
  const compact = text.replace(/\s+/g, " ").trim();
  if (!compact) return "no summary";
  return compact.length > length ? `${compact.slice(0, length - 3)}...` : compact;
}

function countBy<T extends string>(rows: T[]): Record<T, number> {
  return rows.reduce<Record<T, number>>((acc, item) => {
    acc[item] = (acc[item] ?? 0) + 1;
    return acc;
  }, {} as Record<T, number>);
}

async function writeJson(filePath: string, value: unknown): Promise<string> {
  const target = resolve(filePath);
  await mkdir(dirname(target), { recursive: true });
  await writeFile(target, `${JSON.stringify(value, null, 2)}\n`, "utf8");
  return target;
}

async function collectPredictionResearch(timestamp: string): Promise<ResearchArtifact[]> {
  const outDir = resolve("data/research/prediction");
  const payloads = [
    { source: "polymarket", result: await fetchPolymarketLiveSnapshot(20).then((rows) => ({ rows })).catch((error) => ({ error })) },
    { source: "kalshi", result: await fetchKalshiLiveSnapshot(20).then((rows) => ({ rows })).catch((error) => ({ error })) },
    { source: "manifold", result: await fetchManifoldLiveSnapshot(20).then((rows) => ({ rows })).catch((error) => ({ error })) }
  ];
  const results: ResearchArtifact[] = [];

  for (const payload of payloads) {
    const rows = "rows" in payload.result ? payload.result.rows : [];
    const error = "error" in payload.result ? payload.result.error : null;
    const filePath = await writeJson(path.join(outDir, `${payload.source}-snapshot.json`), rows);
    const keep = rows.length > 0 && !error;
    results.push({
      id: artifactId("market-snapshot", payload.source, `${payload.source} snapshot ${timestamp}`),
      kind: "market-snapshot",
      source: payload.source,
      title: `${payload.source} live snapshot`,
      location: filePath,
      fetchedAt: timestamp,
      status: keep ? "keep" : "discard",
      reason: keep ? "current venue snapshot captured" : error ? "venue snapshot fetch failed" : "venue returned no comparable live rows",
      tags: ["prediction", payload.source],
      summary: keep
        ? `${rows.length} comparable rows captured from ${payload.source}.`
        : error
          ? (error instanceof Error ? error.message : String(error))
          : `${payload.source} returned no comparable rows.`,
      metadata: {
        rows: rows.length,
        sample: rows.slice(0, 2)
      }
    });
  }

  return results;
}

async function collectPublicMarketData(timestamp: string): Promise<ResearchArtifact[]> {
  const outDir = resolve("data/research/market-bars");
  const results = await Promise.all(DEFAULT_SYMBOLS.map(async (symbol) => {
    try {
      const result = await fetchFreeBars({ symbol, interval: "1d", range: "1mo", provider: "auto", timeoutMs: 10_000 });
      const outPath = await writeBarsCsv({ bars: result.bars, outPath: path.join(outDir, `${symbol}-1d-1mo.csv`) });
      return {
        id: artifactId("market-bars", result.providerUsed, symbol),
        kind: "market-bars",
        source: result.providerUsed,
        title: `${symbol} 1d 1mo bars`,
        location: outPath,
        fetchedAt: timestamp,
        status: result.bars.length > 0 ? "keep" : "discard",
        reason: result.bars.length > 0 ? "current public market data captured" : "provider returned zero rows",
        tags: ["futures", symbol, result.providerUsed],
        summary: `${result.bars.length} bars fetched for ${symbol} from ${result.providerUsed}.`,
        metadata: {
          symbol,
          providerUsed: result.providerUsed,
          bars: result.bars.length,
          startTs: result.bars[0]?.ts,
          endTs: result.bars[result.bars.length - 1]?.ts,
          warnings: result.warnings
        }
      } satisfies ResearchArtifact;
    } catch (error) {
      return {
        id: artifactId("market-bars", "collector-error", symbol),
        kind: "market-bars",
        source: "collector-error",
        title: `${symbol} 1d 1mo bars`,
        location: path.join(outDir, `${symbol}-1d-1mo.csv`),
        fetchedAt: timestamp,
        status: "discard",
        reason: "public market data fetch failed",
        tags: ["futures", symbol, "error"],
        summary: error instanceof Error ? error.message : String(error),
        metadata: { symbol }
      } satisfies ResearchArtifact;
    }
  }));

  return results;
}

function isPlaceholderArtifact(content: string): boolean {
  const compact = content.replace(/\s+/g, " ").trim().toLowerCase();
  return compact.length === 0
    || compact === "# outbox write compact operator-facing updates here when a run materially changes state."
    || compact === "# agency os outbox use this for compact operator-facing summaries of product, build, growth, and revenue progress.";
}

async function collectLocalArtifacts(timestamp: string): Promise<ResearchArtifact[]> {
  const workspaceMemoryDir = process.env.BILL_WORKSPACE_MEMORY_DIR ?? path.join(os.homedir(), ".openclaw/workspace-bill/memory");
  const localFiles = [
    resolve(".rumbling-hedge/logs/prediction-cycle-history.jsonl"),
    resolve(".rumbling-hedge/logs/bill-health.latest.json"),
    resolve("journals/prediction-opportunities.jsonl"),
    path.join(os.homedir(), ".openclaw/workspace-bill/INBOX.md"),
    path.join(os.homedir(), ".openclaw/workspace-bill/OUTBOX.md"),
    path.join(os.homedir(), ".openclaw/workspace-bill/MAIN_ADVICE.md"),
    path.join(workspaceMemoryDir, `native-prediction-loop-${timestamp.slice(0, 10)}.md`)
  ];

  const results: ResearchArtifact[] = [];
  for (const file of localFiles) {
    if (!existsSync(file)) continue;
    const meta = await stat(file);
    const content = await readFile(file, "utf8");
    const discard = isPlaceholderArtifact(content);
    results.push({
      id: artifactId("local-artifact", "bill-runtime", path.basename(file)),
      kind: "local-artifact",
      source: "bill-runtime",
      title: path.basename(file),
      location: file,
      fetchedAt: timestamp,
      status: discard ? "discard" : "keep",
      reason: discard ? "placeholder or empty artifact" : "active Bill runtime artifact",
      tags: ["bill", "local"],
      summary: summarizeLine(content),
      metadata: {
        bytes: meta.size,
        updatedAt: meta.mtime.toISOString(),
        lines: content.split(/\r?\n/).length
      }
    });
  }

  return results;
}

interface ArxivEntry {
  id: string;
  title: string;
  published: string;
  updated: string;
  summary: string;
  authors: string[];
}

function extractTag(block: string, tag: string): string {
  const match = block.match(new RegExp(`<${tag}[^>]*>([\\s\\S]*?)<\\/${tag}>`, "i"));
  return match?.[1]?.replace(/<!\\[CDATA\\[|\\]\\]>/g, "").trim() ?? "";
}

function parseArxivEntries(xml: string): ArxivEntry[] {
  return [...xml.matchAll(/<entry>([\s\S]*?)<\/entry>/gi)].map((match) => {
    const block = match[1];
    const authors = [...block.matchAll(/<name>([\s\S]*?)<\/name>/gi)].map((item) => item[1].trim());
    return {
      id: extractTag(block, "id"),
      title: summarizeLine(extractTag(block, "title"), 220),
      published: extractTag(block, "published"),
      updated: extractTag(block, "updated"),
      summary: summarizeLine(extractTag(block, "summary"), 260),
      authors
    };
  });
}

async function collectResearchPapers(timestamp: string): Promise<ResearchArtifact[]> {
  const papersOut = resolve("data/research/papers/arxiv-metadata.json");
  const keptTitles = new Set<string>();
  const results = await Promise.all(DEFAULT_PAPER_QUERIES.map(async (query) => {
    const url = new URL("https://export.arxiv.org/api/query");
    url.searchParams.set("search_query", `all:${query}`);
    url.searchParams.set("start", "0");
    url.searchParams.set("max_results", "2");
    url.searchParams.set("sortBy", "relevance");
    url.searchParams.set("sortOrder", "descending");
    const response = await fetch(url, {
      headers: {
        accept: "application/atom+xml",
        "user-agent": "rumbling-hedge/0.1"
      },
      signal: AbortSignal.timeout(10_000)
    });
    if (!response.ok) {
      return [{ error: true, query, summary: `arXiv request failed: ${response.status} ${response.statusText}` }];
    }

    return parseArxivEntries(await response.text()).map((entry) => ({ query, ...entry }));
  }).map(async (promise) => {
    try {
      return await promise;
    } catch (error) {
      return [{ error: true, query: "unknown", summary: error instanceof Error ? error.message : String(error) }];
    }
  }));

  const artifacts: ResearchArtifact[] = [];
  const metadata: Array<Record<string, unknown>> = [];
  for (const group of results) {
    for (const item of group) {
      if ("error" in item) {
        artifacts.push({
          id: artifactId("paper", "arxiv", item.query),
          kind: "paper",
          source: "arxiv",
          title: item.query,
          location: papersOut,
          fetchedAt: timestamp,
          status: "discard",
          reason: "paper metadata fetch failed",
          tags: ["paper", "arxiv"],
          summary: item.summary,
          metadata: { query: item.query }
        });
        continue;
      }

      const titleKey = normalizeKey(item.title);
      const duplicate = keptTitles.has(titleKey);
      if (!duplicate) keptTitles.add(titleKey);
      metadata.push(item);
      artifacts.push({
        id: artifactId("paper", "arxiv", item.title),
        kind: "paper",
        source: "arxiv",
        title: item.title,
        location: papersOut,
        fetchedAt: timestamp,
        status: duplicate ? "discard" : "keep",
        reason: duplicate ? "duplicate paper metadata" : "relevant public paper metadata",
        tags: ["paper", "arxiv", ...item.query.split(" ").slice(0, 2)],
        summary: `${item.summary} Authors: ${item.authors.slice(0, 3).join(", ") || "unknown"}.`,
        metadata: {
          query: item.query,
          paperId: item.id,
          published: item.published,
          updated: item.updated,
          authors: item.authors
        }
      });
    }
  }

  await writeJson(papersOut, metadata);
  return artifacts;
}

export async function collectResearchCatalog(env: NodeJS.ProcessEnv): Promise<ResearchCatalog> {
  const timestamp = new Date().toISOString();
  const items = [
    ...(await collectPredictionResearch(timestamp)),
    ...(await collectPublicMarketData(timestamp)),
    ...(await collectLocalArtifacts(timestamp)),
    ...(await collectResearchPapers(timestamp))
  ];
  const catalogPath = catalogPathFromEnv(env);
  const catalog: ResearchCatalog = {
    command: "research-agent-collect",
    timestamp,
    catalogPath,
    items
  };
  await writeJson(catalogPath, catalog);
  return catalog;
}

export async function readResearchCatalog(env: NodeJS.ProcessEnv): Promise<ResearchCatalog> {
  const catalogPath = catalogPathFromEnv(env);
  const raw = await readFile(catalogPath, "utf8");
  return JSON.parse(raw) as ResearchCatalog;
}

export function buildResearchCatalogReport(catalog: ResearchCatalog): {
  command: "research-agent-report";
  timestamp: string;
  catalogPath: string;
  total: number;
  byStatus: Record<ResearchArtifactStatus, number>;
  byKind: Record<ResearchArtifactKind, number>;
  keptTop10: ResearchArtifact[];
} {
  return {
    command: "research-agent-report",
    timestamp: catalog.timestamp,
    catalogPath: catalog.catalogPath,
    total: catalog.items.length,
    byStatus: countBy(catalog.items.map((item) => item.status)),
    byKind: countBy(catalog.items.map((item) => item.kind)),
    keptTop10: catalog.items.filter((item) => item.status === "keep").slice(0, 10)
  };
}
