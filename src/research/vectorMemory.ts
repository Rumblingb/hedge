import { mkdir, readFile, writeFile } from "node:fs/promises";
import { dirname, join, resolve } from "node:path";
import { embed, buildOllamaConfigFromEnv } from "../llm/ollama.js";
import { readCorpusChunks, resolveCorpusPaths } from "./corpus.js";

export interface VectorEntry {
  id: string;
  embedding: number[];
  snippet: string;
  sourceId: string;
  sourceKind: string;
  fetchedAt: string;
}

export interface VectorIndexMeta {
  version: 1;
  model: string;
  dimensions: number;
  updatedAt: string;
  count: number;
  minClassifierScore: number;
  topicCoverage?: TopicCoverage[];
}

const MIN_CLASSIFIER_SCORE = 5;

function defaultBase(): string {
  return resolve(
    process.env.BILL_RESEARCH_CORPUS_ROOT
      ? dirname(process.env.BILL_RESEARCH_CORPUS_ROOT)
      : join(process.cwd(), ".rumbling-hedge/research")
  );
}

export function resolveVectorPaths(base?: string) {
  const root = base ?? defaultBase();
  return {
    indexJsonl: join(root, "vector-index.jsonl"),
    meta: join(root, "vector-index.meta.json")
  };
}

export async function loadVectorIndex(base?: string): Promise<VectorEntry[]> {
  const paths = resolveVectorPaths(base);
  try {
    const raw = await readFile(paths.indexJsonl, "utf8");
    return raw
      .split(/\r?\n/)
      .filter(Boolean)
      .map((line) => JSON.parse(line) as VectorEntry);
  } catch {
    return [];
  }
}

export async function loadVectorMeta(base?: string): Promise<VectorIndexMeta | null> {
  const paths = resolveVectorPaths(base);
  try {
    return JSON.parse(await readFile(paths.meta, "utf8")) as VectorIndexMeta;
  } catch {
    return null;
  }
}

function cosineSimilarity(a: number[], b: number[]): number {
  let dot = 0, normA = 0, normB = 0;
  for (let i = 0; i < a.length; i++) {
    dot += (a[i] ?? 0) * (b[i] ?? 0);
    normA += (a[i] ?? 0) ** 2;
    normB += (b[i] ?? 0) ** 2;
  }
  const denom = Math.sqrt(normA) * Math.sqrt(normB);
  return denom === 0 ? 0 : dot / denom;
}

export interface VectorSearchResult {
  entry: VectorEntry;
  score: number;
}

export async function vectorSearch(
  query: string,
  entries: VectorEntry[],
  k = 5,
  minScore = 0.3
): Promise<VectorSearchResult[]> {
  if (entries.length === 0) return [];
  const config = buildOllamaConfigFromEnv();
  const { embedding } = await embed(query.slice(0, 2000), {}, config);
  return entries
    .map((entry) => ({ entry, score: cosineSimilarity(embedding, entry.embedding) }))
    .filter((r) => r.score >= minScore)
    .sort((a, b) => b.score - a.score)
    .slice(0, k);
}

export interface BuildIndexResult {
  indexed: number;
  skipped: number;
  filtered: number;
  errors: number;
  totalInIndex: number;
}

export async function buildVectorIndex(opts: {
  force?: boolean;
  base?: string;
  onProgress?: (done: number, total: number) => void;
} = {}): Promise<BuildIndexResult> {
  const { force = false, base, onProgress } = opts;
  const paths = resolveVectorPaths(base);

  const chunks = await readCorpusChunks(resolveCorpusPaths());
  const eligible = chunks.filter((c) => (c.classifierScore ?? 0) >= MIN_CLASSIFIER_SCORE);
  const filtered = chunks.length - eligible.length;

  const existing = force ? [] : await loadVectorIndex(base);
  const existingIds = new Set(existing.map((e) => e.id));
  const toIndex = eligible.filter((c) => !existingIds.has(c.id));

  if (toIndex.length === 0) {
    return { indexed: 0, skipped: existing.length, filtered, errors: 0, totalInIndex: existing.length };
  }

  await mkdir(dirname(paths.indexJsonl), { recursive: true });

  const config = buildOllamaConfigFromEnv();
  let indexed = 0, errors = 0;
  const newEntries: VectorEntry[] = force ? [] : [...existing];

  for (let i = 0; i < toIndex.length; i++) {
    const chunk = toIndex[i]!;
    try {
      const { embedding } = await embed(chunk.text.slice(0, 2000), {}, config);
      newEntries.push({
        id: chunk.id,
        embedding,
        snippet: chunk.text.slice(0, 300).replace(/\n+/g, " "),
        sourceId: chunk.sourceId,
        sourceKind: chunk.sourceKind,
        fetchedAt: chunk.fetchedAt
      });
      indexed++;
    } catch {
      errors++;
    }
    onProgress?.(i + 1, toIndex.length);
  }

  const payload = newEntries.map((e) => JSON.stringify(e)).join("\n");
  await writeFile(paths.indexJsonl, `${payload}\n`, "utf8");

  let topicCoverage: TopicCoverage[] | undefined;
  try {
    topicCoverage = await detectTopicGaps(base);
  } catch {
    // gap detection is best-effort
  }

  const meta: VectorIndexMeta = {
    version: 1,
    model: config.defaultEmbedModel,
    dimensions: newEntries[0]?.embedding.length ?? 768,
    updatedAt: new Date().toISOString(),
    count: newEntries.length,
    minClassifierScore: MIN_CLASSIFIER_SCORE,
    topicCoverage
  };
  await writeFile(paths.meta, `${JSON.stringify(meta, null, 2)}\n`, "utf8");

  return { indexed, skipped: existingIds.size, filtered, errors, totalInIndex: newEntries.length };
}

export async function getSemanticContextBlock(
  query: string,
  k = 5,
  base?: string
): Promise<string> {
  const entries = await loadVectorIndex(base);
  if (entries.length === 0) return "";
  try {
    const results = await vectorSearch(query, entries, k, 0.35);
    if (results.length === 0) return "";
    const lines = results.map(
      (r, i) =>
        `[${i + 1}] score=${r.score.toFixed(2)} source=${r.entry.sourceId}\n${r.entry.snippet}`
    );
    return `## Semantically related corpus knowledge (do not repeat — build on or contrast)\n${lines.join("\n\n")}`;
  } catch {
    return "";
  }
}

export async function getGapTopicsFromMeta(base?: string): Promise<string[]> {
  const meta = await loadVectorMeta(base);
  if (!meta?.topicCoverage) return [];
  return meta.topicCoverage.filter((t) => t.gap).map((t) => t.key);
}

const TOPIC_QUERIES = [
  { key: "opex-gamma", query: "options expiration OPEX gamma squeeze futures intraday" },
  { key: "vix-settlement", query: "VIX settlement volatility regime Wednesday futures" },
  { key: "cme-quarterly-roll", query: "CME quarterly expiry roll CTA rebalancing" },
  { key: "opening-range", query: "opening range breakout reversal intraday RTH" },
  { key: "session-momentum", query: "session momentum trend continuation futures open drive" },
  { key: "ict-fvg", query: "ICT displacement fair value gap order flow market structure" },
  { key: "liquidity-sweep", query: "liquidity sweep stop hunt mean reversion fade" },
  { key: "dealer-gamma-gex", query: "dealer gamma GEX options market maker hedging spot" },
  { key: "cot-positioning", query: "COT commitment of traders leveraged fund positioning" },
  { key: "macro-regime", query: "macro regime interest rates equity futures correlation" }
] as const;

export interface TopicCoverage {
  key: string;
  query: string;
  chunkCount: number;
  avgScore: number;
  gap: boolean;
}

export async function detectTopicGaps(
  base?: string,
  coverageThreshold = 5
): Promise<TopicCoverage[]> {
  const entries = await loadVectorIndex(base);
  if (entries.length === 0) return [];

  const config = buildOllamaConfigFromEnv();
  const results: TopicCoverage[] = [];

  for (const { key, query } of TOPIC_QUERIES) {
    try {
      const { embedding } = await embed(query, {}, config);
      const scores = entries
        .map((e) => cosineSimilarity(embedding, e.embedding))
        .filter((s) => s >= 0.45);
      results.push({
        key,
        query,
        chunkCount: scores.length,
        avgScore: scores.length > 0 ? scores.reduce((a, b) => a + b, 0) / scores.length : 0,
        gap: scores.length < coverageThreshold
      });
    } catch {
      results.push({ key, query, chunkCount: 0, avgScore: 0, gap: true });
    }
  }

  return results.sort((a, b) => a.chunkCount - b.chunkCount);
}
