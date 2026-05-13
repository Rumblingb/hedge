import { mkdir, readFile, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { ALLOWED_TOPSTEP_MARKETS, SUPPORTED_STRATEGY_IDS, type SupportedStrategyId } from "../domain.js";
import { loadGraveyard, type HypothesisGraveyard } from "./graveyard.js";
import { loadLatestNoEdgeLedger } from "./noEdgeLedger.js";
import { assessHypothesisNovelty, isMachineTestableHypothesis, strategyHypothesesLatestPath, type StrategyHypothesis, type StrategyHypothesisArtifact } from "./strategyHypotheses.js";

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
  blockedStrategies?: SupportedStrategyId[];
  graveyard?: HypothesisGraveyard | null;
}

const ALLOWED_SYMBOL_SET = new Set<string>(ALLOWED_TOPSTEP_MARKETS);
const SUPPORTED_STRATEGY_SET = new Set<string>(SUPPORTED_STRATEGY_IDS);

const SYMBOL_ALIASES: Array<{ pattern: RegExp; symbol: string }> = [
  { pattern: /\b(?:NASDAQ|NAS100|NAS\s*100|NQ)\b/, symbol: "NQ" },
  { pattern: /\b(?:SPX|S&P(?:\s*500)?|E-?MINI|ES)\b/, symbol: "ES" },
  { pattern: /\b(?:CRUDE|WTI|OIL|CL)\b/, symbol: "CL" },
  { pattern: /\b(?:GOLD|XAU|GC)\b/, symbol: "GC" },
  { pattern: /\b(?:EURO|EURUSD|6E)\b/, symbol: "6E" },
  { pattern: /\b(?:10Y|10-YEAR|TREASURY(?:\s+NOTE)?|ZN)\b/, symbol: "ZN" }
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
    if (alias.pattern.test(upper)) {
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
      .filter((alias) => alias.pattern.test(corpus))
      .map((alias) => alias.symbol)
  );
}

function inferStrategyScores(hypothesis: StrategyHypothesis): Array<{ strategyId: SupportedStrategyId; score: number }> {
  if (!isMachineTestableHypothesis(hypothesis)) {
    return [];
  }

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

// Fallback: assign a minimal score to non-blocked strategies even without keyword matches.
// Prevents the feed from producing zero directives when all keyword-mapped strategies are blocked.
// Called by buildResearchStrategyFeedFromArtifact when the primary inference returns empty.
export function inferFallbackStrategyScores(
  hypothesis: StrategyHypothesis,
  blockedStrategies: Set<string>
): Array<{ strategyId: SupportedStrategyId; score: number }> {
  if (!isMachineTestableHypothesis(hypothesis)) return [];
  const base = Math.max(0.2, confidenceWeight(hypothesis) * 0.3); // Heavily discounted for no keyword match
  // Non-blocked strategies that have genuine economic rationale
  const fallbackIds: SupportedStrategyId[] = [
    "capitulation-score", "vol-risk-premium", "two-level-uncertainty",
    "drift-regime-csm", "gamma-stability", "drawdown-momentum",
    "intraday-momentum", "monthly-seasonality", "gap-fade-regime",
    "regime-locked-momentum", "short-term-reversal", "opening-stop-hunt",
    "kronos-direction", "hmm-pairs-arb", "llm-momentum-gate",
    "push-response-anomaly", "network-momentum", "optimal-cost-pairs",
    "event-spike-fade", "post-news-settlement", "options-selling-framework",
    // WQ Alphas — institutional alpha signals
    "wq-alpha-001", "wq-alpha-002", "wq-alpha-003", "wq-alpha-006",
    "wq-alpha-007", "wq-alpha-008", "wq-alpha-009", "wq-alpha-012",
    "wq-alpha-020", "wq-alpha-021", "wq-alpha-024", "wq-alpha-033",
    "wq-alpha-044", "wq-alpha-049", "wq-alpha-053", "wq-alpha-054",
    "wq-alpha-057", "wq-alpha-065", "wq-alpha-083", "wq-alpha-101",
  ];
  return fallbackIds
    .filter((id) => !blockedStrategies.has(id))
    .map((id) => ({ strategyId: id, score: base }))
    .sort((a, b) => b.score - a.score)
    .slice(0, 5);
}

function applyNoveltyEvidence(hypothesis: StrategyHypothesis, graveyard: HypothesisGraveyard | null | undefined): StrategyHypothesis | null {
  if (!graveyard) {
    return hypothesis;
  }
  const novelty = assessHypothesisNovelty(hypothesis, graveyard);
  if (novelty.verdict === "duplicate") {
    return null;
  }
  if (novelty.verdict === "variant") {
    return {
      ...hypothesis,
      evidence: [
        `Variant of tested idea "${novelty.matchedTitle ?? novelty.matchedEntryId ?? "unknown"}"; test only changed rule/filter and require incremental OOS lift. Mechanics hash sha1:${novelty.mechanicsHash}.`,
        ...hypothesis.evidence
      ].slice(0, 8),
      confidence: Math.min(hypothesis.confidence, 0.55)
    };
  }
  return {
    ...hypothesis,
    evidence: [
      `New mechanics hash sha1:${novelty.mechanicsHash}.`,
      ...hypothesis.evidence
    ].slice(0, 8)
  };
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

export function strategyFeedLatestPath(env: NodeJS.ProcessEnv = process.env): string {
  return resolve(env.BILL_RESEARCH_STRATEGY_FEED_PATH ?? ".rumbling-hedge/research/researcher/strategy-feed.latest.json");
}

export function buildResearchStrategyFeedFromArtifact(
  artifact: StrategyHypothesisArtifact,
  artifactPath: string,
  options: Pick<StrategyFeedOptions, "blockedStrategies" | "graveyard"> = {}
): FuturesResearchStrategyFeed {
  const directives = new Map<SupportedStrategyId, ResearchStrategyDirective>();
  const symbolScores = new Map<string, number>();
  const sessionScores = new Map<string, number>();
  const blockedStrategies = new Set(options.blockedStrategies ?? []);

  const eligibleHypotheses: StrategyHypothesis[] = [];
  for (const rawHypothesis of artifact.hypotheses ?? []) {
    const hypothesis = applyNoveltyEvidence(rawHypothesis, options.graveyard);
    if (!hypothesis) {
      continue;
    }
    eligibleHypotheses.push(hypothesis);
    const symbols = extractSymbols(hypothesis);
    let strategyScores = inferStrategyScores(hypothesis)
      .filter((entry) => !blockedStrategies.has(entry.strategyId));
    // If primary inference produced nothing (all keyword-mapped strategies blocked),
    // fall back to non-blocked strategies with minimal scores.
    if (strategyScores.length === 0) {
      strategyScores = inferFallbackStrategyScores(hypothesis, blockedStrategies);
    }
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
    artifactPath,
    generatedAt: artifact.generatedAt,
    runId: artifact.runId,
    strategyCount: eligibleHypotheses.length,
    topStrategyTitles: dedupe(eligibleHypotheses.map((hypothesis) => hypothesis.title)).slice(0, 5),
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

export async function writeResearchStrategyFeedArtifact(args: {
  artifact: StrategyHypothesisArtifact;
  artifactPath: string;
  outputPath?: string;
  blockedStrategies?: SupportedStrategyId[];
}): Promise<{ outputPath: string; feed: FuturesResearchStrategyFeed }> {
  const outputPath = args.outputPath ?? strategyFeedLatestPath();
  const noEdgeLedger = args.blockedStrategies === undefined && process.env.NODE_ENV !== "test"
    ? await loadLatestNoEdgeLedger()
    : null;
  const graveyard = process.env.NODE_ENV !== "test" ? await loadGraveyard() : null;
  const feed = buildResearchStrategyFeedFromArtifact(args.artifact, args.artifactPath, {
    blockedStrategies: args.blockedStrategies ?? noEdgeLedger?.nonPromotableStrategies ?? noEdgeLedger?.blockedStrategies,
    graveyard
  });
  await mkdir(dirname(outputPath), { recursive: true });
  await writeFile(outputPath, `${JSON.stringify(feed, null, 2)}\n`, "utf8");
  return { outputPath, feed };
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

  return buildResearchStrategyFeedFromArtifact(artifact, resolvedArtifactPath, {
    blockedStrategies: options.blockedStrategies,
    graveyard: options.graveyard
  });
}
