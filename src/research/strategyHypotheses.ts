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

export interface ResearchChunkStrategySeed {
  sourceId: string;
  sourceKind: string;
  url?: string;
  title?: string;
  text: string;
  tags?: string[];
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

function compactEvidence(text: string): string {
  const normalized = text.replace(/\s+/g, " ").trim();
  return normalized.length > 220 ? `${normalized.slice(0, 217)}...` : normalized;
}

function containsAny(text: string, needles: string[]): boolean {
  const lower = text.toLowerCase();
  return needles.some((needle) => lower.includes(needle));
}

function inferSymbolsFromChunk(text: string): string[] {
  const upper = text.toUpperCase();
  const symbols = [
    { symbol: "NQ", needles: ["NQ", "NASDAQ", "NAS100"] },
    { symbol: "ES", needles: ["ES", "S&P", "SPX", "E-MINI"] },
    { symbol: "CL", needles: ["CL", "CRUDE", "WTI", "OIL"] },
    { symbol: "GC", needles: ["GC", "GOLD", "XAU"] },
    { symbol: "6E", needles: ["6E", "EURO", "EURUSD"] },
    { symbol: "ZN", needles: ["ZN", "10Y", "10-YEAR", "TREASURY NOTE"] }
  ];
  const inferred = symbols
    .filter((entry) => entry.needles.some((needle) => upper.includes(needle)))
    .map((entry) => entry.symbol);
  return inferred.length > 0 ? inferred : ["ES", "NQ"];
}

function mergeHypothesis(current: StrategyHypothesis | undefined, next: StrategyHypothesis): StrategyHypothesis {
  if (!current) return next;
  return {
    ...current,
    symbols: Array.from(new Set([...current.symbols, ...next.symbols])).slice(0, 8),
    timeframes: Array.from(new Set([...current.timeframes, ...next.timeframes])).slice(0, 8),
    sessions: Array.from(new Set([...current.sessions, ...next.sessions])).slice(0, 8),
    biasRules: Array.from(new Set([...current.biasRules, ...next.biasRules])).slice(0, 8),
    entryRules: Array.from(new Set([...current.entryRules, ...next.entryRules])).slice(0, 8),
    stopRules: Array.from(new Set([...current.stopRules, ...next.stopRules])).slice(0, 8),
    targetRules: Array.from(new Set([...current.targetRules, ...next.targetRules])).slice(0, 8),
    riskRules: Array.from(new Set([...current.riskRules, ...next.riskRules])).slice(0, 8),
    confluence: Array.from(new Set([...current.confluence, ...next.confluence])).slice(0, 8),
    invalidationRules: Array.from(new Set([...current.invalidationRules, ...next.invalidationRules])).slice(0, 8),
    evidence: Array.from(new Set([...current.evidence, ...next.evidence])).slice(0, 8),
    confidence: Math.max(current.confidence, next.confidence),
    sourceTargetIds: Array.from(new Set([...current.sourceTargetIds, ...next.sourceTargetIds])),
    sourceVideoIds: Array.from(new Set([...current.sourceVideoIds, ...next.sourceVideoIds])),
    sourceVideoTitles: Array.from(new Set([...current.sourceVideoTitles, ...next.sourceVideoTitles])),
    sourceChannels: Array.from(new Set([...current.sourceChannels, ...next.sourceChannels])),
    sourceUrls: Array.from(new Set([...current.sourceUrls, ...next.sourceUrls]))
  };
}

export function deriveStrategyHypothesesFromResearchChunks(chunks: ResearchChunkStrategySeed[]): StrategyHypothesis[] {
  const merged = new Map<string, StrategyHypothesis>();

  for (const chunk of chunks) {
    const tags = chunk.tags ?? [];
    const tagText = tags.join(" ").toLowerCase();
    const text = [chunk.title, tagText, chunk.text].filter(Boolean).join("\n");
    const title = chunk.title?.trim() || chunk.sourceId;
    const sourceUrls = chunk.url ? [chunk.url] : [];
    const sourceTargetIds = [chunk.sourceId].filter(Boolean);
    const symbols = inferSymbolsFromChunk(text);
    const evidence = [
      `Research source: ${title}`,
      compactEvidence(chunk.text)
    ];

    const candidates: StrategyHypothesis[] = [];
    if (
      containsAny(tagText, ["trend-following", "volatility-targeting", "macro-rates", "momentum"]) ||
      containsAny(text, ["trend following", "time series momentum", "volatility targeting", "managed futures", "breakout", "continuation"])
    ) {
      candidates.push({
        id: strategyId("Research-seeded session momentum with volatility filter"),
        title: "Research-seeded session momentum with volatility filter",
        market: "futures",
        symbols,
        timeframes: ["1m", "5m", "daily-regime"],
        sessions: ["New York AM", "regular session"],
        setupSummary: "Use external trend-following and volatility-targeting research only as a hypothesis seed for Bill's session-momentum lane.",
        biasRules: ["Require a programmatic trend or volatility-regime label before enabling any session-momentum test."],
        entryRules: ["Test continuation entries only after measured session expansion or breakout confirmation."],
        stopRules: ["Use volatility-scaled stops; do not use fixed discretionary stops from the research card."],
        targetRules: ["Compare trailing exits against fixed multiple exits during OOS testing."],
        riskRules: ["Paper-only until walk-forward, rolling OOS, and cost stress all pass."],
        confluence: ["trend-following research", "volatility targeting", "session expansion"],
        invalidationRules: ["Reject if edge disappears after fees, slippage, spread stress, or regime split."],
        evidence,
        automationReadiness: "low",
        confidence: 0.46,
        sourceTargetIds,
        sourceVideoIds: [],
        sourceVideoTitles: [],
        sourceChannels: [],
        sourceUrls
      });
    }

    if (
      containsAny(tagText, ["liquidity", "market-making", "execution-alpha", "microstructure", "prediction"]) ||
      containsAny(text, ["liquidity", "market maker", "spread", "mean reversion", "rebalance", "order book", "microstructure"])
    ) {
      candidates.push({
        id: strategyId("Research-seeded liquidity reversion stress test"),
        title: "Research-seeded liquidity reversion stress test",
        market: "futures",
        symbols,
        timeframes: ["1m", "5m"],
        sessions: ["early session", "New York AM"],
        setupSummary: "Use liquidity and microstructure research as a bounded seed for Bill's liquidity-reversion lane, not for market-making execution.",
        biasRules: ["Only test reversions after objectively measured liquidity extension or range imbalance."],
        entryRules: ["Enter only after the reversion trigger is confirmed by price returning inside the measured range."],
        stopRules: ["Stop outside the liquidity extension or volatility envelope."],
        targetRules: ["Target midpoint/range rebalance before extending targets."],
        riskRules: ["Disable market-making; Bill lacks L2, queue-position, and fill simulation."],
        confluence: ["liquidity extension", "spread/cost stress", "range rebalance"],
        invalidationRules: ["Reject if fills worsen materially under slippage/spread stress."],
        evidence,
        automationReadiness: "low",
        confidence: 0.44,
        sourceTargetIds,
        sourceVideoIds: [],
        sourceVideoTitles: [],
        sourceChannels: [],
        sourceUrls
      });
    }

    if (
      containsAny(tagText, ["0dte", "options-us", "volatility", "short-horizon"]) ||
      containsAny(text, ["0dte", "short-dated", "options", "gamma", "volatility", "vix"])
    ) {
      candidates.push({
        id: strategyId("Research-seeded opening auction volatility filter"),
        title: "Research-seeded opening auction volatility filter",
        market: "futures",
        symbols: symbols.filter((symbol) => symbol === "ES" || symbol === "NQ").length > 0 ? symbols.filter((symbol) => symbol === "ES" || symbol === "NQ") : ["ES", "NQ"],
        timeframes: ["1m", "5m"],
        sessions: ["opening range", "New York AM"],
        setupSummary: "Use options and volatility research as a filter candidate for opening-auction strategies, not as a standalone options lane.",
        biasRules: ["Classify high-volatility event days separately before testing opening-range reversals."],
        entryRules: ["Allow opening-auction tests only after the opening range and volatility regime are known."],
        stopRules: ["Use opening-range invalidation plus volatility-scaled max loss."],
        targetRules: ["Compare midpoint, VWAP, and opposing-liquidity exits in OOS."],
        riskRules: ["Stand down on event days where slippage/cost stress overwhelms the historical edge."],
        confluence: ["opening auction", "volatility regime", "short-horizon flow"],
        invalidationRules: ["Reject if the filter only improves in-sample performance."],
        evidence,
        automationReadiness: "low",
        confidence: 0.43,
        sourceTargetIds,
        sourceVideoIds: [],
        sourceVideoTitles: [],
        sourceChannels: [],
        sourceUrls
      });
    }

    if (
      containsAny(tagText, ["ict", "order-flow"]) ||
      containsAny(text, ["fair value gap", "fvg", "displacement", "liquidity sweep", "market structure shift", "order block"])
    ) {
      candidates.push({
        id: strategyId("Research-seeded ICT displacement ruleset"),
        title: "Research-seeded ICT displacement ruleset",
        market: "futures",
        symbols,
        timeframes: ["1m", "5m"],
        sessions: ["New York AM"],
        setupSummary: "Use ICT-language research only as explicit machine-testable rules for the ict-displacement research lane.",
        biasRules: ["Require a coded liquidity sweep plus displacement condition before any ICT test is admitted."],
        entryRules: ["Test FVG/retest entries only when the sweep, displacement, and invalidation can be computed from bars."],
        stopRules: ["Stop beyond the coded sweep or displacement origin."],
        targetRules: ["Target opposing coded liquidity or range rebalance."],
        riskRules: ["Keep ICT strategies research-only until transcript cards produce explicit measurable rules."],
        confluence: ["liquidity sweep", "displacement", "fair value gap"],
        invalidationRules: ["Reject any rule that depends on discretionary chart reading."],
        evidence,
        automationReadiness: "low",
        confidence: 0.4,
        sourceTargetIds,
        sourceVideoIds: [],
        sourceVideoTitles: [],
        sourceChannels: [],
        sourceUrls
      });
    }

    for (const candidate of candidates) {
      merged.set(candidate.id, mergeHypothesis(merged.get(candidate.id), candidate));
    }
  }

  return [...merged.values()]
    .sort((left, right) => right.confidence - left.confidence)
    .slice(0, 8);
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
