import { mkdir, readFile, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import type { PredictionMarketSnapshot, PredictionCycleReview } from "../prediction/types.js";
import type { MacroConditionedPolicyReport, MacroConditionedPolicyCandidate } from "./macroConditionedPolicy.js";
import type { StrategyFactoryReport } from "./strategyFactory.js";

export interface EdgeForensicsReport {
  command: "edge-forensics";
  generatedAt: string;
  status: "no-deployable-edge" | "edge-candidate-unproven" | "edge-candidate-active";
  paths: {
    outputPath: string;
    predictionSnapshotPath: string;
    predictionReviewPath: string;
    macroPolicyPath: string;
    strategyFactoryPath: string;
  };
  predictionMarkets: {
    venueCounts: Record<string, number>;
    topicCountsByVenue: Record<string, Record<string, number>>;
    currentCandidateCounts: Record<string, number>;
    rootCauses: string[];
  };
  futures: {
    bestLeaf: MacroConditionedPolicyCandidate | null;
    positiveLeaves: number;
    negativeLeaves: number;
    strategySummary: Record<string, {
      leaves: number;
      trades: number;
      netTotalR: number;
      averageR: number;
      positiveLeaves: number;
      negativeLeaves: number;
    }>;
    factoryBlockers: string[];
    rootCauses: string[];
  };
  conclusion: string[];
  nextExperiments: string[];
}

const DEFAULT_OUTPUT_PATH = ".rumbling-hedge/state/edge-forensics.latest.json";
const TOPICS = [
  "bitcoin",
  "ethereum",
  "crypto",
  "cpi",
  "gdp",
  "fed",
  "rate",
  "election",
  "trump",
  "iran",
  "israel",
  "gaza",
  "ukraine",
  "sports",
  "nba",
  "nfl",
  "weather",
  "stock"
];

async function readJsonSafe<T>(path: string): Promise<T | null> {
  try {
    return JSON.parse(await readFile(resolve(path), "utf8")) as T;
  } catch {
    return null;
  }
}

function round(value: number): number {
  return Number(value.toFixed(4));
}

function summarizePredictionSnapshot(markets: PredictionMarketSnapshot[]): {
  venueCounts: Record<string, number>;
  topicCountsByVenue: Record<string, Record<string, number>>;
} {
  const venueCounts: Record<string, number> = {};
  const topicCountsByVenue: Record<string, Record<string, number>> = {};
  for (const market of markets) {
    venueCounts[market.venue] = (venueCounts[market.venue] ?? 0) + 1;
    const text = `${market.eventTitle} ${market.marketQuestion}`.toLowerCase();
    const topicCounts = topicCountsByVenue[market.venue] ?? {};
    for (const topic of TOPICS) {
      if (text.includes(topic)) {
        topicCounts[topic] = (topicCounts[topic] ?? 0) + 1;
      }
    }
    topicCountsByVenue[market.venue] = topicCounts;
  }
  return { venueCounts, topicCountsByVenue };
}

function summarizeLeaves(leaves: MacroConditionedPolicyCandidate[]): EdgeForensicsReport["futures"]["strategySummary"] {
  const byStrategy: EdgeForensicsReport["futures"]["strategySummary"] = {};
  for (const leaf of leaves) {
    const current = byStrategy[leaf.strategyId] ?? {
      leaves: 0,
      trades: 0,
      netTotalR: 0,
      averageR: 0,
      positiveLeaves: 0,
      negativeLeaves: 0
    };
    current.leaves += 1;
    current.trades += leaf.trades;
    current.netTotalR = round(current.netTotalR + leaf.netTotalR);
    current.positiveLeaves += leaf.netTotalR > 0 ? 1 : 0;
    current.negativeLeaves += leaf.netTotalR <= 0 ? 1 : 0;
    current.averageR = current.trades > 0 ? round(current.netTotalR / current.trades) : 0;
    byStrategy[leaf.strategyId] = current;
  }
  return byStrategy;
}

function candidateCounts(review: PredictionCycleReview | null): Record<string, number> {
  return {
    reject: review?.counts.reject ?? 0,
    watch: review?.counts.watch ?? 0,
    "paper-trade": review?.counts["paper-trade"] ?? 0
  };
}

export async function buildEdgeForensics(args: {
  env?: NodeJS.ProcessEnv;
  now?: () => string;
  outputPath?: string;
  predictionSnapshotPath?: string;
  predictionReviewPath?: string;
  macroPolicyPath?: string;
  strategyFactoryPath?: string;
} = {}): Promise<EdgeForensicsReport> {
  const env = args.env ?? process.env;
  const generatedAt = args.now?.() ?? new Date().toISOString();
  const outputPath = resolve(args.outputPath ?? env.BILL_EDGE_FORENSICS_PATH ?? DEFAULT_OUTPUT_PATH);
  const predictionSnapshotPath = resolve(args.predictionSnapshotPath ?? env.BILL_PREDICTION_COLLECT_OUTPUT_PATH ?? ".rumbling-hedge/runtime/prediction/combined-live-snapshot.json");
  const predictionReviewPath = resolve(args.predictionReviewPath ?? env.BILL_PREDICTION_REVIEW_PATH ?? ".rumbling-hedge/state/prediction-review.latest.json");
  const macroPolicyPath = resolve(args.macroPolicyPath ?? env.BILL_MACRO_CONDITIONED_POLICY_PATH ?? ".rumbling-hedge/state/macro-conditioned-policy.latest.json");
  const strategyFactoryPath = resolve(args.strategyFactoryPath ?? env.BILL_STRATEGY_FACTORY_PATH ?? ".rumbling-hedge/state/strategy-factory.latest.json");
  const [markets, review, macroPolicy, strategyFactory] = await Promise.all([
    readJsonSafe<PredictionMarketSnapshot[]>(predictionSnapshotPath),
    readJsonSafe<PredictionCycleReview>(predictionReviewPath),
    readJsonSafe<MacroConditionedPolicyReport>(macroPolicyPath),
    readJsonSafe<StrategyFactoryReport>(strategyFactoryPath)
  ]);
  const predictionSummary = summarizePredictionSnapshot(markets ?? []);
  const leaves = [...(macroPolicy?.candidates ?? []), ...(macroPolicy?.rejectedLeaves ?? [])];
  const bestLeaf = macroPolicy?.selected ?? macroPolicy?.candidates?.[0] ?? null;
  const positiveLeaves = leaves.filter((leaf) => leaf.netTotalR > 0).length;
  const negativeLeaves = leaves.filter((leaf) => leaf.netTotalR <= 0).length;
  const paperCandidates = review?.counts["paper-trade"] ?? 0;
  const factoryBlockers = strategyFactory?.blockers ?? [];
  const predictionRootCauses = [
    ...(!markets || markets.length === 0 ? ["no live prediction snapshot loaded"] : []),
    ...((review?.counts.watch ?? 0) === 0 ? ["no watch candidates survived contract matching"] : []),
    ...(paperCandidates === 0 ? ["no paper candidates survived fees, liquidity, settlement, and semantic matching"] : []),
    ...((predictionSummary.venueCounts.manifold ?? 0) === 0 ? ["Manifold unavailable/empty, removing one cross-venue comparison source"] : []),
    ...((predictionSummary.venueCounts.kalshi ?? 0) > 0 && Object.keys(predictionSummary.topicCountsByVenue.kalshi ?? {}).length <= 2
      ? ["Kalshi snapshot is concentrated in macro series while Polymarket is broad crypto/election/sports, so overlap is low"]
      : [])
  ];
  const futuresRootCauses = [
    ...(!bestLeaf ? ["no futures leaf produced a candidate"] : []),
    ...(bestLeaf && bestLeaf.trades < 20 ? [`best futures leaf has only ${bestLeaf.trades} trades; sample is too thin for live money`] : []),
    ...(factoryBlockers.length > 0 ? ["strategy factory blocks promotion due OOS/live-readiness/research-feed gates"] : []),
    ...((leaves.filter((leaf) => leaf.strategyId === "opening-range-reversal" && leaf.netTotalR <= 0).length > 0)
      ? ["opening-range-reversal is negative in current macro-conditioned evidence"]
      : []),
    ...((leaves.filter((leaf) => leaf.strategyId === "session-momentum" && leaf.netTotalR <= 0).length > 0)
      ? ["session-momentum is negative in current macro-conditioned evidence"]
      : [])
  ];
  const status = paperCandidates > 0 || (bestLeaf?.action === "paper-allow" && (bestLeaf?.trades ?? 0) >= 20)
    ? "edge-candidate-active"
    : bestLeaf?.action === "paper-allow"
      ? "edge-candidate-unproven"
      : "no-deployable-edge";
  const bestLeafLabel = bestLeaf ? `${bestLeaf.symbol}/${bestLeaf.strategyId}` : "no futures leaf";
  const firstLaneStrategy = bestLeaf?.strategyId ?? "the best available leaf";

  const report: EdgeForensicsReport = {
    command: "edge-forensics",
    generatedAt,
    status,
    paths: {
      outputPath,
      predictionSnapshotPath,
      predictionReviewPath,
      macroPolicyPath,
      strategyFactoryPath
    },
    predictionMarkets: {
      ...predictionSummary,
      currentCandidateCounts: candidateCounts(review),
      rootCauses: predictionRootCauses
    },
    futures: {
      bestLeaf,
      positiveLeaves,
      negativeLeaves,
      strategySummary: summarizeLeaves(leaves),
      factoryBlockers,
      rootCauses: futuresRootCauses
    },
    conclusion: [
      "The system is not at zero raw signal; it is at zero deployable edge.",
      "Prediction markets currently have venue coverage but no overlapping comparable contracts after matching.",
      `Futures best current leaf is ${bestLeafLabel}, but the sample is too thin and OOS/live-readiness gates reject promotion.`,
      "Most other current futures leaves are negative, especially opening-range-reversal and session-momentum in this data window."
    ],
    nextExperiments: [
      "For prediction markets, narrow collection by common event families across venues instead of broad venue sampling.",
      "Add Kalshi series targeting that overlaps Polymarket macro/rates/election markets before scanning.",
      `For futures, run longer NQ/ES normalized data windows and require leaf-level OOS for ${firstLaneStrategy} before any promotion.`,
      "Disable opening-range-reversal and session-momentum from first-lane promotion until their macro-conditioned evidence repairs.",
      "Use prediction probabilities as context features for futures only after same-event prediction candidates exist."
    ]
  };

  await mkdir(dirname(outputPath), { recursive: true });
  await writeFile(outputPath, `${JSON.stringify(report, null, 2)}\n`, "utf8");
  return report;
}
