import { mkdir, readFile, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";

export type PmFuturesSymbol = "ES" | "NQ" | "CL" | "GC" | "ZN" | "6E";
export type PmFuturesBias = "bullish" | "bearish" | "risk-on" | "risk-off" | "inflation-up" | "rates-down" | "neutral";
export type PmFuturesSource = "prediction-review" | "prediction-copy-demo";

export interface PmFuturesIndicator {
  source: PmFuturesSource;
  symbol: PmFuturesSymbol;
  bias: PmFuturesBias;
  confidence: number;
  eventKey: string;
  summary: string;
  evidence: string[];
}

export interface PmFuturesBridgeReport {
  command: "pm-futures-bridge";
  generatedAt: string;
  status: "active-context" | "no-usable-context";
  authority: "indicator-only";
  executionAllowed: false;
  sourcePaths: {
    predictionReviewPath: string;
    predictionCopyDemoPath: string;
  };
  indicators: PmFuturesIndicator[];
  blockers: string[];
  nextAction: string;
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

async function readJsonSafe<T>(path: string): Promise<T | null> {
  try {
    return JSON.parse(await readFile(path, "utf8")) as T;
  } catch {
    return null;
  }
}

function textOf(...values: unknown[]): string {
  return values
    .filter((value): value is string => typeof value === "string")
    .join(" ")
    .toLowerCase();
}

function uniqIndicators(indicators: PmFuturesIndicator[]): PmFuturesIndicator[] {
  const seen = new Set<string>();
  const out: PmFuturesIndicator[] = [];
  for (const indicator of indicators.sort((a, b) => b.confidence - a.confidence)) {
    const key = `${indicator.source}:${indicator.symbol}:${indicator.bias}:${indicator.eventKey}`;
    if (seen.has(key)) continue;
    seen.add(key);
    out.push(indicator);
  }
  return out.slice(0, 12);
}

function symbolBiasesFromText(text: string): Array<{ symbol: PmFuturesSymbol; bias: PmFuturesBias; reason: string }> {
  const signals: Array<{ symbol: PmFuturesSymbol; bias: PmFuturesBias; reason: string }> = [];
  if (/\b(bitcoin|btc|ethereum|eth|crypto|nasdaq|nvidia|nvda|tesla|tech|risk assets?)\b/.test(text)) {
    signals.push({ symbol: "NQ", bias: "risk-on", reason: "crypto/tech prediction market maps to NQ risk appetite" });
    signals.push({ symbol: "ES", bias: "risk-on", reason: "broad risk prediction market maps to ES risk appetite" });
  }
  if (/\b(recession|unemployment|layoffs|crash|bank crisis|default|war|ceasefire|iran|ukraine|russia|geopolitic)\b/.test(text)) {
    signals.push({ symbol: "ES", bias: "risk-off", reason: "macro/geopolitical prediction market maps to equity risk-off context" });
    signals.push({ symbol: "NQ", bias: "risk-off", reason: "macro/geopolitical prediction market maps to growth risk-off context" });
    signals.push({ symbol: "GC", bias: "bullish", reason: "tail-risk prediction market maps to gold hedge context" });
  }
  if (/\b(oil|wti|brent|crude|opec|hormuz|inventory|gasoline|energy)\b/.test(text)) {
    signals.push({ symbol: "CL", bias: "bullish", reason: "energy prediction market maps to crude-oil context" });
  }
  if (/\b(cpi|inflation|ppi|tariff|commodity|commodities)\b/.test(text)) {
    signals.push({ symbol: "GC", bias: "inflation-up", reason: "inflation prediction market maps to gold/inflation hedge context" });
    signals.push({ symbol: "ZN", bias: "bearish", reason: "inflation prediction market maps to rates pressure context" });
  }
  if (/\b(fed|fomc|rate cut|rate cuts|interest rate cut|easing|dovish)\b/.test(text)) {
    signals.push({ symbol: "ZN", bias: "rates-down", reason: "rate-cut prediction market maps to Treasury futures context" });
    signals.push({ symbol: "NQ", bias: "risk-on", reason: "rate-cut prediction market maps to growth/risk context" });
  }
  if (/\b(rate hike|higher for longer|hawkish|treasury yield|yields rise)\b/.test(text)) {
    signals.push({ symbol: "ZN", bias: "bearish", reason: "hawkish/rate-hike prediction market maps to Treasury futures context" });
    signals.push({ symbol: "NQ", bias: "risk-off", reason: "hawkish/rate-hike prediction market maps to growth risk context" });
  }
  if (/\b(euro|ecb|eur|dollar|dxy|fx|currency)\b/.test(text)) {
    signals.push({ symbol: "6E", bias: "neutral", reason: "FX prediction market maps to euro futures context but direction is unresolved" });
  }
  return signals;
}

function confidenceFromReview(top: any): number {
  const matchScore = Number(top?.matchScore ?? 0);
  const netEdge = Number(top?.netEdgePct ?? 0);
  const verdictBoost = top?.verdict === "paper-trade" ? 0.25 : top?.verdict === "watch" ? 0.12 : 0;
  return Number(clamp(matchScore * 0.55 + clamp(netEdge / 10, 0, 0.25) + verdictBoost, 0.05, 0.95).toFixed(3));
}

function indicatorsFromPredictionReview(doc: any): PmFuturesIndicator[] {
  const review = doc?.review ?? doc;
  const top = review?.topCandidate;
  if (!top) return [];
  const text = textOf(top.candidateId, top.venuePair, top.normalizedEventKey, top.normalizedQuestionKey, top.recommendation);
  const signals = symbolBiasesFromText(text);
  const confidence = confidenceFromReview(top);
  return signals.map((signal) => ({
    source: "prediction-review",
    symbol: signal.symbol,
    bias: signal.bias,
    confidence,
    eventKey: String(top.candidateId ?? "prediction-top-candidate"),
    summary: `${signal.symbol} ${signal.bias} context from PM top candidate`,
    evidence: [
      signal.reason,
      `candidate=${top.candidateId ?? "unknown"}`,
      `verdict=${top.verdict ?? "unknown"}`,
      `netEdgePct=${top.netEdgePct ?? "unknown"}`,
      `matchScore=${top.matchScore ?? "unknown"}`
    ]
  }));
}

function indicatorsFromCopyDemo(doc: any): PmFuturesIndicator[] {
  const ideas = Array.isArray(doc?.ideas) ? doc.ideas : [];
  const indicators: PmFuturesIndicator[] = [];
  for (const idea of ideas.slice(0, 8)) {
    const text = textOf(idea?.slug, idea?.title, idea?.outcome, idea?.exhaust?.domain, idea?.exhaust?.inferredStrategy);
    const signals = symbolBiasesFromText(text);
    const confidence = Number(clamp(
      Number(idea?.consensusPct ?? 0) * 0.45
      + clamp(Number(idea?.supporterCount ?? 0) / 5, 0, 0.25)
      + clamp(Number(idea?.totalCurrentValue ?? 0) / 25_000, 0, 0.2)
      + (idea?.action === "shadow-buy" ? 0.1 : 0),
      0.05,
      0.9
    ).toFixed(3));
    for (const signal of signals) {
      indicators.push({
        source: "prediction-copy-demo",
        symbol: signal.symbol,
        bias: signal.bias,
        confidence,
        eventKey: String(idea?.id ?? idea?.slug ?? "copy-demo-idea"),
        summary: `${signal.symbol} ${signal.bias} context from PM copy-demo idea`,
        evidence: [
          signal.reason,
          `idea=${idea?.slug ?? "unknown"}`,
          `action=${idea?.action ?? "unknown"}`,
          `supporters=${idea?.supporterCount ?? "unknown"}`,
          `exhaust=${idea?.exhaust?.inferredStrategy ?? "unknown"}`
        ]
      });
    }
  }
  return indicators;
}

export async function buildPmFuturesBridgeReport(args: {
  predictionReviewPath?: string;
  predictionCopyDemoPath?: string;
  outputPath?: string;
  env?: NodeJS.ProcessEnv;
  now?: () => string;
} = {}): Promise<PmFuturesBridgeReport> {
  const env = args.env ?? process.env;
  const predictionReviewPath = resolve(args.predictionReviewPath ?? env.BILL_PREDICTION_REVIEW_PATH ?? ".rumbling-hedge/state/prediction-review.latest.json");
  const predictionCopyDemoPath = resolve(args.predictionCopyDemoPath ?? env.BILL_PREDICTION_COPY_DEMO_PATH ?? ".rumbling-hedge/state/prediction-copy-demo.latest.json");
  const outputPath = args.outputPath ? resolve(args.outputPath) : undefined;
  const [review, copyDemo] = await Promise.all([
    readJsonSafe<any>(predictionReviewPath),
    readJsonSafe<any>(predictionCopyDemoPath)
  ]);
  const indicators = uniqIndicators([
    ...indicatorsFromPredictionReview(review),
    ...indicatorsFromCopyDemo(copyDemo)
  ]);
  const blockers = [
    ...(review ? [] : ["prediction-review-missing"]),
    ...(copyDemo ? [] : ["prediction-copy-demo-missing"]),
    ...(indicators.length > 0 ? [] : ["no-pm-futures-indicators"]),
    "indicator-only-no-execution-authority"
  ];
  const report: PmFuturesBridgeReport = {
    command: "pm-futures-bridge",
    generatedAt: args.now?.() ?? new Date().toISOString(),
    status: indicators.length > 0 ? "active-context" : "no-usable-context",
    authority: "indicator-only",
    executionAllowed: false,
    sourcePaths: {
      predictionReviewPath,
      predictionCopyDemoPath
    },
    indicators,
    blockers,
    nextAction: indicators.length > 0
      ? "Join these PM indicators into futures research/demo dashboards only; require futures OOS/live-readiness gates before routing."
      : "Keep collecting PM review and copy-demo artifacts until a macro/risk event maps cleanly to futures symbols."
  };

  if (outputPath) {
    await mkdir(dirname(outputPath), { recursive: true });
    await writeFile(outputPath, `${JSON.stringify(report, null, 2)}\n`, "utf8");
  }
  return report;
}
