import type { PredictionMarketSnapshot } from "./types.js";

const STOP_WORDS = new Set([
  "a", "an", "and", "are", "be", "for", "from", "game", "games", "if", "in", "is", "market", "match", "of", "on", "or", "the", "this", "to", "vs", "will", "wins", "win", "with"
]);

const OUTCOME_STOP_WORDS = new Set(["yes", "no", "over", "under"]);

function clean(value: string): string {
  return value.toLowerCase().replace(/[^a-z0-9.+]+/g, " ").trim();
}

function tokenize(value: string): string[] {
  return clean(value)
    .split(/\s+/)
    .filter(Boolean);
}

function uniqueSorted(tokens: string[]): string[] {
  return [...new Set(tokens)].sort();
}

function inferMarketType(text: string): string {
  const normalized = clean(text);
  if (!normalized) return "generic";
  if (normalized.includes(",")) return "combo";
  if (/\b(over|under|total)\b/.test(normalized)) return "total";
  if (/\b(spread|wins by|margin)\b/.test(normalized)) return "spread";
  if (/\b(winner|champion|outright|win the|to win)\b/.test(normalized)) return "winner";
  if (/\b(points|runs|kills|goals|rebounds|assists|strikeouts|yards)\b/.test(normalized) || /\b\d+\+\b/.test(normalized)) return "prop";
  return "binary";
}

function extractLineValue(text: string): number | undefined {
  const match = clean(text).match(/\b(\d+(?:\.\d+)?)\b/);
  if (!match) return undefined;
  const value = Number(match[1]);
  return Number.isFinite(value) ? value : undefined;
}

function entityTokens(text: string): string[] {
  return uniqueSorted(
    tokenize(text).filter((token) => token.length > 1 && !STOP_WORDS.has(token) && !/^\d+$/.test(token))
  );
}

function outcomeKey(outcomeLabel: string): string {
  const tokens = tokenize(outcomeLabel).filter((token) => token.length > 1 && !OUTCOME_STOP_WORDS.has(token));
  const normalized = clean(outcomeLabel);
  if (normalized === "yes" || normalized === "no") return normalized;
  return uniqueSorted(tokens).join(" ") || normalized;
}

export interface PredictionNormalizationProfile {
  marketType: string;
  resolutionStyle: string;
  eventKey: string;
  questionKey: string;
  outcomeKey: string;
  lineValue?: number;
}

function inferResolutionStyle(text: string): string {
  const normalized = clean(text);
  if (!normalized) return "generic";
  if ((/\bhit\b/.test(normalized) || /\bat any point\b/.test(normalized) || /\b1 minute candle\b/.test(normalized))
    && (/\bhigh\b/.test(normalized) || /\bequal to or above\b/.test(normalized))) {
    return "touch-high";
  }
  if ((/\bhit\b/.test(normalized) || /\bat any point\b/.test(normalized) || /\b1 minute candle\b/.test(normalized))
    && (/\blow\b/.test(normalized) || /\bequal to or below\b/.test(normalized))) {
    return "touch-low";
  }
  if ((/\babove\b/.test(normalized) || /\bgreater than\b/.test(normalized)) && /\bon\b/.test(normalized)) {
    return "snapshot-above";
  }
  if ((/\bbelow\b/.test(normalized) || /\bless than\b/.test(normalized)) && /\bon\b/.test(normalized)) {
    return "snapshot-below";
  }
  if (/\bwin the\b|\bwinner\b|\boutperform\b|\bipo first\b/.test(normalized)) {
    return "event-outcome";
  }
  return "generic";
}

export function buildPredictionProfile(market: PredictionMarketSnapshot): PredictionNormalizationProfile {
  const combined = `${market.eventTitle} ${market.marketQuestion} ${market.settlementText ?? ""}`;
  return {
    marketType: inferMarketType(combined),
    resolutionStyle: inferResolutionStyle(combined),
    eventKey: entityTokens(market.eventTitle).join(" "),
    questionKey: entityTokens(market.marketQuestion || combined).join(" "),
    outcomeKey: outcomeKey(market.outcomeLabel),
    lineValue: extractLineValue(`${market.marketQuestion} ${market.outcomeLabel}`)
  };
}

export function overlapRatio(leftKey: string, rightKey: string): number {
  const left = new Set(tokenize(leftKey).filter((token) => token.length > 1));
  const right = new Set(tokenize(rightKey).filter((token) => token.length > 1));
  if (!left.size || !right.size) return 0;
  let overlap = 0;
  for (const token of left) {
    if (right.has(token)) overlap += 1;
  }
  return overlap / Math.max(left.size, right.size);
}

export function lineCompatible(left?: number, right?: number): boolean {
  if (left === undefined || right === undefined) return true;
  const diff = Math.abs(left - right);
  if (diff <= 0.5) return true;
  if (diff <= 2) return true;
  return (diff / Math.max(Math.abs(left), Math.abs(right), 1)) <= 0.05;
}

export function outcomeCompatible(left: PredictionNormalizationProfile, right: PredictionNormalizationProfile): boolean {
  if (!left.outcomeKey || !right.outcomeKey) return false;
  if ((left.outcomeKey === "yes" || left.outcomeKey === "no") || (right.outcomeKey === "yes" || right.outcomeKey === "no")) {
    return left.outcomeKey === right.outcomeKey;
  }
  return left.outcomeKey === right.outcomeKey || left.outcomeKey.includes(right.outcomeKey) || right.outcomeKey.includes(left.outcomeKey);
}
