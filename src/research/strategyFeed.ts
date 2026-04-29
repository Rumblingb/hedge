import { readFile } from "node:fs/promises";
import { ALLOWED_TOPSTEP_MARKETS, SUPPORTED_STRATEGY_IDS, type SupportedStrategyId } from "../domain.js";
import { strategyHypothesesLatestPath, type StrategyHypothesis, type StrategyHypothesisArtifact } from "./strategyHypotheses.js";

export interface ResearchStrategyDirective {
  strategyId: SupportedStrategyId;
  score: number;
  sourceTitles: string[];
  symbols: string[];
  sessions: string[];
  evidence: string[];
}

export interface FuturesResearchStrategyFeed {
  artifactPath: string;
  generatedAt?: string;
  runId?: string;
  strategyCount: number;
  topStrategyTitles: string[];
  preferredStrategies: SupportedStrategyId[];
  preferredSymbols: string[];
  preferredSessions: string[];
  directives: ResearchStrategyDirective[];
}

export interface StrategyFeedOptions {
  maxAgeMs?: number;
  requiredRunId?: string;
}

const ALLOWED_SYMBOL_SET = new Set<string>(ALLOWED_TOPSTEP_MARKETS);
const SUPPORTED_STRATEGY_SET = new Set<string>(SUPPORTED_STRATEGY_IDS);

const SYMBOL_ALIASES: Array<{ needle: string; symbol: string }> = [
  { needle: "NASDAQ", symbol: "NQ" },
  { needle: "NAS100", symbol: "NQ" },
  { needle: "NQ", symbol: "NQ" },
  { needle: "SPX", symbol: "ES" },
  { needle: "S&P", symbol: "ES" },
  { needle: "ES", symbol: "ES" },
  { needle: "CRUDE", symbol: "CL" },
  { needle: "WTI", symbol: "CL" },
  { needle: "OIL", symbol: "CL" },
  { needle: "CL", symbol: "CL" },
  { needle: "GOLD", symbol: "GC" },
  { needle: "XAU", symbol: "GC" },
  { needle: "GC", symbol: "GC" },
  { needle: "EURO", symbol: "6E" },
  { needle: "EURUSD", symbol: "6E" },
  { needle: "6E", symbol: "6E" },
  { needle: "10Y", symbol: "ZN" },
  { needle: "10-YEAR", symbol: "ZN" },
  { needle: "TREASURY", symbol: "ZN" },
  { needle: "NOTE", symbol: "ZN" },
  { needle: "ZN", symbol: "ZN" }
];

function dedupe<T>(values: T[]): T[] {
  return Array.from(new Set(values));
}

function keywordHits(text: string, needles: string[]): number {
  return needles.reduce((count, needle) => count + (text.includes(needle) ? 1 : 0), 0);
}

function confidenceWeight(hypothesis: StrategyHypothesis): number {
  const readinessWeight = hypothesis.automationReadiness === "high"
    ? 0.8
    : hypothesis.automationReadiness === "medium"
      ? 0.45
      : 0.15;
  return readinessWeight + Math.max(0, Math.min(1, hypothesis.confidence));
}

function normalizeSymbol(raw: string): string | null {
  const upper = raw.trim().toUpperCase();
  if (!upper) return null;
  if (ALLOWED_SYMBOL_SET.has(upper)) return upper;
  for (const alias of SYMBOL_ALIASES) {
    if (upper.includes(alias.needle)) {
      return alias.symbol;
    }
  }
  return null;
}

function extractSymbols(hypothesis: StrategyHypothesis): string[] {
  const direct = hypothesis.symbols
    .map(normalizeSymbol)
    .filter((value): value is string => Boolean(value));
  if (direct.length > 0) {
    return dedupe(direct);
  }

  const corpus = [
    hypothesis.title,
    hypothesis.setupSummary,
    ...hypothesis.biasRules,
    ...hypothesis.entryRules,
    ...hypothesis.confluence,
    ...hypothesis.evidence
  ].join(" ").toUpperCase();

  return dedupe(
    SYMBOL_ALIASES
      .filter((alias) => corpus.includes(alias.needle))
      .map((alias) => alias.symbol)
  );
}

function inferStrategyScores(hypothesis: StrategyHypothesis): Array<{ strategyId: SupportedStrategyId; score: number }> {
  const corpus = [
    hypothesis.title,
    hypothesis.setupSummary,
    ...hypothesis.biasRules,
    ...hypothesis.entryRules,
    ...hypothesis.stopRules,
    ...hypothesis.targetRules,
    ...hypothesis.riskRules,
    ...hypothesis.confluence,
    ...hypothesis.invalidationRules,
    ...hypothesis.evidence
  ].join(" ").toLowerCase();
  const base = confidenceWeight(hypothesis);
  const scores: Array<{ strategyId: SupportedStrategyId; score: number }> = [
    {
      strategyId: "ict-displacement",
      score: base + keywordHits(corpus, [
        "ict",
        "displacement",
        "fair value gap",
        "fvg",
        "market structure shift",
        "mss",
        "order block",
        "breaker",
        "liquidity raid"
      ]) * 0.7
    },
    {
      strategyId: "opening-range-reversal",
      score: base + keywordHits(corpus, [
        "opening range",
        "open",
        "opening auction",
        "first hour",
        "opening swing",
        "open drive",
        "reversal"
      ]) * 0.5
    },
    {
      strategyId: "liquidity-reversion",
      score: base + keywordHits(corpus, [
        "liquidity sweep",
        "mean reversion",
        "reversion",
        "fade",
        "rebalance",
        "range",
        "sweep and reverse"
      ]) * 0.45
    },
    {
      strategyId: "session-momentum",
      score: base + keywordHits(corpus, [
        "trend day",
        "continuation",
        "momentum",
        "session expansion",
        "breakout",
        "impulse",
        "expansion"
      ]) * 0.45
    }
  ];

  return scores
    .filter((entry) => SUPPORTED_STRATEGY_SET.has(entry.strategyId) && entry.score >= 1.2)
    .sort((left, right) => right.score - left.score)
    .slice(0, 2);
}

function mergeDirective(
  current: ResearchStrategyDirective | undefined,
  args: {
    strategyId: SupportedStrategyId;
    score: number;
    hypothesis: StrategyHypothesis;
    symbols: string[];
  }
): ResearchStrategyDirective {
  const next = current ?? {
    strategyId: args.strategyId,
    score: 0,
    sourceTitles: [],
    symbols: [],
    sessions: [],
    evidence: []
  };
  next.score += args.score;
  next.sourceTitles = dedupe([...next.sourceTitles, args.hypothesis.title]).slice(0, 8);
  next.symbols = dedupe([...next.symbols, ...args.symbols]).slice(0, 8);
  next.sessions = dedupe([...next.sessions, ...args.hypothesis.sessions]).slice(0, 8);
  next.evidence = dedupe([...next.evidence, ...args.hypothesis.evidence]).slice(0, 8);
  return next;
}

export async function loadLatestResearchStrategyFeed(
  artifactPath?: string,
  options: StrategyFeedOptions = {}
): Promise<FuturesResearchStrategyFeed | null> {
  const resolvedArtifactPath = artifactPath ?? strategyHypothesesLatestPath();
  let artifact: StrategyHypothesisArtifact;
  try {
    artifact = JSON.parse(await readFile(resolvedArtifactPath, "utf8")) as StrategyHypothesisArtifact;
  } catch {
    return null;
  }
  if (options.requiredRunId && artifact.runId !== options.requiredRunId) {
    return null;
  }
  if (options.maxAgeMs && artifact.generatedAt) {
    const generatedAtMs = Date.parse(artifact.generatedAt);
    if (!Number.isFinite(generatedAtMs) || Date.now() - generatedAtMs > options.maxAgeMs) {
      return null;
    }
  }

  const directives = new Map<SupportedStrategyId, ResearchStrategyDirective>();
  const symbolScores = new Map<string, number>();
  const sessionScores = new Map<string, number>();

  for (const hypothesis of artifact.hypotheses ?? []) {
    const symbols = extractSymbols(hypothesis);
    const strategyScores = inferStrategyScores(hypothesis);
    for (const { strategyId, score } of strategyScores) {
      directives.set(strategyId, mergeDirective(directives.get(strategyId), {
        strategyId,
        score,
        hypothesis,
        symbols
      }));
      for (const symbol of symbols) {
        symbolScores.set(symbol, (symbolScores.get(symbol) ?? 0) + score);
      }
      for (const session of hypothesis.sessions) {
        sessionScores.set(session, (sessionScores.get(session) ?? 0) + score);
      }
    }
  }

  const rankedDirectives = [...directives.values()]
    .sort((left, right) => right.score - left.score)
    .map((directive) => ({
      ...directive,
      score: Number(directive.score.toFixed(4))
    }));

  return {
    artifactPath: resolvedArtifactPath,
    generatedAt: artifact.generatedAt,
    runId: artifact.runId,
    strategyCount: artifact.count ?? (artifact.hypotheses?.length ?? 0),
    topStrategyTitles: dedupe((artifact.hypotheses ?? []).map((hypothesis) => hypothesis.title)).slice(0, 5),
    preferredStrategies: rankedDirectives.map((directive) => directive.strategyId).slice(0, 3),
    preferredSymbols: [...symbolScores.entries()]
      .sort((left, right) => right[1] - left[1])
      .map(([symbol]) => symbol)
      .slice(0, 5),
    preferredSessions: [...sessionScores.entries()]
      .sort((left, right) => right[1] - left[1])
      .map(([session]) => session)
      .slice(0, 5),
    directives: rankedDirectives
  };
}
