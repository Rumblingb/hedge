import { buildPredictionProfile, lineCompatible, outcomeCompatible, overlapRatio, temporalCompatible } from "./normalize.js";
import { classifyPredictionCandidate, DEFAULT_PREDICTION_SCAN_POLICY } from "./scanPolicy.js";
import { recommendPredictionStake } from "./sizing.js";
import type { PredictionCandidate, PredictionMarketSnapshot, PredictionNearMiss, PredictionScanDiagnostics, PredictionScanInput } from "./types.js";

function norm(value: string): string {
  return value.toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();
}

function sameExpiry(a?: string, b?: string): boolean {
  if (!a || !b) return false;
  return a.slice(0, 10) === b.slice(0, 10) || a.slice(0, 7) === b.slice(0, 7);
}

function settlementCompatible(a?: string, b?: string): boolean {
  if (!a || !b) return false;
  const na = norm(a);
  const nb = norm(b);
  return na === nb || na.includes(nb) || nb.includes(na) || overlapRatio(na, nb) >= 0.5;
}

function fallbackSettlementCompatible(args: {
  entityOverlap: number;
  questionOverlap: number;
  temporalOk: boolean;
  resolutionStyleOk: boolean;
}): boolean {
  const { entityOverlap, questionOverlap, temporalOk, resolutionStyleOk } = args;
  return temporalOk && resolutionStyleOk && questionOverlap >= 0.65 && entityOverlap >= 0.45;
}

function candidateId(a: PredictionMarketSnapshot, b: PredictionMarketSnapshot): string {
  return `${a.venue}:${a.externalId}__${b.venue}:${b.externalId}`;
}

function isExpired(expiry: string | undefined, ts: string): boolean {
  if (!expiry) return false;
  const expiryMs = Date.parse(expiry);
  const nowMs = Date.parse(ts);
  if (!Number.isFinite(expiryMs) || !Number.isFinite(nowMs)) return false;
  return expiryMs <= nowMs;
}

function sameQuestion(a: PredictionMarketSnapshot, b: PredictionMarketSnapshot): boolean {
  return norm(a.marketQuestion) === norm(b.marketQuestion);
}

function strictWinnerComparable(args: {
  marketType: string;
  exactQuestion: boolean;
  questionOverlap: number;
}): boolean {
  if (args.marketType !== "winner") return true;
  return args.exactQuestion || args.questionOverlap >= 0.8;
}

function sameSemanticHorizon(args: {
  profileA: ReturnType<typeof buildPredictionProfile>;
  profileB: ReturnType<typeof buildPredictionProfile>;
  expiryA?: string;
  expiryB?: string;
}): boolean {
  const { profileA, profileB, expiryA, expiryB } = args;
  if (profileA.temporalKey || profileB.temporalKey) {
    return temporalCompatible(profileA, profileB, expiryA, expiryB);
  }
  return sameExpiry(expiryA, expiryB);
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

function verdictRank(verdict: PredictionCandidate["verdict"]): number {
  if (verdict === "paper-trade") return 2;
  if (verdict === "watch") return 1;
  return 0;
}

function hasReason(candidate: PredictionCandidate, reason: string): boolean {
  return candidate.reasons.includes(reason);
}

function compareCandidates(left: PredictionCandidate, right: PredictionCandidate): number {
  return (
    verdictRank(right.verdict) - verdictRank(left.verdict)
    || Number(Boolean(right.sameHorizon)) - Number(Boolean(left.sameHorizon))
    || Number(right.settlementCompatible) - Number(left.settlementCompatible)
    || Number(!hasReason(right, "weak-match")) - Number(!hasReason(left, "weak-match"))
    || right.matchScore - left.matchScore
    || right.netEdgePct - left.netEdgePct
    || right.grossEdgePct - left.grossEdgePct
  );
}

function pushReason(reasons: string[], condition: boolean, reason: string): void {
  if (!condition) reasons.push(reason);
}

function analyzePredictionPair(a: PredictionMarketSnapshot, b: PredictionMarketSnapshot, ts: string): {
  profileA: ReturnType<typeof buildPredictionProfile>;
  profileB: ReturnType<typeof buildPredictionProfile>;
  entityOverlap: number;
  questionOverlap: number;
  marketTypeOk: boolean;
  resolutionStyleOk: boolean;
  temporalOk: boolean;
  sameHorizon: boolean;
  sameLine: boolean;
  outcomeOk: boolean;
  related: boolean;
  winnerComparable: boolean;
  matchScore: number;
  settlementOk: boolean;
  gateReasons: string[];
} {
  const profileA = buildPredictionProfile(a);
  const profileB = buildPredictionProfile(b);
  const gateReasons: string[] = [];
  if (profileA.marketType === "combo" || profileB.marketType === "combo") {
    gateReasons.push("combo-market");
  }
  if (isExpired(a.expiry, ts) || isExpired(b.expiry, ts)) {
    gateReasons.push("expired-market");
  }

  const entityOverlap = overlapRatio(profileA.eventKey || profileA.questionKey, profileB.eventKey || profileB.questionKey);
  const questionOverlap = overlapRatio(profileA.questionKey, profileB.questionKey);
  const marketTypeOk = profileA.marketType === profileB.marketType;
  const resolutionStyleOk = profileA.resolutionStyle === profileB.resolutionStyle
    || profileA.resolutionStyle === "generic"
    || profileB.resolutionStyle === "generic";
  const temporalOk = temporalCompatible(profileA, profileB, a.expiry, b.expiry);
  const sameHorizon = sameSemanticHorizon({
    profileA,
    profileB,
    expiryA: a.expiry,
    expiryB: b.expiry
  });
  const sameLine = lineCompatible(profileA.lineValue, profileB.lineValue);
  const outcomeOk = outcomeCompatible(profileA, profileB);
  const exactQuestion = sameQuestion(a, b);
  const related = exactQuestion
    || questionOverlap >= 0.65
    || entityOverlap >= 0.75
    || (sameLine && (questionOverlap >= 0.5 || entityOverlap >= 0.5));
  const winnerComparable = strictWinnerComparable({
    marketType: profileA.marketType,
    exactQuestion,
    questionOverlap
  });
  const settlementOk = settlementCompatible(a.settlementText, b.settlementText)
    || fallbackSettlementCompatible({
      entityOverlap,
      questionOverlap,
      temporalOk,
      resolutionStyleOk
    });
  const matchScore = scoreMatch({ a, b, entityOverlap, questionOverlap, sameLine, outcomeOk, marketTypeOk });

  pushReason(gateReasons, marketTypeOk, "market-type-mismatch");
  pushReason(gateReasons, resolutionStyleOk, "resolution-style-mismatch");
  pushReason(gateReasons, temporalOk, "temporal-mismatch");
  pushReason(gateReasons, sameLine, "line-mismatch");
  pushReason(gateReasons, outcomeOk, "outcome-mismatch");
  pushReason(gateReasons, related, "weak-relatedness");
  pushReason(gateReasons, winnerComparable, "winner-question-mismatch");

  return {
    profileA,
    profileB,
    entityOverlap,
    questionOverlap,
    marketTypeOk,
    resolutionStyleOk,
    temporalOk,
    sameHorizon,
    sameLine,
    outcomeOk,
    related,
    winnerComparable,
    matchScore,
    settlementOk,
    gateReasons
  };
}

export function scanPredictionCandidates(input: PredictionScanInput): PredictionCandidate[] {
  const { markets, fees, sizing, ts = new Date().toISOString(), policy = DEFAULT_PREDICTION_SCAN_POLICY } = input;
  const results: PredictionCandidate[] = [];

  for (let i = 0; i < markets.length; i += 1) {
    for (let j = i + 1; j < markets.length; j += 1) {
      const a = markets[i];
      const b = markets[j];
      if (a.venue === b.venue) continue;
      const analysis = analyzePredictionPair(a, b, ts);
      const { profileA, entityOverlap, questionOverlap, sameHorizon, matchScore, settlementOk } = analysis;
      if (analysis.gateReasons.length > 0) continue;

      const grossEdgePct = Number((Math.abs(a.price - b.price) * 100).toFixed(2));
      const feeDragPct = Number((fees.venueAFeePct + fees.venueBFeePct + fees.slippagePct).toFixed(2));
      const netEdgePct = Number((grossEdgePct - feeDragPct).toFixed(2));
      const sizingRecommendation = recommendPredictionStake({
        candidate: { matchScore, netEdgePct, displayedSizeA: a.displayedSize, displayedSizeB: b.displayedSize },
        left: a,
        right: b,
        sizing
      });
      const { reasons, verdict, sizeVerdict } = classifyPredictionCandidate({
        candidate: {
          matchScore,
          grossEdgePct,
          netEdgePct,
          feeDragPct,
          displayedSizeA: a.displayedSize,
          displayedSizeB: b.displayedSize,
          expiryA: a.expiry,
          expiryB: b.expiry,
          sameHorizon,
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
        sameHorizon,
        settlementCompatible: settlementOk,
        matchScore,
        entityOverlap: Number(entityOverlap.toFixed(2)),
        questionOverlap: Number(questionOverlap.toFixed(2)),
        grossEdgePct,
        netEdgePct,
        feeDragPct,
        displayedSizeA: a.displayedSize,
        displayedSizeB: b.displayedSize,
        sizeVerdict,
        verdict,
        reasons,
        sizing: sizingRecommendation
      });
    }
  }

  return results.sort(compareCandidates);
}

function compareNearMisses(left: PredictionNearMiss, right: PredictionNearMiss): number {
  return (
    right.matchScore - left.matchScore
    || right.entityOverlap - left.entityOverlap
    || right.questionOverlap - left.questionOverlap
    || right.netEdgePct - left.netEdgePct
  );
}

export function diagnosePredictionScan(input: PredictionScanInput, nearMissLimit = 20): PredictionScanDiagnostics {
  const { markets, fees, ts = new Date().toISOString() } = input;
  const rejectReasons: Record<string, number> = {};
  const venuePairs: Record<string, number> = {};
  const topNearMisses: PredictionNearMiss[] = [];
  let crossVenuePairs = 0;
  let skippedSameVenuePairs = 0;
  let skippedComboPairs = 0;
  let viablePairs = 0;

  for (let i = 0; i < markets.length; i += 1) {
    for (let j = i + 1; j < markets.length; j += 1) {
      const a = markets[i];
      const b = markets[j];
      if (a.venue === b.venue) {
        skippedSameVenuePairs += 1;
        continue;
      }

      crossVenuePairs += 1;
      const venuePairKey = `${a.venue}->${b.venue}`;
      venuePairs[venuePairKey] = (venuePairs[venuePairKey] ?? 0) + 1;
      const analysis = analyzePredictionPair(a, b, ts);
      if (analysis.gateReasons.includes("combo-market")) skippedComboPairs += 1;
      if (analysis.gateReasons.length === 0) {
        viablePairs += 1;
        continue;
      }

      for (const reason of analysis.gateReasons) {
        rejectReasons[reason] = (rejectReasons[reason] ?? 0) + 1;
      }

      const grossEdgePct = Number((Math.abs(a.price - b.price) * 100).toFixed(2));
      const feeDragPct = Number((fees.venueAFeePct + fees.venueBFeePct + fees.slippagePct).toFixed(2));
      const nearMiss: PredictionNearMiss = {
        candidateId: candidateId(a, b),
        venueA: a.venue,
        venueB: b.venue,
        eventTitleA: a.eventTitle,
        eventTitleB: b.eventTitle,
        outcomeA: a.outcomeLabel,
        outcomeB: b.outcomeLabel,
        expiryA: a.expiry,
        expiryB: b.expiry,
        marketTypeA: analysis.profileA.marketType,
        marketTypeB: analysis.profileB.marketType,
        resolutionStyleA: analysis.profileA.resolutionStyle,
        resolutionStyleB: analysis.profileB.resolutionStyle,
        matchScore: analysis.matchScore,
        entityOverlap: Number(analysis.entityOverlap.toFixed(2)),
        questionOverlap: Number(analysis.questionOverlap.toFixed(2)),
        grossEdgePct,
        netEdgePct: Number((grossEdgePct - feeDragPct).toFixed(2)),
        reasons: analysis.gateReasons
      };

      topNearMisses.push(nearMiss);
      topNearMisses.sort(compareNearMisses);
      if (topNearMisses.length > nearMissLimit) topNearMisses.length = nearMissLimit;
    }
  }

  return {
    ts,
    totalMarkets: markets.length,
    totalPairs: (markets.length * (markets.length - 1)) / 2,
    crossVenuePairs,
    skippedSameVenuePairs,
    skippedComboPairs,
    viablePairs,
    rejectReasons,
    venuePairs,
    topNearMisses
  };
}
