import { buildPredictionCommitteeReview } from "./committee.js";
import type {
  PredictionCandidate,
  PredictionCandidateHistorySummary,
  PredictionCycleReview,
  PredictionHistoryTrend,
  PredictionReviewCheck,
  PredictionSourcePolicy,
  PredictionVerdict
} from "./types.js";

function trendFromShortfall(values: number[]): PredictionHistoryTrend {
  if (values.length < 2) return "flat";
  const first = values[0];
  const latest = values[values.length - 1];
  if (latest <= first - 0.25) return "improving";
  if (latest >= first + 0.25) return "worsening";
  return "flat";
}

function average(values: number[]): number {
  if (values.length === 0) return 0;
  return values.reduce((sum, value) => sum + value, 0) / values.length;
}

function buildTopCandidateHistory(
  candidateId: string,
  current: PredictionCandidate,
  recentCycles: Array<Record<string, unknown>>
): PredictionCandidateHistorySummary | null {
  const observations = recentCycles
    .map((row) => (row.review as { topCandidate?: Record<string, unknown> } | undefined)?.topCandidate)
    .filter((top): top is Record<string, unknown> => Boolean(top) && typeof top === "object")
    .filter((top) => top.candidateId === candidateId)
    .map((top) => ({
      grossEdgePct: Number(top.grossEdgePct ?? 0),
      netEdgePct: Number(top.netEdgePct ?? 0),
      edgeShortfallPct: Number(top.edgeShortfallPct ?? 0),
      verdict: String(top.verdict ?? "reject")
    }));

  observations.push({
    grossEdgePct: current.grossEdgePct,
    netEdgePct: current.netEdgePct,
    edgeShortfallPct: Number(Math.max(0, current.feeDragPct - current.grossEdgePct).toFixed(2)),
    verdict: current.verdict
  });

  if (observations.length <= 1) return null;

  const grossEdges = observations.map((item) => item.grossEdgePct);
  const netEdges = observations.map((item) => item.netEdgePct);
  const shortfalls = observations.map((item) => item.edgeShortfallPct);

  return {
    observations: observations.length,
    watchCycles: observations.filter((item) => item.verdict === "watch").length,
    paperCycles: observations.filter((item) => item.verdict === "paper-trade").length,
    bestGrossEdgePct: Number(Math.max(...grossEdges).toFixed(2)),
    bestNetEdgePct: Number(Math.max(...netEdges).toFixed(2)),
    averageGrossEdgePct: Number(average(grossEdges).toFixed(2)),
    averageNetEdgePct: Number(average(netEdges).toFixed(2)),
    averageShortfallPct: Number(average(shortfalls).toFixed(2)),
    latestGrossEdgePct: Number(grossEdges[grossEdges.length - 1].toFixed(2)),
    latestNetEdgePct: Number(netEdges[netEdges.length - 1].toFixed(2)),
    latestShortfallPct: Number(shortfalls[shortfalls.length - 1].toFixed(2)),
    trend: trendFromShortfall(shortfalls)
  };
}

function pickLeadCandidate(rows: PredictionCandidate[]): PredictionCandidate | null {
  return rows.find((row) => row.verdict === "paper-trade" && (row.sizing?.recommendedStake ?? 0) > 0)
    ?? rows[0]
    ?? null;
}

function topCandidate(rows: PredictionCandidate[], recentCycles: Array<Record<string, unknown>> = []): PredictionCycleReview["topCandidate"] {
  const first = pickLeadCandidate(rows);
  if (!first) return null;
  return {
    candidateId: first.candidateId,
    verdict: first.verdict,
    reasons: [...first.reasons],
    grossEdgePct: first.grossEdgePct,
    netEdgePct: first.netEdgePct,
    feeDragPct: first.feeDragPct,
    edgeShortfallPct: Number(Math.max(0, first.feeDragPct - first.grossEdgePct).toFixed(2)),
    matchScore: first.matchScore,
    recommendedStake: first.sizing?.recommendedStake ?? 0,
    venuePair: `${first.venueA}->${first.venueB}`,
    history: buildTopCandidateHistory(first.candidateId, first, recentCycles),
    committee: buildPredictionCommitteeReview(first)
  };
}

function buildCheck(args: {
  name: string;
  passed: boolean;
  observed: number | string;
  threshold: number | string;
  reason: string;
}): PredictionReviewCheck {
  return args;
}

function recommendationFromChecks(blockers: string[], counts: Record<PredictionVerdict, number>): string {
  if (blockers.length === 0 && (counts["paper-trade"] ?? 0) > 0) {
    return "Maintain research mode but queue the highest-ranked candidate for paper-trade review.";
  }
  if (blockers.some((item) => item.includes("required-source") || item.includes("venue-health"))) {
    return "Fix source coverage first. Bill should not widen execution while venue coverage is unstable.";
  }
  if ((counts.watch ?? 0) === 0 && (counts["paper-trade"] ?? 0) === 0) {
    return "Keep the lane in research mode. Improve cross-venue normalization or narrow the source universe.";
  }
  return "Stay in research mode and continue collecting evidence.";
}

function recommendationFromTopCandidate(review: PredictionCycleReview): string | null {
  const committee = review.topCandidate?.committee;
  if (!committee || !review.topCandidate) return null;
  if (committee.finalStance === "approve") {
    return "Committee is aligned for paper deployment. Keep safeguards on, but this candidate is structurally ready for the next gate.";
  }
  const contractVote = committee.votes.find((vote) => vote.analyst === "contract-analyst");
  const edgeVote = committee.votes.find((vote) => vote.analyst === "edge-analyst");
  if (committee.finalStance === "watch" && contractVote?.stance === "approve" && edgeVote?.stance !== "approve") {
    const shortfall = Number(review.topCandidate.edgeShortfallPct.toFixed(2));
    const gross = Number(review.topCandidate.grossEdgePct.toFixed(2));
    const drag = Number(review.topCandidate.feeDragPct.toFixed(2));
    const history = review.topCandidate.history;
    const historySentence = history
      ? history.trend === "improving"
        ? ` It has resurfaced ${history.observations} times recently; best gross edge reached ${history.bestGrossEdgePct}%, and the shortfall trend is improving but still not enough.`
        : history.trend === "worsening"
          ? ` It has resurfaced ${history.observations} times recently; best gross edge reached ${history.bestGrossEdgePct}%, but the shortfall trend is worsening.`
          : ` It has resurfaced ${history.observations} times recently; best gross edge reached ${history.bestGrossEdgePct}%, but the shortfall remains sticky.`
      : "";
    return `A real cross-venue match exists, but the spread is still too weak after costs. Gross edge is ${gross}% against ${drag}% cost drag, so Bill still needs roughly ${shortfall}% more gross dislocation before paper deployment.${historySentence}`;
  }
  if (review.topCandidate.reasons.includes("expiry-mismatch")) {
    return "The top spread is economically large, but the contracts resolve on different expiry windows, so Bill must keep it in watch mode until it finds a same-horizon match.";
  }
  if (review.topCandidate.reasons.includes("settlement-unclear")) {
    return "The top spread is still blocked by unclear settlement alignment. Tighten normalization before paper deployment.";
  }
  if (review.topCandidate.reasons.includes("weak-match")) {
    return "The top spread is still too semantically loose for paper deployment. Tighten contract matching before routing it.";
  }
  if (committee.finalStance === "reject" && contractVote?.stance === "reject") {
    return "Top-ranked pair is still structurally noisy. Tighten collection or normalization before widening execution.";
  }
  return committee.summary;
}

export function buildPredictionCycleReview(args: {
  ts: string;
  policy: PredictionSourcePolicy;
  venueCounts: Record<string, number>;
  counts: Record<PredictionVerdict, number>;
  rows: PredictionCandidate[];
  recentCycles?: Array<Record<string, unknown>>;
}): PredictionCycleReview {
  const { ts, policy, venueCounts, counts, rows } = args;
  const healthyVenues = Object.entries(venueCounts).filter(([, count]) => count >= policy.minRowsPerVenue).map(([venue]) => venue);
  const checks: PredictionReviewCheck[] = [
    buildCheck({
      name: "healthyVenues",
      passed: healthyVenues.length >= policy.minHealthyVenues,
      observed: healthyVenues.length,
      threshold: policy.minHealthyVenues,
      reason: healthyVenues.length >= policy.minHealthyVenues
        ? "Enough venues are contributing comparable rows."
        : "Too few venues are contributing enough comparable rows."
    }),
    buildCheck({
      name: "watchCandidates",
      passed: (counts.watch ?? 0) >= policy.minWatchCandidates,
      observed: counts.watch ?? 0,
      threshold: policy.minWatchCandidates,
      reason: (counts.watch ?? 0) >= policy.minWatchCandidates
        ? "At least one watch candidate exists."
        : "No watch candidates cleared the current thresholds."
    }),
    buildCheck({
      name: "paperCandidates",
      passed: (counts["paper-trade"] ?? 0) >= policy.minPaperCandidates,
      observed: counts["paper-trade"] ?? 0,
      threshold: policy.minPaperCandidates,
      reason: (counts["paper-trade"] ?? 0) >= policy.minPaperCandidates
        ? "At least one paper-trade candidate exists."
        : "No paper-trade candidate exists."
    })
  ];

  for (const source of policy.requiredSources) {
    checks.push(buildCheck({
      name: `requiredSource:${source}`,
      passed: (venueCounts[source] ?? 0) >= policy.minRowsPerVenue,
      observed: venueCounts[source] ?? 0,
      threshold: policy.minRowsPerVenue,
      reason: (venueCounts[source] ?? 0) >= policy.minRowsPerVenue
        ? `${source} is contributing enough rows.`
        : `${source} is missing or below the minimum row threshold.`
    }));
  }

  const blockers = checks.filter((check) => !check.passed).map((check) => {
    if (check.name.startsWith("requiredSource:")) return `required-source-missing:${check.name.split(":")[1]}`;
    if (check.name === "healthyVenues") return "venue-health-insufficient";
    if (check.name === "watchCandidates") return "no-watch-candidates";
    if (check.name === "paperCandidates") return "no-paper-candidates";
    return `check-failed:${check.name}`;
  });

  const review: PredictionCycleReview = {
    ts,
    policy,
    venueCounts,
    counts,
    topCandidate: topCandidate(rows, args.recentCycles ?? []),
    checks,
    blockers,
    recommendation: recommendationFromChecks(blockers, counts),
    readyForPaper: blockers.length === 0
  };

  if (review.topCandidate && review.topCandidate.recommendedStake <= 0) {
    review.blockers.push("top-candidate-zero-stake");
    review.readyForPaper = false;
    review.recommendation = "The top candidate has zero recommended stake. Fix sizing confidence or liquidity before paper deployment.";
  }

  if (review.topCandidate?.verdict !== "paper-trade") {
    review.blockers.push("lead-candidate-not-paper-trade");
    review.readyForPaper = false;
  }

  if (review.topCandidate?.committee && review.topCandidate.committee.finalStance !== "approve") {
    review.blockers.push(`committee-${review.topCandidate.committee.finalStance}`);
    review.readyForPaper = false;
  }

  const committeeRecommendation = recommendationFromTopCandidate(review);
  if (committeeRecommendation) {
    review.recommendation = committeeRecommendation;
  }

  return review;
}
