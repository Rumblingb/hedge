import type { BillPromotionState, PredictionCycleReview } from "../types.js";

export interface PredictionExecutionAuthorization {
  ok: boolean;
  reason: string | null;
}

interface AuthorizePredictionExecutionArgs {
  mode: "paper" | "live";
  review?: PredictionCycleReview | null;
  promotion?: BillPromotionState | null;
}

export function authorizePredictionExecution(
  args: AuthorizePredictionExecutionArgs
): PredictionExecutionAuthorization {
  if (args.mode === "live") {
    if (args.review?.readyForPaper !== true) {
      return {
        ok: false,
        reason: "prediction review is not ready for live execution"
      };
    }

    if (args.promotion?.currentStage !== "live" && args.promotion?.recommendedStage !== "live") {
      return {
        ok: false,
        reason: `promotion state is not explicitly at live (current=${args.promotion?.currentStage ?? "research"}, recommended=${args.promotion?.recommendedStage ?? "research"})`
      };
    }

    return { ok: true, reason: null };
  }

  if (args.mode !== "paper") {
    return { ok: true, reason: null };
  }

  if (args.review?.readyForPaper !== true) {
    return {
      ok: false,
      reason: "prediction review is not ready for paper execution"
    };
  }

  if (args.promotion?.recommendedStage !== "paper") {
    return {
      ok: false,
      reason: `promotion state recommends ${args.promotion?.recommendedStage ?? "research"} instead of paper`
    };
  }

  return { ok: true, reason: null };
}
