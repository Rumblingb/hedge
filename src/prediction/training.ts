import { appendFile, mkdir, readFile, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import type { PredictionCandidate, PredictionPolicyEvaluation, PredictionRecentCycleSummary, PredictionScanPolicy, PredictionSourceSummary, PredictionTrainingState } from "./types.js";
import { classifyPredictionCandidate, DEFAULT_PREDICTION_LEARNED_POLICY_PATH, DEFAULT_PREDICTION_SCAN_POLICY, resolvePredictionScanPolicy, writePredictionLearnedPolicy } from "./scanPolicy.js";

interface BillSourceStatusLike {
  category?: string;
  mode?: string;
}

function round(value: number): number {
  return Number(value.toFixed(4));
}

function average(values: number[]): number {
  if (values.length === 0) return 0;
  return values.reduce((sum, value) => sum + value, 0) / values.length;
}

function generatePolicyGrid(base: PredictionScanPolicy): PredictionScanPolicy[] {
  const minMatchScores = [...new Set([0.68, 0.7, 0.72, 0.75, base.minMatchScore].map((value) => Number(value.toFixed(2))))];
  const paperMatchScores = [...new Set([0.8, 0.85, 0.9, base.paperMatchScore].map((value) => Number(value.toFixed(2))))];
  const paperEdges = [...new Set([2.5, 3, 4, 5, base.paperEdgeThresholdPct].map((value) => Number(value.toFixed(2))))];
  const minDisplayedSizes = [...new Set([50, 100, 150, base.minDisplayedSize].map((value) => Math.round(value)))];
  const minRecommendedStakes = [...new Set([1, 2, 3, base.minRecommendedStake].map((value) => Number(value.toFixed(2))))];

  const grid: PredictionScanPolicy[] = [];
  for (const minMatchScore of minMatchScores) {
    for (const paperMatchScore of paperMatchScores) {
      if (paperMatchScore < minMatchScore) continue;
      for (const paperEdgeThresholdPct of paperEdges) {
        for (const minDisplayedSize of minDisplayedSizes) {
          for (const minRecommendedStake of minRecommendedStakes) {
            grid.push({
              minMatchScore,
              paperMatchScore,
              paperEdgeThresholdPct,
              minDisplayedSize,
              minRecommendedStake
            });
          }
        }
      }
    }
  }
  return grid;
}

export function evaluatePredictionPolicy(rows: PredictionCandidate[], policy: PredictionScanPolicy): PredictionPolicyEvaluation {
  const classified = rows.map((row) => {
    const next = classifyPredictionCandidate({ candidate: row, policy });
    return { ...row, ...next };
  });

  const paperRows = classified.filter((row) => row.verdict === "paper-trade");
  const watchRows = classified.filter((row) => row.verdict === "watch");
  const rejectRows = classified.filter((row) => row.verdict === "reject");
  const lowConvictionPaperCount = paperRows.filter((row) =>
    row.matchScore < 0.8 || row.netEdgePct < 4 || (row.sizing?.recommendedStake ?? 0) < Math.max(policy.minRecommendedStake, 2)
  ).length;

  const avgPaperEdgePct = average(paperRows.map((row) => row.netEdgePct));
  const avgPaperMatchScore = average(paperRows.map((row) => row.matchScore));
  const avgPaperStake = average(paperRows.map((row) => row.sizing?.recommendedStake ?? 0));
  const topPaperEdgePct = paperRows[0]?.netEdgePct ?? 0;
  const uniqueVenuePairs = new Set(paperRows.map((row) => `${row.venueA}->${row.venueB}`)).size;
  const densityPenalty = Math.max(0, paperRows.length - 3) * 1.5;
  const objectiveScore = round(
    (paperRows.length * 2)
    + (avgPaperEdgePct * 0.9)
    + (avgPaperMatchScore * 5)
    + (Math.min(uniqueVenuePairs, 3) * 0.75)
    + (Math.min(avgPaperStake, 10) * 0.15)
    + (Math.min(topPaperEdgePct, 10) * 0.25)
    + (Math.min(watchRows.length, 3) * 0.25)
    - (lowConvictionPaperCount * 2.5)
    - densityPenalty
  );

  return {
    objectiveScore,
    counts: {
      reject: rejectRows.length,
      watch: watchRows.length,
      "paper-trade": paperRows.length
    },
    paperCount: paperRows.length,
    watchCount: watchRows.length,
    rejectCount: rejectRows.length,
    avgPaperEdgePct: round(avgPaperEdgePct),
    avgPaperMatchScore: round(avgPaperMatchScore),
    avgPaperStake: round(avgPaperStake),
    topPaperEdgePct: round(topPaperEdgePct),
    uniqueVenuePairs,
    lowConvictionPaperCount
  };
}

export function summarizePredictionSources(rows: BillSourceStatusLike[]): PredictionSourceSummary {
  const totalSources = rows.length;
  const activeSources = rows.filter((row) => row.mode === "active").length;
  const activePredictionSources = rows.filter((row) => row.mode === "active" && row.category === "prediction-market").length;
  const missingConfigSources = rows.filter((row) => row.mode === "missing-config").length;
  const catalogOnlySources = rows.filter((row) => row.mode === "catalog-only").length;

  return {
    totalSources,
    activeSources,
    activePredictionSources,
    missingConfigSources,
    catalogOnlySources
  };
}

export function summarizeRecentPredictionCycles(rows: Array<Record<string, unknown>>): PredictionRecentCycleSummary {
  const totalCycles = rows.length;
  const healthyCycles = rows.filter((row) => Number(row.venuesHealthy ?? 0) >= 2).length;
  const paperCandidateCycles = rows.filter((row) => Number(((row.scan as { counts?: Record<string, number> } | undefined)?.counts?.["paper-trade"]) ?? 0) > 0).length;
  const averageTopEdgePct = average(rows.map((row) => Number((row.topCandidate as { netEdgePct?: number } | undefined)?.netEdgePct ?? 0)).filter((value) => value > 0));
  const averageTopMatchScore = average(rows.map((row) => Number((row.topCandidate as { matchScore?: number } | undefined)?.matchScore ?? 0)).filter((value) => value > 0));
  const structuralWatchCycles = rows.filter((row) => {
    const votes = (((row.review as { topCandidate?: { committee?: { votes?: Array<{ analyst?: string; stance?: string }> } } } | undefined)
      ?.topCandidate?.committee?.votes) ?? []);
    return votes.some((vote) =>
      ["contract-analyst", "portfolio-manager"].includes(vote.analyst ?? "") && vote.stance !== "approve"
    );
  }).length;
  const economicBlockCycles = rows.filter((row) => {
    const votes = (((row.review as { topCandidate?: { committee?: { votes?: Array<{ analyst?: string; stance?: string }> } } } | undefined)
      ?.topCandidate?.committee?.votes) ?? []);
    return votes.some((vote) =>
      ["edge-analyst", "risk-manager"].includes(vote.analyst ?? "") && vote.stance === "reject"
    );
  }).length;

  const recurring = new Map<string, Array<{ grossEdgePct: number; edgeShortfallPct: number }>>();
  for (const row of rows) {
    const candidate = (row.review as {
      topCandidate?: {
        candidateId?: string;
        grossEdgePct?: number;
        edgeShortfallPct?: number;
      };
    } | undefined)?.topCandidate;
    if (!candidate?.candidateId) continue;
    const values = recurring.get(candidate.candidateId) ?? [];
    values.push({
      grossEdgePct: Number(candidate.grossEdgePct ?? 0),
      edgeShortfallPct: Number(candidate.edgeShortfallPct ?? 0)
    });
    recurring.set(candidate.candidateId, values);
  }

  const dominantEntry = [...recurring.entries()].sort((a, b) => b[1].length - a[1].length)[0];
  const dominantCandidate = dominantEntry
    ? {
        candidateId: dominantEntry[0],
        observations: dominantEntry[1].length,
        bestGrossEdgePct: round(Math.max(...dominantEntry[1].map((entry) => entry.grossEdgePct))),
        latestGrossEdgePct: round(dominantEntry[1][dominantEntry[1].length - 1]?.grossEdgePct ?? 0),
        latestShortfallPct: round(dominantEntry[1][dominantEntry[1].length - 1]?.edgeShortfallPct ?? 0),
        trend:
          (dominantEntry[1][dominantEntry[1].length - 1]?.grossEdgePct ?? 0) > (dominantEntry[1][0]?.grossEdgePct ?? 0)
            ? "improving" as const
            : (dominantEntry[1][dominantEntry[1].length - 1]?.grossEdgePct ?? 0) < (dominantEntry[1][0]?.grossEdgePct ?? 0)
              ? "worsening" as const
              : "flat" as const
      }
    : null;

  return {
    totalCycles,
    healthyCycles,
    paperCandidateCycles,
    structuralWatchCycles,
    economicBlockCycles,
    averageTopEdgePct: round(averageTopEdgePct),
    averageTopMatchScore: round(averageTopMatchScore),
    dominantCandidate
  };
}

function buildRecommendations(args: {
  baseline: PredictionPolicyEvaluation;
  selected: PredictionPolicyEvaluation;
  sourceSummary: PredictionSourceSummary;
  cycleSummary: PredictionRecentCycleSummary;
}): string[] {
  const { baseline, selected, sourceSummary, cycleSummary } = args;
  const recommendations: string[] = [];

  if (sourceSummary.activePredictionSources < 2) {
    recommendations.push("Restore at least two active prediction-market sources before trusting further scan-policy changes.");
  }
  if (selected.paperCount === 0) {
    recommendations.push("No paper-trade candidates clear the current evidence bar. Keep collecting instead of forcing execution.");
  }
  if (selected.objectiveScore > baseline.objectiveScore) {
    recommendations.push("Adopt the learned scan policy because it improves the quality-weighted paper-candidate objective.");
  } else {
    recommendations.push("Hold the prior scan policy; the latest journal does not support a better threshold set yet.");
  }
  if (cycleSummary.totalCycles > 0 && cycleSummary.paperCandidateCycles === 0) {
    recommendations.push("Recent cycles produced no paper candidates. Focus on venue health and source normalization before widening scope.");
  }
  if (sourceSummary.missingConfigSources > 0) {
    recommendations.push("Missing-config sources are still setup debt. Keep Bill's execution lane narrow until more sources are actually wired and stable.");
  }

  return recommendations;
}

export function trainPredictionPolicy(args: {
  rows: PredictionCandidate[];
  currentPolicy: PredictionScanPolicy;
  sourceSummary: PredictionSourceSummary;
  recentCycleSummary: PredictionRecentCycleSummary;
  paths: {
    journalPath: string;
    policyPath: string;
    statePath: string;
    historyPath: string;
    trainingSetPath: string;
  };
  ts?: string;
}): PredictionTrainingState {
  const ts = args.ts ?? new Date().toISOString();
  const baselineEvaluation = evaluatePredictionPolicy(args.rows, args.currentPolicy);
  let selectedPolicy = args.currentPolicy;
  let selectedEvaluation = baselineEvaluation;

  for (const candidatePolicy of generatePolicyGrid(args.currentPolicy)) {
    const evaluation = evaluatePredictionPolicy(args.rows, candidatePolicy);
    if (evaluation.objectiveScore > selectedEvaluation.objectiveScore) {
      selectedPolicy = candidatePolicy;
      selectedEvaluation = evaluation;
    }
  }

  return {
    ts,
    journalPath: args.paths.journalPath,
    policyPath: args.paths.policyPath,
    statePath: args.paths.statePath,
    historyPath: args.paths.historyPath,
    trainingSetPath: args.paths.trainingSetPath,
    baselinePolicy: args.currentPolicy,
    selectedPolicy,
    baselineEvaluation,
    selectedEvaluation,
    recentCycleSummary: args.recentCycleSummary,
    sourceSummary: args.sourceSummary,
    recommendations: buildRecommendations({
      baseline: baselineEvaluation,
      selected: selectedEvaluation,
      sourceSummary: args.sourceSummary,
      cycleSummary: args.recentCycleSummary
    })
  };
}

async function readJsonArray(filePath: string): Promise<unknown[]> {
  try {
    const raw = await readFile(resolve(filePath), "utf8");
    return JSON.parse(raw) as unknown[];
  } catch {
    return [];
  }
}

async function readJsonl(filePath: string): Promise<Array<Record<string, unknown>>> {
  try {
    const raw = await readFile(resolve(filePath), "utf8");
    return raw
      .split(/\r?\n/)
      .map((line) => line.trim())
      .filter(Boolean)
      .map((line) => JSON.parse(line) as Record<string, unknown>);
  } catch {
    return [];
  }
}

async function writeJson(filePath: string, value: unknown): Promise<string> {
  const target = resolve(filePath);
  await mkdir(dirname(target), { recursive: true });
  await writeFile(target, `${JSON.stringify(value, null, 2)}\n`, "utf8");
  return target;
}

export async function runPredictionTraining(args: {
  env?: NodeJS.ProcessEnv;
  journalPath?: string;
  sourceCatalogPath?: string;
  cycleHistoryPath?: string;
  trainingSetPath?: string;
  statePath?: string;
  historyPath?: string;
  policyPath?: string;
} = {}): Promise<PredictionTrainingState> {
  const env = args.env ?? process.env;
  const journalPath = resolve(args.journalPath ?? env.BILL_PREDICTION_JOURNAL_PATH ?? ".rumbling-hedge/runtime/prediction/opportunities.jsonl");
  const sourceCatalogPath = args.sourceCatalogPath ?? ".rumbling-hedge/research/source-catalog.json";
  const cycleHistoryPath = args.cycleHistoryPath ?? env.BILL_PREDICTION_CYCLE_HISTORY_PATH ?? ".rumbling-hedge/logs/prediction-cycle-history.jsonl";
  const trainingSetPath = args.trainingSetPath ?? env.BILL_PREDICTION_TRAINING_SET_PATH ?? ".rumbling-hedge/research/prediction-training-set.json";
  const statePath = args.statePath ?? env.BILL_PREDICTION_LEARNING_STATE_PATH ?? ".rumbling-hedge/state/prediction-learning.latest.json";
  const historyPath = args.historyPath ?? env.BILL_PREDICTION_LEARNING_HISTORY_PATH ?? ".rumbling-hedge/logs/prediction-learning-history.jsonl";
  const policyPath = args.policyPath ?? env.BILL_PREDICTION_LEARNED_POLICY_PATH ?? DEFAULT_PREDICTION_LEARNED_POLICY_PATH;
  const currentPolicy = await resolvePredictionScanPolicy({ ...env, BILL_PREDICTION_LEARNED_POLICY_ENABLED: "false" });

  const rows = await readJsonl(journalPath) as unknown as PredictionCandidate[];
  const sourceRows = await readJsonArray(sourceCatalogPath) as BillSourceStatusLike[];
  const recentCycles = (await readJsonl(cycleHistoryPath)).slice(-20);
  const sourceSummary = summarizePredictionSources(sourceRows);
  const recentCycleSummary = summarizeRecentPredictionCycles(recentCycles);

  const state = trainPredictionPolicy({
    rows,
    currentPolicy: rows.length > 0 ? currentPolicy : DEFAULT_PREDICTION_SCAN_POLICY,
    sourceSummary,
    recentCycleSummary,
    paths: {
      journalPath,
      policyPath: resolve(policyPath),
      statePath: resolve(statePath),
      historyPath: resolve(historyPath),
      trainingSetPath: resolve(trainingSetPath)
    }
  });

  await writeJson(trainingSetPath, {
    ts: state.ts,
    journalPath,
    rows,
    sourceSummary,
    recentCycleSummary
  });
  await writeJson(statePath, state);
  await writePredictionLearnedPolicy({
    filePath: policyPath,
    ts: state.ts,
    selectedPolicy: state.selectedPolicy,
    objectiveScore: state.selectedEvaluation.objectiveScore
  });
  await mkdir(dirname(resolve(historyPath)), { recursive: true });
  await appendFile(resolve(historyPath), `${JSON.stringify(state)}\n`, "utf8");
  return state;
}
