import { buildPredictionProfile, lineCompatible, outcomeCompatible, overlapRatio } from "./normalize.js";
import { classifyPredictionCandidate, DEFAULT_PREDICTION_SCAN_POLICY } from "./scanPolicy.js";
import { recommendPredictionStake } from "./sizing.js";
import type { PredictionCandidate, PredictionMarketSnapshot, PredictionScanInput } from "./types.js";

function norm(value: string): string {
  return value.toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();
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

function scoreMatch(args: {
  a: PredictionMarketSnapshot;
  b: PredictionMarketSnapshot;
  entityOverlap: number;
  questionOverlap: number;
  sameLine: boolean;
  outcomeOk: boolean;
  marketTypeOk: boolean;
}): number {
  const { a, b, entityOverlap, questionOverlap, sameLine, outcomeOk, marketTypeOk } = args;
  let score = 0;
  score += Math.min(0.35, questionOverlap * 0.35);
  score += Math.min(0.2, entityOverlap * 0.2);
  if (marketTypeOk) score += 0.15;
  if (outcomeOk) score += 0.15;
  if (sameLine) score += 0.05;
  if (sameExpiry(a.expiry, b.expiry)) score += 0.05;
  if (settlementCompatible(a.settlementText, b.settlementText)) score += 0.05;
  return Number(score.toFixed(2));
}

export function scanPredictionCandidates(input: PredictionScanInput): PredictionCandidate[] {
  const { markets, fees, sizing, ts = new Date().toISOString(), policy = DEFAULT_PREDICTION_SCAN_POLICY } = input;
  const results: PredictionCandidate[] = [];

  for (let i = 0; i < markets.length; i += 1) {
    for (let j = i + 1; j < markets.length; j += 1) {
      const a = markets[i];
      const b = markets[j];
      if (a.venue === b.venue) continue;
      const profileA = buildPredictionProfile(a);
      const profileB = buildPredictionProfile(b);
      if (profileA.marketType === "combo" || profileB.marketType === "combo") continue;

      const entityOverlap = overlapRatio(profileA.eventKey || profileA.questionKey, profileB.eventKey || profileB.questionKey);
      const questionOverlap = overlapRatio(profileA.questionKey, profileB.questionKey);
      const marketTypeOk = profileA.marketType === profileB.marketType;
      const sameLine = lineCompatible(profileA.lineValue, profileB.lineValue);
      const outcomeOk = outcomeCompatible(profileA, profileB);
      const related = sameQuestion(a, b)
        || questionOverlap >= 0.65
        || entityOverlap >= 0.75
        || (sameLine && (questionOverlap >= 0.5 || entityOverlap >= 0.5));
      if (!marketTypeOk || !sameLine || !outcomeOk || !related) continue;

      const matchScore = scoreMatch({ a, b, entityOverlap, questionOverlap, sameLine, outcomeOk, marketTypeOk });
      const grossEdgePct = Number((Math.abs(a.price - b.price) * 100).toFixed(2));
      const feeDrag = fees.venueAFeePct + fees.venueBFeePct + fees.slippagePct;
      const netEdgePct = Number((grossEdgePct - feeDrag).toFixed(2));
      const settlementOk = settlementCompatible(a.settlementText, b.settlementText);
      const sizingRecommendation = recommendPredictionStake({
        candidate: { matchScore, netEdgePct, displayedSizeA: a.displayedSize, displayedSizeB: b.displayedSize },
        left: a,
        right: b,
        sizing
      });
      const { reasons, verdict, sizeVerdict } = classifyPredictionCandidate({
        candidate: {
          matchScore,
          netEdgePct,
          displayedSizeA: a.displayedSize,
          displayedSizeB: b.displayedSize,
          expiryA: a.expiry,
          expiryB: b.expiry,
          settlementCompatible: settlementOk,
          sizing: sizingRecommendation
        },
        policy: {
          ...policy,
          minDisplayedSize: Math.max(policy.minDisplayedSize, fees.minDisplayedSize),
          paperEdgeThresholdPct: Math.max(policy.paperEdgeThresholdPct, fees.watchThresholdPct)
        }
      });

      results.push({
        ts,
        candidateId: candidateId(a, b),
        venueA: a.venue,
        venueB: b.venue,
        marketType: profileA.marketType,
        normalizedEventKey: profileA.eventKey || profileA.questionKey,
        normalizedQuestionKey: profileA.questionKey,
        normalizedOutcomeKey: profileA.outcomeKey,
        eventTitleA: a.eventTitle,
        eventTitleB: b.eventTitle,
        outcomeA: a.outcomeLabel,
        outcomeB: b.outcomeLabel,
        expiryA: a.expiry,
        expiryB: b.expiry,
        settlementCompatible: settlementOk,
        matchScore,
        entityOverlap: Number(entityOverlap.toFixed(2)),
        questionOverlap: Number(questionOverlap.toFixed(2)),
        grossEdgePct,
        netEdgePct,
        displayedSizeA: a.displayedSize,
        displayedSizeB: b.displayedSize,
        sizeVerdict,
        verdict,
        reasons,
        sizing: sizingRecommendation
      });
    }
  }

  return results.sort((left, right) => right.netEdgePct - left.netEdgePct || right.matchScore - left.matchScore);
}
