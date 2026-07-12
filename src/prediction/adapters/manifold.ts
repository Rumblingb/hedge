import { buildPredictionProfile, overlapRatio, temporalCompatible } from "../normalize.js";
import type { PredictionMarketSnapshot } from "../types.js";

interface ManifoldMarket {
  id?: string;
  question?: string;
  outcomeType?: string;
  probability?: number;
  closeTime?: number;
  volume?: number;
  isResolved?: boolean;
  mechanism?: string;
}

export interface ManifoldLiveSnapshotOptions {
  seedMarkets?: PredictionMarketSnapshot[];
  searchTermLimit?: number;
}

const SEARCH_BOOST_PATTERNS = [
  /\bipo\b/i,
  /\bopenai\b/i,
  /\banthropic\b/i,
  /\bbitcoin\b/i,
  /\bgold\b/i,
  /\bprice increase\b/i,
  /\btrade below\b/i,
  /\biran\b/i,
  /\bhormuz\b/i,
  /\bpeace\b/i,
  /\bceasefire\b/i,
  /\bdiplomatic\b/i,
  /\bmeeting\b/i,
  /\bblockade\b/i,
  /\bwar\b/i,
  /\bstrike\b/i,
  /\binflation\b/i,
  /\bfed\b/i,
  /\bcrypto\b/i,
  /\bai\b/i
] as const;

const SEARCH_PENALTY_PATTERNS = [
  /\bfifa\b/i,
  /\bworld cup\b/i,
  /\bchampions league\b/i,
  /\bmlb\b/i,
  /\bnba\b/i,
  /\bnhl\b/i,
  /\bnfl\b/i,
  /\bfc\b/i,
  /\bvs\b/i,
  /\bbo[1-9]\b/i,
  /\bscore\b/i,
  /\bmatch\b/i
] as const;

const MIRROR_PRIORITY_PATTERNS = [
  /\bpeace deal\b/i,
  /\bpermanent peace\b/i,
  /\bhormuz\b/i,
  /\bipo first\b/i,
  /\boutperform\b/i,
  /\bprice increase\b/i
] as const;

const SEED_FAMILY_STOP_WORDS = new Set([
  "a", "an", "after", "at", "be", "before", "by", "in", "no", "of", "on", "the", "there", "to", "will"
]);

function toIso(value?: number): string | undefined {
  if (typeof value !== "number" || !Number.isFinite(value)) return undefined;
  return new Date(value).toISOString();
}

function normalizeWhitespace(value: string): string {
  return value.replace(/\s+/g, " ").trim();
}

function cleanSearchTerm(value: string): string {
  return normalizeWhitespace(
    value
      .replace(/\[[^\]]+\]/g, " ")
      .replace(/[^\p{L}\p{N}$%/ .:-]+/gu, " ")
  );
}

function tokenize(value: string): string[] {
  return cleanSearchTerm(value)
    .toLowerCase()
    .split(" ")
    .map((token) => token.trim())
    .filter((token) => token.length >= 2);
}

function lexicalOverlap(left: string, right: string): number {
  const leftTokens = new Set(tokenize(left));
  const rightTokens = new Set(tokenize(right));
  if (leftTokens.size === 0 || rightTokens.size === 0) return 0;
  let shared = 0;
  for (const token of leftTokens) {
    if (rightTokens.has(token)) shared += 1;
  }
  return shared / Math.max(leftTokens.size, rightTokens.size);
}

function resolutionStyleCompatible(left: string, right: string): boolean {
  return left === right || left === "generic" || right === "generic";
}

function marketEligible(market: ManifoldMarket): boolean {
  return market.outcomeType === "BINARY"
    && market.isResolved === false
    && typeof market.probability === "number"
    && market.probability > 0
    && market.probability < 1;
}

function toSnapshot(market: ManifoldMarket): PredictionMarketSnapshot {
  return {
    venue: "manifold",
    externalId: market.id ?? "unknown-market",
    eventTitle: market.question ?? "unknown-event",
    marketQuestion: market.question ?? "unknown-question",
    outcomeLabel: "Yes",
    side: "yes" as const,
    expiry: toIso(market.closeTime),
    settlementText: market.question ?? "unknown-question",
    price: market.probability as number,
    displayedSize: market.volume ?? 0
  };
}

function rankSnapshot(snapshot: PredictionMarketSnapshot, searchTerms: string[]): number {
  const overlap = searchTerms.reduce(
    (best, term) => Math.max(best, lexicalOverlap(term, snapshot.marketQuestion)),
    0
  );
  const mirrorHint = /\[(polymarket|kalshi)\]/i.test(snapshot.marketQuestion) ? 0.2 : 0;
  const size = Math.min(snapshot.displayedSize ?? 0, 100_000);
  return overlap * 1_000_000 + mirrorHint * 100_000 + size;
}

function matchesSeedMarket(candidate: PredictionMarketSnapshot, seed: PredictionMarketSnapshot): boolean {
  const candidateProfile = buildPredictionProfile(candidate);
  const seedProfile = buildPredictionProfile(seed);
  const candidateQuestion = candidate.marketQuestion || candidate.eventTitle;
  const seedQuestion = seed.marketQuestion || seed.eventTitle;
  const questionOverlap = overlapRatio(candidateProfile.questionKey, seedProfile.questionKey);
  const eventOverlap = overlapRatio(candidateProfile.eventKey || candidateProfile.questionKey, seedProfile.eventKey || seedProfile.questionKey);
  const lexical = lexicalOverlap(candidateQuestion, seedQuestion);
  const mirrorTagged = /\[(polymarket|kalshi)\]/i.test(candidateQuestion);
  const temporalOk = temporalCompatible(candidateProfile, seedProfile, candidate.expiry, seed.expiry);
  const marketTypeOk = candidateProfile.marketType === seedProfile.marketType;
  const resolutionOk = resolutionStyleCompatible(candidateProfile.resolutionStyle, seedProfile.resolutionStyle);

  if (!temporalOk || !marketTypeOk || !resolutionOk) {
    return false;
  }

  if (questionOverlap >= 0.72 || eventOverlap >= 0.82) {
    return true;
  }

  if (mirrorTagged && questionOverlap >= 0.55) {
    return true;
  }

  return lexical >= 0.6 && questionOverlap >= 0.5;
}

function seedAligned(candidate: PredictionMarketSnapshot, seedMarkets: PredictionMarketSnapshot[]): boolean {
  if (seedMarkets.length === 0) return true;
  return seedMarkets.some((seed) => matchesSeedMarket(candidate, seed));
}

function hasSearchPenalty(question: string): boolean {
  return SEARCH_PENALTY_PATTERNS.some((pattern) => pattern.test(question));
}

function hasSearchBoost(question: string): boolean {
  return SEARCH_BOOST_PATTERNS.some((pattern) => pattern.test(question));
}

function detectSeedTopic(question: string): string {
  const normalized = question.toLowerCase();
  if (/\b(iran|hormuz|peace|ceasefire|diplomatic|blockade)\b/.test(normalized)) return "iran-hormuz";
  if (/\b(fed|interest rates?|bps)\b/.test(normalized)) return "fed-rates";
  if (/\b(bitcoin|crypto|gold)\b/.test(normalized)) return "bitcoin-crypto";
  if (/\b(wti|crude|oil)\b/.test(normalized)) return "oil";
  if (/\b(openai|anthropic|ipo|ai)\b/.test(normalized)) return "ai-ipo";
  return "general";
}

function seedFamilyKey(question: string): string {
  return cleanSearchTerm(question)
    .toLowerCase()
    .split(" ")
    .filter((token) => token.length > 2 && !SEED_FAMILY_STOP_WORDS.has(token) && !/^\d+$/.test(token))
    .slice(0, 8)
    .join(" ");
}

function scoreSeedMarket(market: PredictionMarketSnapshot): number {
  const question = market.marketQuestion || market.eventTitle;
  let score = market.displayedSize ?? 0;
  if (market.venue === "kalshi") score += 250_000;
  if (hasSearchBoost(question)) score += 1_000_000;
  if (MIRROR_PRIORITY_PATTERNS.some((pattern) => pattern.test(question))) score += 1_500_000;
  if (/\b(by|before|after|during)\b/i.test(question)) score += 50_000;
  if (hasSearchPenalty(question)) score -= 2_000_000;
  return score;
}

export function buildManifoldSearchTerms(seedMarkets: PredictionMarketSnapshot[], limit = 12): string[] {
  const seen = new Set<string>();
  const topicCaps: Record<string, number> = {
    "iran-hormuz": 3,
    "fed-rates": 2,
    "bitcoin-crypto": 2,
    "oil": 2,
    "ai-ipo": 2,
    general: 1
  };
  const topicCounts: Record<string, number> = {};
  const familySeen = new Set<string>();
  const terms: string[] = [];

  for (const market of [...seedMarkets]
    .filter((market) => market.venue !== "manifold")
    .filter((market) => market.venue === "kalshi" || hasSearchBoost(market.marketQuestion || market.eventTitle))
    .filter((market) => !hasSearchPenalty(market.marketQuestion || market.eventTitle))
    .sort((left, right) => scoreSeedMarket(right) - scoreSeedMarket(left))) {
    if (terms.length >= limit) break;
    const question = market.marketQuestion || market.eventTitle;
    const topic = detectSeedTopic(question);
    const family = seedFamilyKey(question);
    if (family && familySeen.has(`${topic}:${family}`)) continue;
    const cap = topicCaps[topic] ?? topicCaps.general;
    if ((topicCounts[topic] ?? 0) >= cap) continue;
    const term = cleanSearchTerm(question);
    if (term.length < 12) continue;
    const key = term.toLowerCase();
    if (seen.has(key)) continue;
    seen.add(key);
    topicCounts[topic] = (topicCounts[topic] ?? 0) + 1;
    if (family) familySeen.add(`${topic}:${family}`);
    terms.push(term);
  }

  return terms;
}

async function fetchJson<T>(url: URL): Promise<T> {
  const response = await fetch(url, {
    headers: {
      accept: "application/json",
      "user-agent": "rumbling-hedge/0.1"
    },
    signal: AbortSignal.timeout(10_000)
  });

  if (!response.ok) {
    throw new Error(`Manifold market fetch failed: ${response.status} ${response.statusText}`);
  }

  return response.json() as Promise<T>;
}

async function fetchManifoldTopMarkets(limit: number): Promise<ManifoldMarket[]> {
  const url = new URL("https://api.manifold.markets/v0/markets");
  url.searchParams.set("limit", String(Math.max(limit * 4, 100)));
  return fetchJson<ManifoldMarket[]>(url);
}

async function fetchManifoldSearchMarkets(term: string): Promise<ManifoldMarket[]> {
  const url = new URL("https://api.manifold.markets/v0/search-markets");
  url.searchParams.set("term", term);
  return fetchJson<ManifoldMarket[]>(url);
}

export async function fetchManifoldLiveSnapshot(
  limit = 25,
  options: ManifoldLiveSnapshotOptions = {}
): Promise<PredictionMarketSnapshot[]> {
  const seedTerms = buildManifoldSearchTerms(options.seedMarkets ?? [], options.searchTermLimit ?? 12);
  const seedMarkets = (options.seedMarkets ?? []).filter((market) => market.venue !== "manifold");
  const baseMarkets = await fetchManifoldTopMarkets(limit);
  const searchSettled = seedTerms.length === 0
    ? []
    : await Promise.allSettled(seedTerms.map((term) => fetchManifoldSearchMarkets(term)));

  const merged = new Map<string, PredictionMarketSnapshot>();
  const rankingTerms = seedTerms.length > 0 ? seedTerms : [];
  const consider = (market: ManifoldMarket): void => {
    if (!marketEligible(market)) return;
    const snapshot = toSnapshot(market);
    if (seedMarkets.length > 0 && !seedAligned(snapshot, seedMarkets)) return;
    if (!merged.has(snapshot.externalId)) {
      merged.set(snapshot.externalId, snapshot);
    }
  };

  baseMarkets.forEach(consider);
  for (const result of searchSettled) {
    if (result.status !== "fulfilled") continue;
    result.value.forEach(consider);
  }

  const rows = [...merged.values()];
  if (rankingTerms.length === 0) {
    return rows
      .sort((left, right) => (right.displayedSize ?? 0) - (left.displayedSize ?? 0))
      .slice(0, limit);
  }

  return rows
    .sort((left, right) => rankSnapshot(right, rankingTerms) - rankSnapshot(left, rankingTerms))
    .slice(0, limit);
}
