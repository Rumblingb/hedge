import { mkdir, readFile, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import type { BillPromotionState, PredictionCycleReview } from "../prediction/types.js";

export const DEFAULT_PROMOTION_STATE_PATH = ".rumbling-hedge/state/promotion-state.json";

export function buildDefaultPromotionState(): BillPromotionState {
  return {
    track: "prediction-markets",
    currentStage: "research",
    recommendedStage: "research",
    updatedAt: new Date(0).toISOString(),
    blockers: ["no-promotion-review-yet"],
    approvalsRequired: ["operator-approval-for-demo", "operator-approval-for-live"],
    checks: [],
    notes: ["Bill remains fail-closed until the first promotion review is written."]
  };
}

export async function readPromotionState(filePath = DEFAULT_PROMOTION_STATE_PATH): Promise<BillPromotionState> {
  try {
    const raw = await readFile(resolve(filePath), "utf8");
    return JSON.parse(raw) as BillPromotionState;
  } catch {
    return buildDefaultPromotionState();
  }
}

export async function writePromotionState(state: BillPromotionState, filePath = DEFAULT_PROMOTION_STATE_PATH): Promise<string> {
  const target = resolve(filePath);
  await mkdir(dirname(target), { recursive: true });
  await writeFile(target, `${JSON.stringify(state, null, 2)}\n`, "utf8");
  return target;
}

export function buildPromotionStateFromPredictionReview(args: {
  review: PredictionCycleReview;
  prior?: BillPromotionState;
}): BillPromotionState {
  const { review, prior } = args;
  const currentStage = prior?.currentStage ?? "research";
  const recommendedStage = review.readyForPaper ? "paper" : "research";
  const notes = [
    review.recommendation,
    review.topCandidate?.committee?.summary ?? null,
    review.readyForPaper
      ? "Prediction lane has enough coverage and candidate flow to be considered for paper review."
      : "Prediction lane is still below the thresholds needed for paper promotion."
  ].filter(Boolean) as string[];

  return {
    track: "prediction-markets",
    currentStage,
    recommendedStage,
    updatedAt: review.ts,
    blockers: review.blockers,
    approvalsRequired: ["operator-approval-for-demo", "operator-approval-for-live"],
    checks: review.checks.map((check) => ({
      name: check.name,
      passed: check.passed,
      reason: check.reason
    })),
    notes
  };
}
