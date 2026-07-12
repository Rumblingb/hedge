import { appendFile, mkdir, readFile, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import type { Classification, SupportedStrategyId } from "../domain.js";
import { getClassification } from "../domain.js";
import type { PromotionGateResult } from "../engine/promotionGate.js";
import type { WalkforwardProfileResult } from "../engine/walkforward.js";

export type NoEdgeVerdict = "promotable" | "no-edge" | "needs-more-data" | "blocked";

export interface NoEdgeLedgerEntry {
  profileId: string;
  strategies: SupportedStrategyId[];
  verdict: NoEdgeVerdict;
  status: string;
  testTrades: number;
  testNetR: number;
  testExpectancyR: number;
  maxDrawdownR: number;
  scoreStability: number;
  failedChecks: string[];
  reasons: string[];
  nextAction: string;
}

export interface NoEdgeLedgerArtifact {
  generatedAt: string;
  runId: string;
  count: number;
  noEdgeCount: number;
  blockedCount: number;
  needsMoreDataCount: number;
  promotableCount: number;
  blockedStrategies: SupportedStrategyId[];
  nonPromotableStrategies: SupportedStrategyId[];
  learningSummary: string[];
  entries: NoEdgeLedgerEntry[];
}

export interface BuildNoEdgeLedgerInput {
  generatedAt: string;
  runId: string;
  profiles: WalkforwardProfileResult[];
  gatesByProfileId: Map<string, PromotionGateResult>;
  strategiesByProfileId: Map<string, SupportedStrategyId[]>;
}

export function noEdgeLedgerLatestPath(env: NodeJS.ProcessEnv = process.env): string {
  return resolve(env.BILL_NO_EDGE_LEDGER_PATH ?? ".rumbling-hedge/research/no-edge-ledger/latest.json");
}

export function noEdgeLedgerHistoryPath(env: NodeJS.ProcessEnv = process.env): string {
  return resolve(env.BILL_NO_EDGE_LEDGER_HISTORY_PATH ?? ".rumbling-hedge/research/no-edge-ledger/history.jsonl");
}

function round4(value: number): number {
  return Number(value.toFixed(4));
}

function unique<T>(values: T[]): T[] {
  return Array.from(new Set(values));
}

function classifyProfile(profile: WalkforwardProfileResult, gate: PromotionGateResult | undefined): {
  verdict: NoEdgeVerdict;
  reasons: string[];
  nextAction: string;
} {
  const reasons = gate?.reasons ?? [];
  const testTrades = profile.testSummary.totalTrades;
  const netR = profile.testSummary.netTotalR;
  const expectancy = profile.testSummary.tradeQuality.expectancyR;

  if (gate?.ready) {
    return {
      verdict: "promotable",
      reasons: ["All promotion checks passed."],
      nextAction: "Eligible for paper-only promotion sizing review."
    };
  }

  if (testTrades < 8) {
    return {
      verdict: "needs-more-data",
      reasons: unique(["Out-of-sample sample size is too small.", ...reasons]),
      nextAction: "Keep researching, but do not conclude edge until more OOS trades exist."
    };
  }

  if (netR <= 0 || expectancy <= 0) {
    return {
      verdict: "no-edge",
      reasons: unique([
        ...(netR <= 0 ? ["OOS net R is not positive."] : []),
        ...(expectancy <= 0 ? ["OOS per-trade expectancy is not positive."] : []),
        ...reasons
      ]),
      nextAction: "Do not re-promote this profile without a materially different rule, regime filter, or dataset."
    };
  }

  return {
    verdict: "blocked",
    reasons: unique(reasons.length > 0 ? reasons : ["Promotion gate failed despite positive OOS headline metrics."]),
    nextAction: "Keep as research-only; fix failed gate before paper/demo routing."
  };
}

function summarizeLearning(entries: NoEdgeLedgerEntry[]): string[] {
  const noEdge = entries.filter((entry) => entry.verdict === "no-edge");
  const needsData = entries.filter((entry) => entry.verdict === "needs-more-data");
  const blocked = entries.filter((entry) => entry.verdict === "blocked");
  const promotable = entries.filter((entry) => entry.verdict === "promotable");
  const worst = [...entries]
    .sort((left, right) => left.testExpectancyR - right.testExpectancyR || left.testNetR - right.testNetR)
    .slice(0, 3)
    .map((entry) => `${entry.profileId}: ${entry.verdict}, expectancy ${entry.testExpectancyR}R, net ${entry.testNetR}R`);

  return [
    `profiles=${entries.length}, promotable=${promotable.length}, noEdge=${noEdge.length}, blocked=${blocked.length}, needsMoreData=${needsData.length}`,
    ...(worst.length > 0 ? [`weakest tested profiles: ${worst.join("; ")}`] : []),
    "Agents must treat no-edge entries as negative evidence; research can revisit only with new rules, data, or market regime."
  ];
}

export function buildNoEdgeLedger(input: BuildNoEdgeLedgerInput): NoEdgeLedgerArtifact {
  const entries = input.profiles.map((profile): NoEdgeLedgerEntry => {
    const gate = input.gatesByProfileId.get(profile.profileId);
    const classified = classifyProfile(profile, gate);
    const strategies = input.strategiesByProfileId.get(profile.profileId) ?? [];
    return {
      profileId: profile.profileId,
      strategies,
      verdict: classified.verdict,
      status: classified.verdict === "promotable" ? "candidate" : "research-only",
      testTrades: profile.testSummary.totalTrades,
      testNetR: round4(profile.testSummary.netTotalR),
      testExpectancyR: round4(profile.testSummary.tradeQuality.expectancyR),
      maxDrawdownR: round4(profile.testSummary.maxDrawdownR),
      scoreStability: round4(profile.scoreStability),
      failedChecks: gate?.checks.filter((check) => !check.passed).map((check) => check.name) ?? [],
      reasons: classified.reasons,
      nextAction: classified.nextAction
    };
  });

  const nonPromotableStrategies = unique(
    entries
      .filter((entry) => entry.verdict !== "promotable")
      .flatMap((entry) => entry.strategies)
  );

  // Auto-block SKELETON strategies — names without implementation
  const skeletonStrategies = entries
    .flatMap((entry) => entry.strategies)
    .filter((s) => getClassification(s) === "SKELETON");
  const allBlockedStrategies = unique([
    ...entries
      .filter((entry) => entry.verdict === "no-edge")
      .flatMap((entry) => entry.strategies),
    ...skeletonStrategies
  ]);

  return {
    generatedAt: input.generatedAt,
    runId: input.runId,
    count: entries.length,
    noEdgeCount: entries.filter((entry) => entry.verdict === "no-edge").length,
    blockedCount: entries.filter((entry) => entry.verdict === "blocked").length,
    needsMoreDataCount: entries.filter((entry) => entry.verdict === "needs-more-data").length,
    promotableCount: entries.filter((entry) => entry.verdict === "promotable").length,
    blockedStrategies: allBlockedStrategies,
    nonPromotableStrategies,
    learningSummary: summarizeLearning(entries),
    entries
  };
}

export function mergeNoEdgeLedgers(args: {
  previous: NoEdgeLedgerArtifact | null;
  current: NoEdgeLedgerArtifact;
}): NoEdgeLedgerArtifact {
  if (!args.previous) {
    return args.current;
  }

  const entriesByProfile = new Map<string, NoEdgeLedgerEntry>();
  for (const entry of args.previous.entries) {
    entriesByProfile.set(entry.profileId, entry);
  }
  for (const entry of args.current.entries) {
    entriesByProfile.set(entry.profileId, entry);
  }
  const entries = [...entriesByProfile.values()]
    .sort((left, right) => left.profileId.localeCompare(right.profileId));
  const blockedStrategies = unique(
    entries
      .filter((entry) => entry.verdict === "no-edge")
      .flatMap((entry) => entry.strategies)
  );
  const nonPromotableStrategies = unique(
    entries
      .filter((entry) => entry.verdict !== "promotable")
      .flatMap((entry) => entry.strategies)
  );

  return {
    generatedAt: args.current.generatedAt,
    runId: args.current.runId,
    count: entries.length,
    noEdgeCount: entries.filter((entry) => entry.verdict === "no-edge").length,
    blockedCount: entries.filter((entry) => entry.verdict === "blocked").length,
    needsMoreDataCount: entries.filter((entry) => entry.verdict === "needs-more-data").length,
    promotableCount: entries.filter((entry) => entry.verdict === "promotable").length,
    blockedStrategies,
    nonPromotableStrategies,
    learningSummary: summarizeLearning(entries),
    entries
  };
}

export async function writeNoEdgeLedger(
  artifact: NoEdgeLedgerArtifact,
  options: {
    latestPath?: string;
    historyPath?: string;
  } = {}
): Promise<{ latestPath: string; historyPath: string }> {
  const latestPath = resolve(options.latestPath ?? noEdgeLedgerLatestPath());
  const historyPath = resolve(options.historyPath ?? noEdgeLedgerHistoryPath());
  await mkdir(dirname(latestPath), { recursive: true });
  await mkdir(dirname(historyPath), { recursive: true });
  await writeFile(latestPath, `${JSON.stringify(artifact, null, 2)}\n`, "utf8");
  await appendFile(historyPath, `${JSON.stringify(artifact)}\n`, "utf8");
  return { latestPath, historyPath };
}

export async function loadLatestNoEdgeLedger(path: string = noEdgeLedgerLatestPath()): Promise<NoEdgeLedgerArtifact | null> {
  try {
    return JSON.parse(await readFile(path, "utf8")) as NoEdgeLedgerArtifact;
  } catch {
    return null;
  }
}
