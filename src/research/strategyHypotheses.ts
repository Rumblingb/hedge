import { createHash } from "node:crypto";
import { dirname, resolve } from "node:path";
import { mkdir, writeFile } from "node:fs/promises";
import { buildOllamaConfigFromEnv, generateJson as generateOllamaJson, type OllamaConfig } from "../llm/ollama.js";
import {
  buildOpenAiCompatibleConfigFromEnv,
  generateJson as generateCloudJson,
  type OpenAiCompatibleConfig
} from "../llm/openaiCompatible.js";
import { chunkText } from "./corpus.js";
import type { ResearcherPolicy } from "./pipeline.js";

export interface TranscriptSourceMeta {
  targetId: string;
  videoId: string;
  title: string;
  channel?: string;
  url: string;
  language?: string;
  transcriptText: string;
}

export interface StrategyHypothesis {
  id: string;
  title: string;
  market: "futures";
  symbols: string[];
  timeframes: string[];
  sessions: string[];
  setupSummary: string;
  biasRules: string[];
  entryRules: string[];
  stopRules: string[];
  targetRules: string[];
  riskRules: string[];
  confluence: string[];
  invalidationRules: string[];
  evidence: string[];
  automationReadiness: "low" | "medium" | "high";
  confidence: number;
  sourceTargetIds: string[];
  sourceVideoIds: string[];
  sourceVideoTitles: string[];
  sourceChannels: string[];
  sourceUrls: string[];
}

interface StrategyHypothesisEnvelope {
  strategies: Array<Omit<StrategyHypothesis, "id" | "sourceTargetIds" | "sourceVideoIds" | "sourceVideoTitles" | "sourceChannels" | "sourceUrls">>;
}

export interface StrategyHypothesisArtifact {
  generatedAt: string;
  runId: string;
  count: number;
  provider: "ollama" | "cloud";
  model: string;
  hypotheses: StrategyHypothesis[];
}

const EXTRACTION_SYSTEM_PROMPT = [
  "You extract systematic futures trading hypotheses from ICT-style YouTube transcripts.",
  "Return only explicit or strongly implied trading setups that could sharpen a futures automation lab.",
  "Focus on bias, session framing, liquidity, displacement, MSS, FVG, order blocks, entries, stops, targets, and risk controls.",
  "Do not invent numerical rules that are absent from the transcript.",
  "If a chunk is motivational or vague, return zero strategies for it.",
  "Prefer concise, machine-usable bullet-like rules in arrays.",
  "Keep evidence quotes short and verbatim.",
  "Return strict JSON."
].join(" ");

export function strategyHypothesesLatestPath(): string {
  return resolve(".rumbling-hedge/research/researcher/strategy-hypotheses.latest.json");
}

export function strategyHypothesesRunDir(): string {
  return resolve(".rumbling-hedge/research/researcher/strategy-hypotheses");
}

function strategyId(title: string): string {
  return createHash("sha1").update(title.toLowerCase().trim()).digest("hex").slice(0, 16);
}

function normalizeList(values: unknown): string[] {
  if (!Array.isArray(values)) return [];
  return values
    .filter((value): value is string => typeof value === "string")
    .map((value) => value.trim())
    .filter(Boolean);
}

function clampConfidence(value: unknown): number {
  const numeric = typeof value === "number" ? value : Number(value);
  if (!Number.isFinite(numeric)) return 0.4;
  return Math.max(0, Math.min(1, numeric));
}

function chooseProvider(): { kind: "ollama"; config: OllamaConfig } | { kind: "cloud"; config: OpenAiCompatibleConfig } {
  const cloud = buildOpenAiCompatibleConfigFromEnv(process.env);
  if (cloud.apiKey) {
    return { kind: "cloud", config: cloud };
  }
  return { kind: "ollama", config: buildOllamaConfigFromEnv(process.env) };
}

async function extractChunkStrategies(
  prompt: string,
  args: {
    provider: ReturnType<typeof chooseProvider>;
    model: string;
  }
): Promise<{ model: string; strategies: StrategyHypothesisEnvelope["strategies"] }> {
  if (args.provider.kind === "cloud") {
    const { value, model } = await generateCloudJson<StrategyHypothesisEnvelope>(
      prompt,
      {
        system: EXTRACTION_SYSTEM_PROMPT,
        model: args.model,
        temperature: 0.1,
        maxTokens: 1400
      },
      args.provider.config
    );
    return { model, strategies: Array.isArray(value?.strategies) ? value.strategies : [] };
  }

  const { value, model } = await generateOllamaJson<StrategyHypothesisEnvelope>(
    prompt,
    {
      system: EXTRACTION_SYSTEM_PROMPT,
      model: args.model,
      temperature: 0.1,
      maxTokens: 1400
    },
    args.provider.config
  );
  return { model, strategies: Array.isArray(value?.strategies) ? value.strategies : [] };
}

export async function extractStrategyHypothesesFromTranscript(
  source: TranscriptSourceMeta,
  policy: ResearcherPolicy
): Promise<{ hypotheses: StrategyHypothesis[]; provider: "ollama" | "cloud"; model: string }> {
  const provider = chooseProvider();
  const chunkMax = Math.max(1800, Math.min(6000, policy.quality.maxChars * 3));
  const transcriptChunks = chunkText(source.transcriptText, Math.max(300, policy.quality.minChars), chunkMax);
  const merged = new Map<string, StrategyHypothesis>();
  let model = policy.llm.generateModel;

  for (const [index, transcriptChunk] of transcriptChunks.entries()) {
    const prompt = [
      `Target ID: ${source.targetId}`,
      `Video ID: ${source.videoId}`,
      `Title: ${source.title}`,
      `Channel: ${source.channel ?? "unknown"}`,
      `Language: ${source.language ?? "unknown"}`,
      `Chunk: ${index + 1}/${transcriptChunks.length}`,
      "",
      "Return JSON with shape:",
      '{ "strategies": [{ "title": string, "market": "futures", "symbols": string[], "timeframes": string[], "sessions": string[], "setupSummary": string, "biasRules": string[], "entryRules": string[], "stopRules": string[], "targetRules": string[], "riskRules": string[], "confluence": string[], "invalidationRules": string[], "evidence": string[], "automationReadiness": "low"|"medium"|"high", "confidence": number }] }',
      "",
      "Transcript:",
      transcriptChunk
    ].join("\n");

    const extracted = await extractChunkStrategies(prompt, {
      provider,
      model: provider.kind === "cloud" ? buildOpenAiCompatibleConfigFromEnv(process.env).defaultModel : policy.llm.generateModel
    });
    model = extracted.model;

    for (const raw of extracted.strategies) {
      if (!raw || typeof raw.title !== "string" || raw.title.trim().length === 0) continue;
      const id = strategyId(raw.title);
      const existing = merged.get(id);
      const next: StrategyHypothesis = existing ?? {
        id,
        title: raw.title.trim(),
        market: "futures",
        symbols: [],
        timeframes: [],
        sessions: [],
        setupSummary: "",
        biasRules: [],
        entryRules: [],
        stopRules: [],
        targetRules: [],
        riskRules: [],
        confluence: [],
        invalidationRules: [],
        evidence: [],
        automationReadiness: "low",
        confidence: 0,
        sourceTargetIds: [],
        sourceVideoIds: [],
        sourceVideoTitles: [],
        sourceChannels: [],
        sourceUrls: []
      };

      next.market = "futures";
      next.setupSummary = typeof raw.setupSummary === "string" && raw.setupSummary.trim().length > 0
        ? raw.setupSummary.trim()
        : next.setupSummary;
      next.symbols = Array.from(new Set([...next.symbols, ...normalizeList(raw.symbols)]));
      next.timeframes = Array.from(new Set([...next.timeframes, ...normalizeList(raw.timeframes)]));
      next.sessions = Array.from(new Set([...next.sessions, ...normalizeList(raw.sessions)]));
      next.biasRules = Array.from(new Set([...next.biasRules, ...normalizeList(raw.biasRules)]));
      next.entryRules = Array.from(new Set([...next.entryRules, ...normalizeList(raw.entryRules)]));
      next.stopRules = Array.from(new Set([...next.stopRules, ...normalizeList(raw.stopRules)]));
      next.targetRules = Array.from(new Set([...next.targetRules, ...normalizeList(raw.targetRules)]));
      next.riskRules = Array.from(new Set([...next.riskRules, ...normalizeList(raw.riskRules)]));
      next.confluence = Array.from(new Set([...next.confluence, ...normalizeList(raw.confluence)]));
      next.invalidationRules = Array.from(new Set([...next.invalidationRules, ...normalizeList(raw.invalidationRules)]));
      next.evidence = Array.from(new Set([...next.evidence, ...normalizeList(raw.evidence)])).slice(0, 8);
      next.automationReadiness = raw.automationReadiness === "high" || raw.automationReadiness === "medium"
        ? raw.automationReadiness
        : next.automationReadiness;
      next.confidence = Math.max(next.confidence, clampConfidence(raw.confidence));
      next.sourceTargetIds = Array.from(new Set([...next.sourceTargetIds, source.targetId]));
      next.sourceVideoIds = Array.from(new Set([...next.sourceVideoIds, source.videoId]));
      next.sourceVideoTitles = Array.from(new Set([...next.sourceVideoTitles, source.title]));
      next.sourceChannels = Array.from(new Set([...next.sourceChannels, source.channel ?? ""])).filter(Boolean);
      next.sourceUrls = Array.from(new Set([...next.sourceUrls, source.url]));

      merged.set(id, next);
    }
  }

  return {
    hypotheses: [...merged.values()].sort((left, right) => right.confidence - left.confidence),
    provider: provider.kind,
    model
  };
}

export async function writeStrategyHypothesisArtifacts(
  artifact: StrategyHypothesisArtifact
): Promise<{ latestPath: string; runPath: string }> {
  const latestPath = strategyHypothesesLatestPath();
  const runPath = resolve(strategyHypothesesRunDir(), `${artifact.runId}.json`);
  await mkdir(dirname(latestPath), { recursive: true });
  await mkdir(dirname(runPath), { recursive: true });
  await writeFile(latestPath, `${JSON.stringify(artifact, null, 2)}\n`, "utf8");
  await writeFile(runPath, `${JSON.stringify(artifact, null, 2)}\n`, "utf8");
  return { latestPath, runPath };
}
