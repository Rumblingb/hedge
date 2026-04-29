import { generateJson, type OllamaConfig } from "../llm/ollama.js";
import type { CorpusChunk } from "./corpus.js";
import { isNearDuplicate } from "./minhash.js";

export interface FilterThresholds {
  minChars: number;
  maxChars: number;
  minhashThreshold: number;
  classifierMinScore: number;
  judgeTopFraction: number;
  classifierSample: number;
}

export const DEFAULT_THRESHOLDS: FilterThresholds = {
  minChars: 200,          // Reduced from 400
  maxChars: 2000,
  minhashThreshold: 0.8,
  classifierMinScore: 2,  // Reduced from 3 (easier to pass)
  judgeTopFraction: 0.25, // Increased from 0.05 (keep more chunks)
  classifierSample: 600
};

export interface FilterDecision {
  chunk: CorpusChunk;
  verdict: "keep" | "reject";
  reason: string;
  stage: "length" | "dedup" | "classifier" | "judge" | "passed";
}

export function rejectByLength(chunk: CorpusChunk, thresholds: FilterThresholds): FilterDecision | null {
  if (chunk.text.length < thresholds.minChars) {
    return { chunk, verdict: "reject", reason: `too-short (<${thresholds.minChars})`, stage: "length" };
  }
  return null;
}

export function rejectByDedup(
  chunk: CorpusChunk,
  existing: Iterable<CorpusChunk>,
  thresholds: FilterThresholds
): FilterDecision | null {
  const existingSigs = Array.from(existing, (e) => e.minhash);
  if (isNearDuplicate(chunk.minhash, existingSigs, thresholds.minhashThreshold)) {
    return { chunk, verdict: "reject", reason: `near-duplicate (jaccard >= ${thresholds.minhashThreshold})`, stage: "dedup" };
  }
  return null;
}

export interface HeuristicClassifierResult {
  score: number;
  signals: string[];
}

const RESEARCH_TOPIC_HINTS: Record<string, string[]> = {
  prediction: ["prediction", "kalshi", "polymarket", "manifold", "liquidity", "market making", "scoring rule", "settlement"],
  "market-making": ["market making", "liquidity", "bid ask", "order book", "inventory"],
  "crypto-liquid": ["bitcoin", "btc", "ethereum", "eth", "crypto", "funding rate", "liquidation", "perpetual"],
  "short-horizon": ["5 minute", "5-minute", "15 minute", "15-minute", "intraday", "short horizon", "up or down", "0dte", "1dte", "same day expiring", "short-dated"],
  "volatility-targeting": ["volatility targeting", "target volatility", "inverse volatility scaling", "vol control", "volatility scaling"],
  liquidity: ["liquidity", "depth", "fill", "filled", "spread", "order book", "displayed size"],
  "execution-alpha": ["execution quality", "market making", "bid ask", "inventory", "price improvement", "theoretical price"],
  "futures-core": ["futures", "contract", "execution", "roll", "microstructure", "slippage"],
  microstructure: ["microstructure", "order flow", "adverse selection", "limit order", "market order", "price impact"],
  "order-flow": ["order flow", "trade flow", "execution", "fill", "liquidity"],
  backtest: ["backtest", "backtesting", "simulation", "slippage", "transaction cost"],
  oos: ["out of sample", "out-of-sample", "walk forward", "walk-forward", "robustness", "validation"],
  "risk-review": ["drawdown", "tail risk", "risk", "robustness", "transaction cost", "slippage"],
  "macro-rates": ["macro", "rates", "yield", "treasury", "fomc", "cpi", "payrolls", "inflation"],
  "event-driven": ["event driven", "event-driven", "announcement", "macro", "earnings", "surprise"],
  "trend-following": ["trend following", "time series momentum", "managed futures", "cta", "cross asset"],
  carry: ["carry", "roll yield", "term structure", "yield differential", "forward premium"],
  "market-neutral": ["market neutral", "relative value", "statistical arbitrage", "stat arb", "pair trading"],
  dispersion: ["dispersion", "correlation trading", "index options", "single stock options"],
  "options-us": ["option", "options", "implied volatility", "volatility surface", "gamma", "delta", "vega", "straddle", "iron condor", "gamma scalp", "0dte", "1dte", "short-dated"],
  volatility: ["volatility", "implied volatility", "realized volatility", "variance"]
};

function normalizeTopicKey(value: string): string {
  return value.toLowerCase().trim();
}

function buildTopicLexicon(topics: string[], tags: string[]): string[] {
  const phrases = new Set<string>();
  for (const value of [...topics, ...tags]) {
    const normalized = normalizeTopicKey(value);
    const hints = RESEARCH_TOPIC_HINTS[normalized];
    if (!hints) continue;
    for (const phrase of hints) {
      phrases.add(phrase);
    }
  }
  return [...phrases];
}

function topicRelevanceSignals(text: string, topics: string[], tags: string[]): { scoreDelta: number; signals: string[] } {
  const lexicon = buildTopicLexicon(topics, tags);
  if (lexicon.length === 0) {
    return { scoreDelta: 0, signals: [] };
  }

  const sample = text.slice(0, 2400).toLowerCase();
  const matches = lexicon.filter((phrase) => sample.includes(phrase));
  if (matches.length === 0) {
    return {
      scoreDelta: -2,
      signals: ["topic-miss"]
    };
  }

  if (matches.length >= 3) {
    return {
      scoreDelta: 1,
      signals: [`topic-hit:${matches.slice(0, 3).join("|")}`]
    };
  }

  return {
    scoreDelta: 0,
    signals: [`topic-thin:${matches.slice(0, 2).join("|")}`]
  };
}

export function heuristicClassifier(
  text: string,
  sampleChars: number,
  options: {
    topics?: string[];
    tags?: string[];
  } = {}
): HeuristicClassifierResult {
  const signals: string[] = [];
  const sample = text.slice(0, sampleChars);
  let score = 2;

  const tokenCount = sample.split(/\s+/).filter(Boolean).length;
  const avgWordLen =
    tokenCount > 0 ? sample.replace(/\s+/g, "").length / tokenCount : 0;

  if (avgWordLen >= 4 && avgWordLen <= 8) {
    score += 1;
    signals.push("avg-word-len-ok");
  } else {
    signals.push(`avg-word-len=${avgWordLen.toFixed(1)}`);
  }

  const punctRatio = (sample.match(/[.,;:!?]/g)?.length ?? 0) / Math.max(1, tokenCount);
  if (punctRatio > 0.03 && punctRatio < 0.25) {
    score += 1;
    signals.push("punct-density-ok");
  }

  const uniqWords = new Set(sample.toLowerCase().split(/\s+/)).size;
  const uniqRatio = uniqWords / Math.max(1, tokenCount);
  if (uniqRatio > 0.45) {
    score += 1;
    signals.push(`diversity=${uniqRatio.toFixed(2)}`);
  } else if (uniqRatio < 0.15) {
    score -= 1;
    signals.push(`low-diversity=${uniqRatio.toFixed(2)}`);
  }

  if (/cookie|privacy policy|subscribe to newsletter|all rights reserved/i.test(sample)) {
    score -= 2;
    signals.push("boilerplate-match");
  }

  const codeFraction = (sample.match(/```|function |class |import |def /g)?.length ?? 0);
  if (codeFraction > 0) {
    score += 1;
    signals.push(`code-signals=${codeFraction}`);
  }

  const topicSignals = topicRelevanceSignals(text, options.topics ?? [], options.tags ?? []);
  score += topicSignals.scoreDelta;
  signals.push(...topicSignals.signals);

  return { score: Math.max(0, Math.min(5, score)), signals };
}

export interface JudgeVerdict {
  score: number;
  rationale: string;
  topic_relevance: number;
  self_contained: boolean;
}

export async function judgeChunk(
  chunk: CorpusChunk,
  ollamaConfig: OllamaConfig,
  topics: string[]
): Promise<JudgeVerdict> {
  const snippet = chunk.text.slice(0, 1800);
  const prompt = `You are a strict quality judge for an autonomous research agent.

Topics the agent cares about: ${topics.join(", ")}.

Rate the following text snippet from 0-5 for its value as *durable knowledge* for the agent's corpus.
- 5: textbook-quality, dense, directly teaches a core concept.
- 4: solid documentation or paper, clearly written, on-topic.
- 3: useful notes or examples, partially on-topic.
- 2: thin, shallow, or partially off-topic.
- 1: noise, boilerplate, marketing.
- 0: junk, auto-generated, or unreadable.

Return strict JSON with keys: score (int 0-5), rationale (<=30 words), topic_relevance (float 0-1), self_contained (bool).

TEXT:
---
${snippet}
---`;
  const { value } = await generateJson<JudgeVerdict>(prompt, { temperature: 0, maxTokens: 180 }, ollamaConfig);
  if (typeof value.score !== "number") throw new Error(`judge returned no score: ${JSON.stringify(value)}`);
  value.score = Math.max(0, Math.min(5, Math.round(value.score)));
  value.topic_relevance = Math.max(0, Math.min(1, Number(value.topic_relevance ?? 0)));
  value.self_contained = Boolean(value.self_contained);
  return value;
}

export interface FilterRunResult {
  kept: CorpusChunk[];
  rejected: FilterDecision[];
  heuristicScored: number;
  judged: number;
}

export async function runFilterPipeline(
  fresh: CorpusChunk[],
  existing: CorpusChunk[],
  options: {
    thresholds?: FilterThresholds;
    topics: string[];
    ollamaConfig: OllamaConfig;
    useJudge: boolean;
  }
): Promise<FilterRunResult> {
  const thresholds = { ...DEFAULT_THRESHOLDS, ...(options.thresholds ?? {}) };
  const rejected: FilterDecision[] = [];
  const passedLengthAndDedup: CorpusChunk[] = [];
  const seen: CorpusChunk[] = [...existing];

  for (const chunk of fresh) {
    const lenReject = rejectByLength(chunk, thresholds);
    if (lenReject) {
      rejected.push(lenReject);
      continue;
    }
    const dupReject = rejectByDedup(chunk, seen, thresholds);
    if (dupReject) {
      rejected.push(dupReject);
      continue;
    }
    seen.push(chunk);
    passedLengthAndDedup.push(chunk);
  }

  let heuristicScored = 0;
  const passedClassifier: CorpusChunk[] = [];
  for (const chunk of passedLengthAndDedup) {
    const { score, signals } = heuristicClassifier(chunk.text, thresholds.classifierSample, {
      topics: options.topics,
      tags: chunk.tags
    });
    chunk.classifierScore = score;
    heuristicScored++;
    if (score < thresholds.classifierMinScore) {
      rejected.push({
        chunk,
        verdict: "reject",
        reason: `classifier ${score}/5 below ${thresholds.classifierMinScore} (${signals.join(",")})`,
        stage: "classifier"
      });
    } else {
      passedClassifier.push(chunk);
    }
  }

  let judged = 0;
  if (options.useJudge && passedClassifier.length > 0) {
    const topN = Math.max(1, Math.ceil(passedClassifier.length * thresholds.judgeTopFraction));
    const sorted = [...passedClassifier].sort((a, b) => (b.classifierScore ?? 0) - (a.classifierScore ?? 0));
    for (let i = 0; i < Math.min(topN, sorted.length); i++) {
      const chunk = sorted[i];
      try {
        const verdict = await judgeChunk(chunk, options.ollamaConfig, options.topics);
        chunk.judgeScore = verdict.score;
        chunk.judgeRationale = verdict.rationale;
        judged++;
        if (verdict.score < thresholds.classifierMinScore) {
          const idx = passedClassifier.indexOf(chunk);
          if (idx !== -1) passedClassifier.splice(idx, 1);
          rejected.push({
            chunk,
            verdict: "reject",
            reason: `judge ${verdict.score}/5 — ${verdict.rationale}`,
            stage: "judge"
          });
        }
      } catch (err) {
        chunk.judgeRationale = `judge-error: ${(err as Error).message.slice(0, 100)}`;
      }
    }
  }

  return { kept: passedClassifier, rejected, heuristicScored, judged };
}
