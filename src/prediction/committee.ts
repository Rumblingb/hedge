import type { PredictionCandidate, PredictionCommitteeReview, PredictionCommitteeStance, PredictionCommitteeVote } from "./types.js";

function vote(args: PredictionCommitteeVote): PredictionCommitteeVote {
  return args;
}

function sizeFloor(candidate: PredictionCandidate): number {
  return Math.min(candidate.displayedSizeA ?? 0, candidate.displayedSizeB ?? 0);
}

function contractAnalyst(candidate: PredictionCandidate): PredictionCommitteeVote {
  if (candidate.settlementCompatible && candidate.matchScore >= 0.8 && candidate.questionOverlap >= 0.8) {
    return vote({
      analyst: "contract-analyst",
      stance: "approve",
      summary: "Contract shape is strong enough to treat the pair as genuinely comparable.",
      evidence: [
        `matchScore=${candidate.matchScore}`,
        `questionOverlap=${candidate.questionOverlap}`,
        "settlement-compatible=true"
      ]
    });
  }
  if (candidate.settlementCompatible && candidate.matchScore >= 0.7) {
    return vote({
      analyst: "contract-analyst",
      stance: "watch",
      summary: "The contracts are related, but the semantic match is not tight enough for automatic deployment.",
      evidence: [
        `matchScore=${candidate.matchScore}`,
        `questionOverlap=${candidate.questionOverlap}`,
        "settlement-compatible=true"
      ]
    });
  }
  return vote({
    analyst: "contract-analyst",
    stance: "reject",
    summary: "Contract semantics are still too weak or unclear for a real cross-venue comparison.",
    evidence: [
      `matchScore=${candidate.matchScore}`,
      `questionOverlap=${candidate.questionOverlap}`,
      `settlement-compatible=${candidate.settlementCompatible}`
    ]
  });
}

function edgeAnalyst(candidate: PredictionCandidate): PredictionCommitteeVote {
  if (candidate.netEdgePct >= 3 && (candidate.sizing?.recommendedStake ?? 0) > 0) {
    return vote({
      analyst: "edge-analyst",
      stance: "approve",
      summary: "The spread is wide enough after costs to justify a paper trade.",
      evidence: [
        `netEdgePct=${candidate.netEdgePct}`,
        `recommendedStake=${candidate.sizing?.recommendedStake ?? 0}`
      ]
    });
  }
  if (candidate.netEdgePct > 0) {
    return vote({
      analyst: "edge-analyst",
      stance: "watch",
      summary: "There is some dislocation, but it is not yet large enough after costs.",
      evidence: [
        `netEdgePct=${candidate.netEdgePct}`,
        `grossEdgePct=${candidate.grossEdgePct}`
      ]
    });
  }
  return vote({
    analyst: "edge-analyst",
    stance: "reject",
    summary: "The price gap disappears after costs, so there is no economic reason to deploy.",
    evidence: [
      `netEdgePct=${candidate.netEdgePct}`,
      `grossEdgePct=${candidate.grossEdgePct}`
    ]
  });
}

function liquidityAnalyst(candidate: PredictionCandidate): PredictionCommitteeVote {
  const floor = sizeFloor(candidate);
  if (candidate.sizeVerdict === "ok" && floor >= 1_000) {
    return vote({
      analyst: "liquidity-analyst",
      stance: "approve",
      summary: "Both venues have enough displayed size for a real test fill.",
      evidence: [
        `displayedSizeA=${candidate.displayedSizeA ?? 0}`,
        `displayedSizeB=${candidate.displayedSizeB ?? 0}`
      ]
    });
  }
  if (candidate.sizeVerdict === "ok") {
    return vote({
      analyst: "liquidity-analyst",
      stance: "watch",
      summary: "Liquidity is acceptable for observation, but still thin for confident sizing.",
      evidence: [
        `displayedSizeA=${candidate.displayedSizeA ?? 0}`,
        `displayedSizeB=${candidate.displayedSizeB ?? 0}`
      ]
    });
  }
  return vote({
    analyst: "liquidity-analyst",
    stance: "reject",
    summary: "Displayed size is too thin for a trustworthy paper route.",
    evidence: [
      `displayedSizeA=${candidate.displayedSizeA ?? 0}`,
      `displayedSizeB=${candidate.displayedSizeB ?? 0}`,
      `sizeVerdict=${candidate.sizeVerdict}`
    ]
  });
}

function riskAnalyst(candidate: PredictionCandidate): PredictionCommitteeVote {
  const stake = candidate.sizing?.recommendedStake ?? 0;
  const expectedValue = candidate.sizing?.expectedValue ?? 0;
  if (stake > 0 && expectedValue > 0) {
    return vote({
      analyst: "risk-manager",
      stance: "approve",
      summary: "Sizing clears the minimum bar and the expected value is positive.",
      evidence: [
        `recommendedStake=${stake}`,
        `expectedValue=${expectedValue}`
      ]
    });
  }
  if (candidate.matchScore >= 0.8 && candidate.netEdgePct > -1) {
    return vote({
      analyst: "risk-manager",
      stance: "watch",
      summary: "The setup is structurally interesting, but the risk budget stays at zero for now.",
      evidence: [
        `recommendedStake=${stake}`,
        `netEdgePct=${candidate.netEdgePct}`
      ]
    });
  }
  return vote({
    analyst: "risk-manager",
    stance: "reject",
    summary: "Risk budget should remain at zero because the candidate does not justify stake deployment.",
    evidence: [
      `recommendedStake=${stake}`,
      `netEdgePct=${candidate.netEdgePct}`
    ]
  });
}

function count(votes: PredictionCommitteeVote[], stance: PredictionCommitteeStance): number {
  return votes.filter((vote) => vote.stance === stance).length;
}

function chair(candidate: PredictionCandidate, votes: PredictionCommitteeVote[]): PredictionCommitteeVote {
  const contract = votes.find((vote) => vote.analyst === "contract-analyst");
  const edge = votes.find((vote) => vote.analyst === "edge-analyst");
  const liquidity = votes.find((vote) => vote.analyst === "liquidity-analyst");
  const risk = votes.find((vote) => vote.analyst === "risk-manager");

  if (contract?.stance === "reject" || liquidity?.stance === "reject") {
    return vote({
      analyst: "portfolio-manager",
      stance: "reject",
      summary: "Reject the setup because comparability or tradability is still too weak.",
      evidence: [
        `contract=${contract?.stance ?? "unknown"}`,
        `liquidity=${liquidity?.stance ?? "unknown"}`
      ]
    });
  }
  if (
    contract?.stance === "approve"
    && edge?.stance === "approve"
    && liquidity?.stance === "approve"
    && risk?.stance === "approve"
  ) {
    return vote({
      analyst: "portfolio-manager",
      stance: "approve",
      summary: "The setup is comparable, tradable, and economically strong enough for paper deployment.",
      evidence: [
        `netEdgePct=${candidate.netEdgePct}`,
        `recommendedStake=${candidate.sizing?.recommendedStake ?? 0}`
      ]
    });
  }
  if (contract?.stance === "approve") {
    return vote({
      analyst: "portfolio-manager",
      stance: "watch",
      summary: "The contract is real, but this cycle should wait for a better spread or cleaner economics.",
      evidence: [
        `edge=${edge?.stance ?? "unknown"}`,
        `risk=${risk?.stance ?? "unknown"}`
      ]
    });
  }
  return vote({
    analyst: "portfolio-manager",
    stance: count(votes, "watch") >= 2 ? "watch" : "reject",
    summary: "The setup is not strong enough to move beyond observation.",
    evidence: [
      `approveVotes=${count(votes, "approve")}`,
      `watchVotes=${count(votes, "watch")}`,
      `rejectVotes=${count(votes, "reject")}`
    ]
  });
}

export function buildPredictionCommitteeReview(candidate: PredictionCandidate): PredictionCommitteeReview {
  const votes = [
    contractAnalyst(candidate),
    edgeAnalyst(candidate),
    liquidityAnalyst(candidate),
    riskAnalyst(candidate)
  ];
  const finalVote = chair(candidate, votes);
  return {
    finalStance: finalVote.stance,
    summary: finalVote.summary,
    votes: [...votes, finalVote]
  };
}
