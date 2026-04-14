import type { PredictionCandidate, PredictionFeeConfig, PredictionMarketSnapshot, PredictionScanInput } from "./types.js";

function norm(value: string): string {
  return value.toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();
}

function tokenSet(value: string): Set<string> {
  return new Set(norm(value).split(/\s+/).filter((token) => token.length > 2));
}

function tokenOverlapRatio(a: string, b: string): number {
  const left = tokenSet(a);
  const right = tokenSet(b);
  if (!left.size || !right.size) return 0;
  let overlap = 0;
  for (const token of left) {
    if (right.has(token)) overlap += 1;
  }
  return overlap / Math.max(left.size, right.size);
}

function sameExpiry(a?: string, b?: string): boolean {
  if (!a || !b) return false;
  return a.slice(0, 10) === b.slice(0, 10);
}

function settlementCompatible(a?: string, b?: string): boolean {
  if (!a || !b) return false;
  const na = norm(a);
  const nb = norm(b);
  return na === nb || na.includes(nb) || nb.includes(na);
}

function candidateId(a: PredictionMarketSnapshot, b: PredictionMarketSnapshot): string {
  return `${a.venue}:${a.externalId}__${b.venue}:${b.externalId}`;
}

function sameQuestion(a: PredictionMarketSnapshot, b: PredictionMarketSnapshot): boolean {
  return norm(a.marketQuestion) === norm(b.marketQuestion);
}

function relatedPrompt(a: PredictionMarketSnapshot, b: PredictionMarketSnapshot): boolean {
  return (
    norm(a.eventTitle) === norm(b.eventTitle) ||
    sameQuestion(a, b) ||
    tokenOverlapRatio(a.marketQuestion, b.marketQuestion) >= 0.5 ||
    tokenOverlapRatio(a.eventTitle, b.eventTitle) >= 0.5 ||
    settlementCompatible(a.settlementText, b.settlementText)
  );
}

function scoreMatch(a: PredictionMarketSnapshot, b: PredictionMarketSnapshot): number {
  let score = 0;
  if (norm(a.eventTitle) === norm(b.eventTitle) || sameQuestion(a, b) || tokenOverlapRatio(a.marketQuestion, b.marketQuestion) >= 0.7) score += 0.45;
  if (norm(a.outcomeLabel) === norm(b.outcomeLabel)) score += 0.25;
  if (sameExpiry(a.expiry, b.expiry)) score += 0.15;
  if (settlementCompatible(a.settlementText, b.settlementText)) score += 0.15;
  return Number(score.toFixed(2));
}

export function scanPredictionCandidates(input: PredictionScanInput): PredictionCandidate[] {
  const { markets, fees, ts = new Date().toISOString() } = input;
  const results: PredictionCandidate[] = [];

  for (let i = 0; i < markets.length; i += 1) {
    for (let j = i + 1; j < markets.length; j += 1) {
      const a = markets[i];
      const b = markets[j];
      if (a.venue === b.venue) continue;
      if (!relatedPrompt(a, b)) continue;

      const matchScore = scoreMatch(a, b);
      const grossEdgePct = Number((Math.abs(a.price - b.price) * 100).toFixed(2));
      const feeDrag = fees.venueAFeePct + fees.venueBFeePct + fees.slippagePct;
      const netEdgePct = Number((grossEdgePct - feeDrag).toFixed(2));
      const settlementOk = settlementCompatible(a.settlementText, b.settlementText);
      const size = Math.min(a.displayedSize ?? 0, b.displayedSize ?? 0);
      const sizeVerdict = size >= fees.minDisplayedSize ? "ok" : "thin";

      const reasons: string[] = [];
      if (matchScore < 0.7) reasons.push("weak-match");
      if (!sameExpiry(a.expiry, b.expiry)) reasons.push("expiry-mismatch");
      if (!settlementOk) reasons.push("settlement-unclear");
      if (sizeVerdict !== "ok") reasons.push("thin-size");
      if (netEdgePct <= 0) reasons.push("negative-net-edge");

      const verdict =
        reasons.includes("weak-match") || reasons.includes("settlement-unclear") || reasons.includes("expiry-mismatch")
          ? "reject"
          : sizeVerdict !== "ok" || netEdgePct <= 0
            ? "watch"
            : matchScore >= 0.85
              ? "paper-trade"
              : netEdgePct >= fees.watchThresholdPct
                ? "paper-trade"
                : "watch";

      results.push({
        ts,
        candidateId: candidateId(a, b),
        venueA: a.venue,
        venueB: b.venue,
        eventTitleA: a.eventTitle,
        eventTitleB: b.eventTitle,
        outcomeA: a.outcomeLabel,
        outcomeB: b.outcomeLabel,
        expiryA: a.expiry,
        expiryB: b.expiry,
        settlementCompatible: settlementOk,
        matchScore,
        grossEdgePct,
        netEdgePct,
        displayedSizeA: a.displayedSize,
        displayedSizeB: b.displayedSize,
        sizeVerdict,
        verdict,
        reasons
      });
    }
  }

  return results.sort((left, right) => right.netEdgePct - left.netEdgePct || right.matchScore - left.matchScore);
}
