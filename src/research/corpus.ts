import { createHash } from "node:crypto";
import { appendFile, mkdir, readFile, writeFile } from "node:fs/promises";
import { dirname, join, resolve } from "node:path";
import { minhash, type MinHashSignature } from "./minhash.js";

export interface CorpusChunk {
  id: string;
  runId: string;
  sourceId: string;
  sourceKind: "web" | "github-repo" | "arxiv" | "github-issues";
  url: string;
  fetchedAt: string;
  title?: string;
  text: string;
  tokensEstimate: number;
  classifierScore?: number;
  judgeScore?: number;
  judgeRationale?: string;
  tags?: string[];
  minhash: MinHashSignature;
  embedding?: number[];
  hash: string;
}

export interface CorpusManifest {
  version: 1;
  updatedAt: string;
  chunkCount: number;
  totalBytes: number;
  lastRunId?: string;
  runs: Array<{
    runId: string;
    startedAt: string;
    finishedAt: string;
    targetsAttempted: number;
    chunksKept: number;
    chunksRejected: number;
    reason?: string;
  }>;
}

export interface CorpusPaths {
  root: string;
  chunksJsonl: string;
  manifest: string;
}

function defaultCorpusRoot(): string {
  return resolve(process.env.BILL_RESEARCH_CORPUS_ROOT ?? join(process.cwd(), ".rumbling-hedge/research/corpus"));
}

export function resolveCorpusPaths(root: string = defaultCorpusRoot()): CorpusPaths {
  return {
    root,
    chunksJsonl: join(root, "chunks.jsonl"),
    manifest: join(root, "manifest.json")
  };
}

export function hashText(text: string): string {
  return createHash("sha256").update(text).digest("hex").slice(0, 16);
}

export function estimateTokens(text: string): number {
  return Math.ceil(text.length / 4);
}

export async function readCorpusChunks(paths: CorpusPaths = resolveCorpusPaths()): Promise<CorpusChunk[]> {
  try {
    const raw = await readFile(paths.chunksJsonl, "utf8");
    return raw
      .split(/\r?\n/)
      .map((line) => line.trim())
      .filter(Boolean)
      .map((line) => JSON.parse(line) as CorpusChunk);
  } catch {
    return [];
  }
}

export async function readManifest(paths: CorpusPaths = resolveCorpusPaths()): Promise<CorpusManifest> {
  try {
    const raw = await readFile(paths.manifest, "utf8");
    return JSON.parse(raw) as CorpusManifest;
  } catch {
    return {
      version: 1,
      updatedAt: new Date(0).toISOString(),
      chunkCount: 0,
      totalBytes: 0,
      runs: []
    };
  }
}

export async function appendCorpusChunks(
  chunks: CorpusChunk[],
  paths: CorpusPaths = resolveCorpusPaths()
): Promise<void> {
  if (chunks.length === 0) return;
  await mkdir(dirname(paths.chunksJsonl), { recursive: true });
  const payload = chunks.map((c) => JSON.stringify(c)).join("\n");
  await appendFile(paths.chunksJsonl, `${payload}\n`, "utf8");
}

export async function writeManifest(
  manifest: CorpusManifest,
  paths: CorpusPaths = resolveCorpusPaths()
): Promise<void> {
  await mkdir(dirname(paths.manifest), { recursive: true });
  await writeFile(paths.manifest, `${JSON.stringify(manifest, null, 2)}\n`, "utf8");
}

export function chunkText(text: string, minChars = 400, maxChars = 2000): string[] {
  const cleaned = text.replace(/\r\n/g, "\n").replace(/[ \t]+\n/g, "\n").trim();
  if (cleaned.length <= maxChars) {
    return cleaned.length >= minChars ? [cleaned] : cleaned.length > 0 ? [cleaned] : [];
  }
  const paragraphs = cleaned.split(/\n\s*\n+/);
  const chunks: string[] = [];
  let buffer = "";
  for (const p of paragraphs) {
    if (!p.trim()) continue;
    if ((buffer + "\n\n" + p).length > maxChars && buffer.length >= minChars) {
      chunks.push(buffer.trim());
      buffer = p;
    } else {
      buffer = buffer ? `${buffer}\n\n${p}` : p;
    }
  }
  if (buffer.trim()) chunks.push(buffer.trim());
  return chunks;
}

export function buildChunk(
  input: {
    runId: string;
    sourceId: string;
    sourceKind: CorpusChunk["sourceKind"];
    url: string;
    title?: string;
    text: string;
    tags?: string[];
  }
): CorpusChunk {
  const text = input.text.trim();
  const hash = hashText(text);
  return {
    id: `${input.sourceId}:${hash}`,
    runId: input.runId,
    sourceId: input.sourceId,
    sourceKind: input.sourceKind,
    url: input.url,
    fetchedAt: new Date().toISOString(),
    title: input.title,
    text,
    tokensEstimate: estimateTokens(text),
    tags: input.tags,
    minhash: minhash(text),
    hash
  };
}

export function corpusStats(chunks: CorpusChunk[]): {
  total: number;
  tokens: number;
  perSource: Record<string, number>;
  perKind: Record<string, number>;
} {
  const perSource: Record<string, number> = {};
  const perKind: Record<string, number> = {};
  let tokens = 0;
  for (const c of chunks) {
    tokens += c.tokensEstimate;
    perSource[c.sourceId] = (perSource[c.sourceId] ?? 0) + 1;
    perKind[c.sourceKind] = (perKind[c.sourceKind] ?? 0) + 1;
  }
  return { total: chunks.length, tokens, perSource, perKind };
}
