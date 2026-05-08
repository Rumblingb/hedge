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
import type { GraveyardEntry, HypothesisGraveyard } from "./graveyard.js";

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

export type StrategyHypothesisNoveltyVerdict = "new" | "variant" | "duplicate";

export interface StrategyHypothesisNovelty {
  verdict: StrategyHypothesisNoveltyVerdict;
  mechanicsHash: string;
  matchedEntryId?: string;
  matchedTitle?: string;
  similarity?: number;
  reason: string;
}

export interface ResearchChunkStrategySeed {
  sourceId: string;
  sourceKind: string;
  url?: string;
  title?: string;
  text: string;
  tags?: string[];
}

const BASE_EXTRACTION_SYSTEM_PROMPT = [
  "You extract systematic futures trading hypotheses from ICT-style YouTube transcripts.",
  "Return only explicit or strongly implied trading setups that could sharpen a futures automation lab.",
  "Focus on bias, session framing, liquidity, displacement, MSS, FVG, order blocks, entries, stops, targets, and risk controls.",
  "Do not invent numerical rules that are absent from the transcript.",
  "If a chunk is motivational or vague, return zero strategies for it.",
  "Prefer concise, machine-usable bullet-like rules in arrays.",
  "Keep evidence quotes short and verbatim.",
  "Return strict JSON."
].join(" ");

function buildExtractionSystemPrompt(graveyardContext = ""): string {
  return BASE_EXTRACTION_SYSTEM_PROMPT + graveyardContext;
}


export function strategyHypothesesLatestPath(env: NodeJS.ProcessEnv = process.env): string {
  return resolve(env.BILL_STRATEGY_HYPOTHESES_LATEST_PATH ?? ".rumbling-hedge/research/researcher/strategy-hypotheses.latest.json");
}

export function strategyHypothesesRunDir(env: NodeJS.ProcessEnv = process.env): string {
  return resolve(env.BILL_STRATEGY_HYPOTHESES_RUN_DIR ?? ".rumbling-hedge/research/researcher/strategy-hypotheses");
}

function strategyId(title: string): string {
  return createHash("sha1").update(title.toLowerCase().trim()).digest("hex").slice(0, 16);
}

function normalizedMechanicsText(hypothesis: Pick<StrategyHypothesis,
  "setupSummary" | "biasRules" | "entryRules" | "stopRules" | "targetRules" | "riskRules" | "confluence" | "invalidationRules"
>): string {
  return [
    hypothesis.setupSummary,
    ...hypothesis.biasRules,
    ...hypothesis.entryRules,
    ...hypothesis.stopRules,
    ...hypothesis.targetRules,
    ...hypothesis.riskRules,
    ...hypothesis.confluence,
    ...hypothesis.invalidationRules
  ]
    .join(" ")
    .toLowerCase()
    .replace(/[^a-z0-9.%:/\s-]/g, " ")
    .replace(/\b(the|a|an|and|or|to|of|for|with|after|before|when|then|only|use|using)\b/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function tokenSet(text: string): Set<string> {
  return new Set(text.split(/\s+/).filter((token) => token.length >= 3));
}

function jaccard(left: Set<string>, right: Set<string>): number {
  if (left.size === 0 || right.size === 0) return 0;
  let intersection = 0;
  for (const token of left) {
    if (right.has(token)) intersection += 1;
  }
  return intersection / (left.size + right.size - intersection);
}

export function hypothesisMechanicsHash(hypothesis: Pick<StrategyHypothesis,
  "setupSummary" | "biasRules" | "entryRules" | "stopRules" | "targetRules" | "riskRules" | "confluence" | "invalidationRules"
>): string {
  return createHash("sha1").update(normalizedMechanicsText(hypothesis)).digest("hex").slice(0, 16);
}

function entryMechanicsTexts(entry: GraveyardEntry): string[] {
  return entry.mechanics
    .map((value) => value.trim())
    .filter(Boolean)
    .filter((value) => !/^sha1:[0-9a-f]{16}$/i.test(value));
}

function entryMechanicsHashes(entry: GraveyardEntry): string[] {
  return [
    entry.mechanicsHash,
    ...entry.mechanics
      .map((value) => value.trim())
      .filter((value) => /^sha1:[0-9a-f]{16}$/i.test(value))
      .map((value) => value.replace(/^sha1:/i, ""))
  ].filter((value): value is string => Boolean(value));
}

function graveyardEntryActive(entry: GraveyardEntry, now = new Date()): boolean {
  if (entry.status === "dead") return true;
  if (entry.status === "cooling" && entry.reviewAfter) {
    return new Date(entry.reviewAfter) > now;
  }
  return false;
}

export function assessHypothesisNovelty(
  hypothesis: StrategyHypothesis,
  graveyard: HypothesisGraveyard,
  options: {
    duplicateSimilarity?: number;
    variantSimilarity?: number;
    now?: Date;
  } = {}
): StrategyHypothesisNovelty {
  const mechanicsHash = hypothesisMechanicsHash(hypothesis);
  const activeEntries = graveyard.entries.filter((entry) => graveyardEntryActive(entry, options.now));
  const exactIdOrTitle = activeEntries.find((entry) =>
    entry.id === hypothesis.id || entry.title.trim().toLowerCase() === hypothesis.title.trim().toLowerCase()
  );
  if (exactIdOrTitle) {
    return {
      verdict: "duplicate",
      mechanicsHash,
      matchedEntryId: exactIdOrTitle.id,
      matchedTitle: exactIdOrTitle.title,
      similarity: 1,
      reason: "exact hypothesis id/title is already in the tested-failure graveyard"
    };
  }

  const exactMechanics = activeEntries.find((entry) => entryMechanicsHashes(entry).includes(mechanicsHash));
  if (exactMechanics) {
    return {
      verdict: "duplicate",
      mechanicsHash,
      matchedEntryId: exactMechanics.id,
      matchedTitle: exactMechanics.title,
      similarity: 1,
      reason: "mechanics hash is already in the tested-failure graveyard"
    };
  }

  const hypothesisTokens = tokenSet(normalizedMechanicsText(hypothesis));
  let best: { entry: GraveyardEntry; similarity: number } | null = null;
  for (const entry of activeEntries) {
    for (const mechanics of entryMechanicsTexts(entry)) {
      const similarity = jaccard(hypothesisTokens, tokenSet(normalizedMechanicsText({
        setupSummary: mechanics,
        biasRules: [],
        entryRules: [],
        stopRules: [],
        targetRules: [],
        riskRules: [],
        confluence: [],
        invalidationRules: []
      })));
      if (!best || similarity > best.similarity) {
        best = { entry, similarity };
      }
    }
  }

  const duplicateSimilarity = options.duplicateSimilarity ?? 0.9;
  const variantSimilarity = options.variantSimilarity ?? 0.55;
  if (best && best.similarity >= duplicateSimilarity) {
    return {
      verdict: "duplicate",
      mechanicsHash,
      matchedEntryId: best.entry.id,
      matchedTitle: best.entry.title,
      similarity: Number(best.similarity.toFixed(4)),
      reason: "mechanics are effectively the same as a tested failed idea"
    };
  }
  if (best && best.similarity >= variantSimilarity) {
    return {
      verdict: "variant",
      mechanicsHash,
      matchedEntryId: best.entry.id,
      matchedTitle: best.entry.title,
      similarity: Number(best.similarity.toFixed(4)),
      reason: "mechanics overlap with a failed idea; test only the changed rule/filter and compare incremental lift"
    };
  }

  return {
    verdict: "new",
    mechanicsHash,
    reason: "no active graveyard match"
  };
}

function compactEvidence(text: string): string {
  const normalized = text.replace(/\s+/g, " ").trim();
  return normalized.length > 220 ? `${normalized.slice(0, 217)}...` : normalized;
}

function evidenceSnippets(text: string, needles: string[], limit = 4): string[] {
  return text
    .replace(/\s+/g, " ")
    .split(/(?<=[.!?])\s+/)
    .map((sentence) => sentence.trim())
    .filter((sentence) => sentence.length >= 24)
    .filter((sentence) => containsAny(sentence, needles))
    .map((sentence) => compactEvidence(sentence))
    .slice(0, limit);
}

function containsAny(text: string, needles: string[]): boolean {
  const lower = text.toLowerCase();
  return needles.some((needle) => lower.includes(needle));
}

const STRATEGY_SEED_TAGS = new Set([
  "backtest",
  "carry",
  "dispersion",
  "execution-alpha",
  "ict",
  "liquidity",
  "market-making",
  "market-neutral",
  "microstructure",
  "oos",
  "options-us",
  "order-flow",
  "risk-review",
  "short-horizon",
  "trend-following",
  "volatility",
  "volatility-targeting"
]);

const STRATEGY_SEED_BLOCK_TAGS = new Set([
  "context-only",
  "news",
  "no-strategy-seed",
  "raw-transcript"
]);

const DURABLE_RESEARCH_CUES = [
  "adverse selection",
  "backtest",
  "breaker block",
  "breakout",
  "carry",
  "cot",
  "cost stress",
  "deflated sharpe",
  "drawdown",
  "fair value gap",
  "fvg",
  "gap fill",
  "inventory",
  "liquidity sweep",
  "managed futures",
  "market microstructure",
  "market structure shift",
  "mean reversion",
  "momentum",
  "opening range",
  "optimal execution",
  "order block",
  "order book",
  "order flow",
  "order flow imbalance",
  "out of sample",
  "out-of-sample",
  "price impact",
  "queue position",
  "regime split",
  "robustness",
  "roll yield",
  "sharpe",
  "slippage",
  "spread",
  "statistical arbitrage",
  "time series momentum",
  "transaction cost",
  "trend following",
  "vwap",
  "volatility scaling",
  "volatility target",
  "walk forward",
  "walk-forward"
];

function isGenericNewsChunk(chunk: ResearchChunkStrategySeed): boolean {
  const source = [chunk.sourceId, chunk.title, chunk.url].filter(Boolean).join(" ").toLowerCase();
  return /(^|[-_\s])(news|latest-stock-market-news|stock-market-news|market-news)([-_\s]|$)/i.test(source)
    || source.includes("yahoo-finance-stock-market-news")
    || source.includes("latest stock market news")
    || source.includes("finance.yahoo.com/news");
}

export function isStrategySeedEligible(chunk: ResearchChunkStrategySeed): boolean {
  const tags = (chunk.tags ?? []).map((tag) => tag.toLowerCase());
  if (tags.some((tag) => STRATEGY_SEED_BLOCK_TAGS.has(tag))) {
    return false;
  }
  if (isGenericNewsChunk(chunk)) {
    return false;
  }

  const hasSeedTag = tags.some((tag) => STRATEGY_SEED_TAGS.has(tag));
  if (!hasSeedTag) {
    return false;
  }

  const text = [chunk.title, tags.join(" "), chunk.text].filter(Boolean).join("\n").toLowerCase();
  const durableCueCount = DURABLE_RESEARCH_CUES.filter((cue) => text.includes(cue)).length;
  if (chunk.sourceKind === "arxiv" || chunk.sourceKind === "scholar" || chunk.sourceKind === "github-repo") {
    return durableCueCount > 0 || tags.includes("backtest") || tags.includes("oos");
  }

  return durableCueCount >= 2;
}

function inferSymbolsFromChunk(text: string, fallback: string[] = ["ES", "NQ"]): string[] {
  const upper = text.toUpperCase();
  const symbols = [
    { symbol: "NQ", patterns: [/\bNQ\b/, /\bNASDAQ\b/, /\bNAS100\b/] },
    { symbol: "ES", patterns: [/\bES\b/, /\bS&P\b/, /\bSPX\b/, /\bE-MINI\b/] },
    { symbol: "CL", patterns: [/\bCL\b/, /\bCRUDE\b/, /\bWTI\b/, /\bOIL\b/] },
    { symbol: "GC", patterns: [/\bGC\b/, /\bGOLD\b/, /\bXAU\b/] },
    { symbol: "6E", patterns: [/\b6E\b/, /\bEURO\b/, /\bEURUSD\b/] },
    { symbol: "ZN", patterns: [/\bZN\b/, /\b10Y\b/, /\b10-YEAR\b/, /\bTREASURY NOTE\b/] }
  ];
  const inferred = symbols
    .filter((entry) => entry.patterns.some((pattern) => pattern.test(upper)))
    .map((entry) => entry.symbol);
  return inferred.length > 0 ? inferred : fallback;
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

export function dedupeStrategyHypotheses(hypotheses: StrategyHypothesis[]): StrategyHypothesis[] {
  const merged = new Map<string, StrategyHypothesis>();
  for (const hypothesis of hypotheses) {
    const key = hypothesisMechanicsHash(hypothesis);
    merged.set(key, mergeHypothesis(merged.get(key), hypothesis));
  }
  return [...merged.values()].sort((left, right) => right.confidence - left.confidence);
}

export function deriveStrategyHypothesesFromResearchChunks(chunks: ResearchChunkStrategySeed[]): StrategyHypothesis[] {
  const merged = new Map<string, StrategyHypothesis>();

  for (const chunk of chunks) {
    if (!isStrategySeedEligible(chunk)) {
      continue;
    }
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

export function isMachineTestableHypothesis(hypothesis: StrategyHypothesis): boolean {
  const requiredRuleGroups = [
    hypothesis.entryRules,
    hypothesis.stopRules,
    hypothesis.targetRules,
    hypothesis.riskRules,
    hypothesis.invalidationRules
  ];
  if (requiredRuleGroups.some((rules) => rules.length === 0)) {
    return false;
  }
  if (hypothesis.evidence.length === 0 || hypothesis.symbols.length === 0 || hypothesis.sessions.length === 0) {
    return false;
  }

  const corpus = [
    hypothesis.setupSummary,
    ...hypothesis.biasRules,
    ...hypothesis.entryRules,
    ...hypothesis.stopRules,
    ...hypothesis.targetRules,
    ...hypothesis.riskRules,
    ...hypothesis.invalidationRules
  ].join(" ").toLowerCase();
  const vagueOnly = [
    "be patient",
    "wait for confirmation",
    "trust the model",
    "follow intuition",
    "high probability",
    "smart money"
  ];
  const measurableTerms = [
    "close",
    "break",
    "sweep",
    "stop",
    "target",
    "range",
    "high",
    "low",
    "atr",
    "rr",
    "r/r",
    "minutes",
    "session",
    "volume",
    "displacement",
    "fair value gap",
    "fvg",
    "market structure"
  ];

  return !vagueOnly.some((phrase) => corpus.includes(phrase))
    && measurableTerms.some((term) => corpus.includes(term));
}

function automationReadinessForRules(raw: unknown, hypothesis: StrategyHypothesis): StrategyHypothesis["automationReadiness"] {
  if (!isMachineTestableHypothesis(hypothesis)) {
    return "low";
  }
  return raw === "high" || raw === "medium" ? raw : "low";
}

export function deriveFallbackTranscriptHypotheses(source: TranscriptSourceMeta, transcriptText = source.transcriptText): StrategyHypothesis[] {
  const lower = transcriptText.toLowerCase();
  const ictTerms = [
    "fair value gap",
    "fvg",
    "displacement",
    "liquidity sweep",
    "sweep",
    "market structure shift",
    "mss",
    "order block"
  ];
  const riskTerms = ["stop", "risk", "invalidation", "target", "liquidity pool", "range", "high", "low"];
  const matchedIctTerms = ictTerms.filter((term) => lower.includes(term));
  if (matchedIctTerms.length < 2 || !containsAny(lower, riskTerms)) {
    return [];
  }

  const evidence = evidenceSnippets(transcriptText, [...ictTerms, ...riskTerms]);
  if (evidence.length === 0) {
    return [];
  }

  const title = "Transcript-seeded ICT displacement replay";
  const hypothesis: StrategyHypothesis = {
    id: strategyId(`${title}:${source.videoId}`),
    title,
    market: "futures",
    symbols: inferSymbolsFromChunk(source.title),
    timeframes: ["1m", "5m"],
    sessions: ["New York AM"],
    setupSummary: "Fallback extractor captured an ICT-style sweep/displacement/FVG idea from transcript text after model extraction failed or returned no usable strategies.",
    biasRules: ["Require a coded session liquidity sweep and displacement condition before any replay test is admitted."],
    entryRules: ["Enter only after bars show liquidity sweep, displacement, and fair value gap or retest conditions from the transcript."],
    stopRules: ["Stop beyond the coded sweep extreme or displacement origin."],
    targetRules: ["Target opposing coded liquidity, prior session high/low, or range rebalance when explicitly present in the setup."],
    riskRules: ["Keep paper-only; reject if OOS, spread, fee, and slippage stress do not survive."],
    confluence: Array.from(new Set(matchedIctTerms)).slice(0, 6),
    invalidationRules: ["No trade if the sweep, displacement, or fair value gap/retest cannot be computed from bars."],
    evidence,
    automationReadiness: "low",
    confidence: 0.45,
    sourceTargetIds: [source.targetId],
    sourceVideoIds: [source.videoId],
    sourceVideoTitles: [source.title],
    sourceChannels: [source.channel ?? ""].filter(Boolean),
    sourceUrls: [source.url]
  };

  return isMachineTestableHypothesis(hypothesis) ? [hypothesis] : [];
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
    graveyardContext?: string;
  }
): Promise<{ model: string; strategies: StrategyHypothesisEnvelope["strategies"] }> {
  if (args.provider.kind === "cloud") {
    const { value, model } = await generateCloudJson<StrategyHypothesisEnvelope>(
      prompt,
      {
        system: buildExtractionSystemPrompt(args.graveyardContext),
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
      system: buildExtractionSystemPrompt(args.graveyardContext),
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
  policy: ResearcherPolicy,
  graveyardContext = ""
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

    let extracted: { model: string; strategies: StrategyHypothesisEnvelope["strategies"] };
    try {
      extracted = await extractChunkStrategies(prompt, {
        provider,
        model: provider.kind === "cloud" ? buildOpenAiCompatibleConfigFromEnv(process.env).defaultModel : policy.llm.generateModel,
        graveyardContext
      });
      model = extracted.model;
      if (extracted.strategies.length === 0) {
        extracted.strategies = deriveFallbackTranscriptHypotheses(source, transcriptChunk);
        if (extracted.strategies.length > 0) {
          model = `${model}+deterministic-fallback`;
        }
      }
    } catch {
      extracted = {
        model: "deterministic-transcript-fallback",
        strategies: deriveFallbackTranscriptHypotheses(source, transcriptChunk)
      };
      model = extracted.model;
    }

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
      next.automationReadiness = automationReadinessForRules(raw.automationReadiness, next);
      const confidence = clampConfidence(raw.confidence);
      next.confidence = Math.max(next.confidence, isMachineTestableHypothesis(next) ? confidence : Math.min(confidence, 0.35));
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
