import type { PredictionCandidate, PredictionCycleReview, PredictionReviewCheck, PredictionSourcePolicy, PredictionVerdict } from "./types.js";

function topCandidate(rows: PredictionCandidate[]): PredictionCycleReview["topCandidate"] {
  const first = rows[0];
  if (!first) return null;
  return {
    candidateId: first.candidateId,
    verdict: first.verdict,
    netEdgePct: first.netEdgePct,
    matchScore: first.matchScore,
    recommendedStake: first.sizing?.recommendedStake ?? 0,
    venuePair: `${first.venueA}->${first.venueB}`
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

export function buildPredictionCycleReview(args: {
  ts: string;
  policy: PredictionSourcePolicy;
  venueCounts: Record<string, number>;
  counts: Record<PredictionVerdict, number>;
  rows: PredictionCandidate[];
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
    topCandidate: topCandidate(rows),
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

  return review;
}
