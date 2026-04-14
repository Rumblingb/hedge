import { mkdir, readFile, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import type { PredictionCandidate, PredictionScanPolicy, PredictionVerdict } from "./types.js";

export const DEFAULT_PREDICTION_SCAN_POLICY: PredictionScanPolicy = {
  minMatchScore: 0.7,
  paperMatchScore: 0.85,
  paperEdgeThresholdPct: 3,
  minDisplayedSize: 100,
  minRecommendedStake: 1
};

export const DEFAULT_PREDICTION_LEARNED_POLICY_PATH = ".rumbling-hedge/state/prediction-learned-policy.json";

function readNumber(env: NodeJS.ProcessEnv, key: string, fallback: number): number {
  const raw = env[key];
  if (!raw) return fallback;
  const parsed = Number(raw);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function clampPolicy(input: Partial<PredictionScanPolicy>): PredictionScanPolicy {
  const minMatchScore = Math.min(Math.max(input.minMatchScore ?? DEFAULT_PREDICTION_SCAN_POLICY.minMatchScore, 0.5), 0.99);
  const paperMatchScore = Math.min(Math.max(input.paperMatchScore ?? DEFAULT_PREDICTION_SCAN_POLICY.paperMatchScore, minMatchScore), 0.99);
  return {
    minMatchScore: Number(minMatchScore.toFixed(2)),
    paperMatchScore: Number(paperMatchScore.toFixed(2)),
    paperEdgeThresholdPct: Number(Math.max(0, input.paperEdgeThresholdPct ?? DEFAULT_PREDICTION_SCAN_POLICY.paperEdgeThresholdPct).toFixed(2)),
    minDisplayedSize: Math.max(1, Math.round(input.minDisplayedSize ?? DEFAULT_PREDICTION_SCAN_POLICY.minDisplayedSize)),
    minRecommendedStake: Number(Math.max(0, input.minRecommendedStake ?? DEFAULT_PREDICTION_SCAN_POLICY.minRecommendedStake).toFixed(2))
  };
}

export function buildPredictionScanPolicyFromEnv(env: NodeJS.ProcessEnv = process.env): PredictionScanPolicy {
  return clampPolicy({
    minMatchScore: readNumber(env, "BILL_PREDICTION_MIN_MATCH_SCORE", DEFAULT_PREDICTION_SCAN_POLICY.minMatchScore),
    paperMatchScore: readNumber(env, "BILL_PREDICTION_PAPER_MATCH_SCORE", DEFAULT_PREDICTION_SCAN_POLICY.paperMatchScore),
    paperEdgeThresholdPct: readNumber(env, "BILL_PREDICTION_PAPER_EDGE_PCT", DEFAULT_PREDICTION_SCAN_POLICY.paperEdgeThresholdPct),
    minDisplayedSize: readNumber(env, "BILL_PREDICTION_MIN_DISPLAYED_SIZE", DEFAULT_PREDICTION_SCAN_POLICY.minDisplayedSize),
    minRecommendedStake: readNumber(env, "BILL_PREDICTION_MIN_RECOMMENDED_STAKE", DEFAULT_PREDICTION_SCAN_POLICY.minRecommendedStake)
  });
}

export function predictionLearnedPolicyEnabled(env: NodeJS.ProcessEnv = process.env): boolean {
  return env.BILL_PREDICTION_LEARNED_POLICY_ENABLED !== "false";
}

export async function readPredictionLearnedPolicy(filePath = DEFAULT_PREDICTION_LEARNED_POLICY_PATH): Promise<PredictionScanPolicy | null> {
  try {
    const raw = await readFile(resolve(filePath), "utf8");
    const parsed = JSON.parse(raw) as { selectedPolicy?: Partial<PredictionScanPolicy> } & Partial<PredictionScanPolicy>;
    const selectedPolicy = typeof parsed.selectedPolicy === "object" && parsed.selectedPolicy ? parsed.selectedPolicy : null;
    return clampPolicy(selectedPolicy ?? parsed);
  } catch {
    return null;
  }
}

export async function resolvePredictionScanPolicy(env: NodeJS.ProcessEnv = process.env): Promise<PredictionScanPolicy> {
  const envPolicy = buildPredictionScanPolicyFromEnv(env);
  if (!predictionLearnedPolicyEnabled(env)) {
    return envPolicy;
  }

  const learned = await readPredictionLearnedPolicy(env.BILL_PREDICTION_LEARNED_POLICY_PATH ?? DEFAULT_PREDICTION_LEARNED_POLICY_PATH);
  if (!learned) {
    return envPolicy;
  }

  return clampPolicy({ ...envPolicy, ...learned });
}

export async function writePredictionLearnedPolicy(args: {
  filePath?: string;
  ts: string;
  selectedPolicy: PredictionScanPolicy;
  objectiveScore: number;
}): Promise<string> {
  const target = resolve(args.filePath ?? DEFAULT_PREDICTION_LEARNED_POLICY_PATH);
  await mkdir(dirname(target), { recursive: true });
  await writeFile(target, `${JSON.stringify({
    ts: args.ts,
    selectedPolicy: clampPolicy(args.selectedPolicy),
    objectiveScore: Number(args.objectiveScore.toFixed(4))
  }, null, 2)}\n`, "utf8");
  return target;
}

function sameExpiry(a?: string, b?: string): boolean {
  if (!a || !b) return false;
  return a.slice(0, 10) === b.slice(0, 10);
}

function minimumDisplayedSize(candidate: Pick<PredictionCandidate, "displayedSizeA" | "displayedSizeB">): number {
  return Math.min(candidate.displayedSizeA ?? 0, candidate.displayedSizeB ?? 0);
}

export function classifyPredictionCandidate(args: {
  candidate: Pick<PredictionCandidate, "matchScore" | "netEdgePct" | "displayedSizeA" | "displayedSizeB" | "expiryA" | "expiryB" | "settlementCompatible" | "sizing">;
  policy: PredictionScanPolicy;
}): {
  verdict: PredictionVerdict;
  reasons: string[];
  sizeVerdict: string;
} {
  const { candidate, policy } = args;
  const sizeVerdict = minimumDisplayedSize(candidate) >= policy.minDisplayedSize ? "ok" : "thin";
  const recommendedStake = candidate.sizing?.recommendedStake ?? 0;
  const reasons: string[] = [];

  if (candidate.matchScore < policy.minMatchScore) reasons.push("weak-match");
  if (!sameExpiry(candidate.expiryA, candidate.expiryB)) reasons.push("expiry-mismatch");
  if (!candidate.settlementCompatible) reasons.push("settlement-unclear");
  if (sizeVerdict !== "ok") reasons.push("thin-size");
  if (candidate.netEdgePct <= 0) reasons.push("negative-net-edge");
  if (recommendedStake < policy.minRecommendedStake) reasons.push("subscale-edge");

  const verdict: PredictionVerdict =
    reasons.includes("weak-match") || reasons.includes("settlement-unclear") || reasons.includes("expiry-mismatch")
      ? "reject"
      : sizeVerdict !== "ok" || candidate.netEdgePct <= 0 || recommendedStake < policy.minRecommendedStake
        ? "watch"
        : candidate.matchScore >= policy.paperMatchScore || candidate.netEdgePct >= policy.paperEdgeThresholdPct
          ? "paper-trade"
          : "watch";

  return { verdict, reasons, sizeVerdict };
}
