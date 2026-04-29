import type { PredictionMarketSnapshot } from "./types.js";

const STOP_WORDS = new Set([
  "a", "an", "and", "are", "be", "by", "end", "for", "from", "game", "games",
  "if", "in", "is", "it", "market", "match", "more", "not", "of", "on", "or",
  "than", "the", "this", "to", "vs", "will", "wins", "win", "with",
  "what", "price", "hit", "returns", "return", "normal", "announces", "announce",
  "lifted", "set", "before", "after", "does", "increase", "decrease", "rise",
  "any", "there", "no", "yes", "has", "have", "been", "its", "at", "how", "about"
]);

const ENTITY_SYNONYMS: Record<string, string> = {
  hezbollah: "lebanon hezbollah",
  hizbollah: "lebanon hezbollah",
  iranian: "iran iranian",
  bitcoin: "btc bitcoin",
  btc: "btc bitcoin",
  deal: "deal agreement",
  agreement: "deal agreement",
  framework: "deal agreement framework",
  champion: "champion finals",
  finals: "champion finals",
};

const OUTCOME_STOP_WORDS = new Set(["yes", "no", "over", "under"]);
const MONTH_TOKENS = [
  "january", "february", "march", "april", "may", "june",
  "july", "august", "september", "october", "november", "december",
  "jan", "feb", "mar", "apr", "jun", "jul", "aug", "sep", "sept", "oct", "nov", "dec"
] as const;
const MONTH_ALIASES: Record<string, number> = {
  january: 1, jan: 1,
  february: 2, feb: 2,
  march: 3, mar: 3,
  april: 4, apr: 4,
  may: 5,
  june: 6, jun: 6,
  july: 7, jul: 7,
  august: 8, aug: 8,
  september: 9, sep: 9, sept: 9,
  october: 10, oct: 10,
  november: 11, nov: 11,
  december: 12, dec: 12
};
const MONTH_PATTERN = MONTH_TOKENS.join("|");

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

function expandSynonyms(tokens: string[]): string[] {
  const expanded: string[] = [];
  for (const token of tokens) {
    const synonym = ENTITY_SYNONYMS[token];
    if (synonym) {
      for (const s of synonym.split(" ")) {
        expanded.push(s);
      }
    } else {
      expanded.push(token);
    }
  }
  return expanded;
}

function entityTokens(text: string): string[] {
  const raw = tokenize(text).filter((token) => token.length > 1 && !STOP_WORDS.has(token) && !/^\d+$/.test(token));
  return uniqueSorted(expandSynonyms(raw));
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
  temporalKey?: string;
  lineValue?: number;
}

interface TemporalMarker {
  year?: number;
  month?: number;
  day?: number;
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

function extractTemporalMarker(text: string): TemporalMarker {
  const normalized = clean(text);
  if (!normalized) return {};

  const yearMatch = normalized.match(/\b(20\d{2})\b/);
  const monthDayForward = normalized.match(new RegExp(`\\b(${MONTH_PATTERN})\\s+(\\d{1,2})(?:\\b|st\\b|nd\\b|rd\\b|th\\b)`));
  const monthDayReverse = normalized.match(new RegExp(`\\b(\\d{1,2})(?:st\\b|nd\\b|rd\\b|th\\b)?\\s+(${MONTH_PATTERN})\\b`));
  const standaloneMonthMatch = normalized.match(new RegExp(`\\b(${MONTH_PATTERN})\\b`));

  const monthToken = monthDayForward?.[1] ?? monthDayReverse?.[2] ?? standaloneMonthMatch?.[1];
  const dayToken = monthDayForward?.[2] ?? monthDayReverse?.[1];
  const year = yearMatch ? Number(yearMatch[1]) : undefined;
  const month = monthToken ? MONTH_ALIASES[monthToken] : undefined;
  const day = dayToken ? Number(dayToken) : undefined;

  return {
    year: Number.isFinite(year) ? year : undefined,
    month: Number.isFinite(month) ? month : undefined,
    day: Number.isFinite(day) ? day : undefined
  };
}

function temporalKey(marker: TemporalMarker): string | undefined {
  if (!marker.year && !marker.month && !marker.day) return undefined;
  const year = marker.year ? String(marker.year) : "xxxx";
  const month = marker.month ? String(marker.month).padStart(2, "0") : "xx";
  const day = marker.day ? String(marker.day).padStart(2, "0") : "xx";
  return `${year}-${month}-${day}`;
}

export function buildPredictionProfile(market: PredictionMarketSnapshot): PredictionNormalizationProfile {
  const combined = `${market.eventTitle} ${market.marketQuestion} ${market.settlementText ?? ""}`;
  const marker = extractTemporalMarker(`${market.marketQuestion} ${market.eventTitle}`);
  return {
    marketType: inferMarketType(combined),
    resolutionStyle: inferResolutionStyle(combined),
    eventKey: entityTokens(market.eventTitle).join(" "),
    questionKey: entityTokens(market.marketQuestion || combined).join(" "),
    outcomeKey: outcomeKey(market.outcomeLabel),
    temporalKey: temporalKey(marker),
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
  return overlap / Math.sqrt(left.size * right.size);
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

function parseTemporalKey(key?: string): TemporalMarker {
  if (!key) return {};
  const [yearRaw, monthRaw, dayRaw] = key.split("-");
  return {
    year: yearRaw && yearRaw !== "xxxx" ? Number(yearRaw) : undefined,
    month: monthRaw && monthRaw !== "xx" ? Number(monthRaw) : undefined,
    day: dayRaw && dayRaw !== "xx" ? Number(dayRaw) : undefined
  };
}

export function temporalCompatible(
  left: PredictionNormalizationProfile,
  right: PredictionNormalizationProfile,
  leftExpiry?: string,
  rightExpiry?: string
): boolean {
  const leftMarker = parseTemporalKey(left.temporalKey);
  const rightMarker = parseTemporalKey(right.temporalKey);
  const hasExplicitTime = Boolean(left.temporalKey || right.temporalKey);

  if (leftMarker.year && rightMarker.year && leftMarker.year !== rightMarker.year) return false;
  if (leftMarker.month && rightMarker.month && leftMarker.month !== rightMarker.month) return false;
  if (leftMarker.day && rightMarker.day && leftMarker.day !== rightMarker.day) return false;

  if (hasExplicitTime) return true;
  if (!leftExpiry || !rightExpiry) return true;
  return leftExpiry.slice(0, 10) === rightExpiry.slice(0, 10) || leftExpiry.slice(0, 7) === rightExpiry.slice(0, 7);
}
