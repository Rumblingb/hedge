import { mkdir, readFile, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import type { CapitalAllocatorReport, LaneBudget } from "./capitalAllocator.js";
import type { CompetitiveReadinessReport } from "./competitiveReadiness.js";
import type { LiveReadinessGateReport } from "./liveReadinessGate.js";

export interface CompoundEdgeLane {
  lane: "prediction-markets" | "futures-prop" | "long-only-compounder" | "reserve";
  status: "locked" | "research" | "paper-demo" | "compound";
  budget: number;
  maxDailyLoss: number;
  maxSingleTradeRisk: number;
  score: number;
  blockers: string[];
  mandate: string[];
}

export interface EdgeCompoundingControllerReport {
  command: "edge-compounding-controller";
  generatedAt: string;
  status: "blocked" | "research-only" | "paper-demo-ready";
  liveAllowed: false;
  demoExpansionAllowed: boolean;
  bankroll: number;
  currency: string;
  deployablePaperBudget: number;
  reserveBudget: number;
  lanes: CompoundEdgeLane[];
  compoundingRules: string[];
  hermesMandate: {
    allowed: string[];
    forbidden: string[];
  };
  runbook: string[];
  blockers: string[];
  paths: {
    outputPath: string;
    allocatorPath: string;
    liveReadinessGatePath: string;
    competitiveReadinessPath: string;
    twoTrackReadinessPath: string;
  };
}

const DEFAULT_OUTPUT_PATH = ".rumbling-hedge/state/edge-compounding-controller.latest.json";

async function readJsonSafe<T>(path: string): Promise<T | null> {
  try {
    return JSON.parse(await readFile(path, "utf8")) as T;
  } catch {
    return null;
  }
}

function round(value: number): number {
  return Number(value.toFixed(2));
}

function unique(values: string[]): string[] {
  return [...new Set(values.filter((value) => value.trim().length > 0))];
}

function laneBudget(
  allocator: CapitalAllocatorReport | null,
  lane: "prediction-markets" | "futures-prop"
): LaneBudget | null {
  return allocator?.laneBudgets.find((entry) => entry.lane === lane) ?? null;
}

function readinessScore(
  competitive: CompetitiveReadinessReport | null,
  lane: "prediction" | "futures-core" | "long-only-compounder"
): number {
  return competitive?.lanes.find((entry) => entry.lane === lane)?.score ?? 0;
}

function competitiveBlockers(
  competitive: CompetitiveReadinessReport | null,
  lane: "prediction" | "futures-core" | "long-only-compounder"
): string[] {
  return competitive?.lanes.find((entry) => entry.lane === lane)?.blockers ?? [];
}

function buildLane(args: {
  lane: CompoundEdgeLane["lane"];
  status: CompoundEdgeLane["status"];
  budget?: LaneBudget | null;
  score: number;
  blockers: string[];
  mandate: string[];
}): CompoundEdgeLane {
  return {
    lane: args.lane,
    status: args.status,
    budget: round(args.budget?.budget ?? 0),
    maxDailyLoss: round(args.budget?.maxDailyLoss ?? 0),
    maxSingleTradeRisk: round(args.budget?.maxSingleTradeRisk ?? 0),
    score: args.score,
    blockers: unique(args.blockers),
    mandate: args.mandate
  };
}

export async function buildEdgeCompoundingController(args: {
  baseDir?: string;
  env?: NodeJS.ProcessEnv;
  now?: () => string;
  outputPath?: string;
  allocatorPath?: string;
  liveReadinessGatePath?: string;
  competitiveReadinessPath?: string;
  twoTrackReadinessPath?: string;
} = {}): Promise<EdgeCompoundingControllerReport> {
  const baseDir = resolve(args.baseDir ?? process.cwd());
  const generatedAt = args.now?.() ?? new Date().toISOString();
  const outputPath = resolve(baseDir, args.outputPath ?? DEFAULT_OUTPUT_PATH);
  const allocatorPath = resolve(baseDir, args.allocatorPath ?? ".rumbling-hedge/state/capital-allocator.latest.json");
  const liveReadinessGatePath = resolve(baseDir, args.liveReadinessGatePath ?? ".rumbling-hedge/state/live-readiness-gate.latest.json");
  const competitiveReadinessPath = resolve(baseDir, args.competitiveReadinessPath ?? ".rumbling-hedge/state/competitive-readiness.latest.json");
  const twoTrackReadinessPath = resolve(baseDir, args.twoTrackReadinessPath ?? ".rumbling-hedge/state/two-track-readiness.latest.json");

  const [allocator, liveGate, competitive, twoTrack] = await Promise.all([
    readJsonSafe<CapitalAllocatorReport>(allocatorPath),
    readJsonSafe<LiveReadinessGateReport>(liveReadinessGatePath),
    readJsonSafe<CompetitiveReadinessReport>(competitiveReadinessPath),
    readJsonSafe<any>(twoTrackReadinessPath)
  ]);

  const bankroll = round(allocator?.bankroll ?? Number(args.env?.BILL_FUND_BANKROLL ?? 100));
  const currency = allocator?.currency ?? args.env?.BILL_FUND_CURRENCY ?? args.env?.BILL_PREDICTION_BANKROLL_CURRENCY ?? "GBP";
  const predictionBudget = laneBudget(allocator, "prediction-markets");
  const futuresBudget = laneBudget(allocator, "futures-prop");
  const demoExpansionAllowed = liveGate?.readyForDemoExpansion === true && twoTrack?.demoExpansionAllowed === true;
  const allocatorReady = allocator?.status === "paper-budget-ready";

  const predictionStatus: CompoundEdgeLane["status"] =
    allocatorReady && predictionBudget?.status === "paper" && demoExpansionAllowed ? "paper-demo" : "research";
  const futuresStatus: CompoundEdgeLane["status"] =
    allocatorReady && futuresBudget?.status === "paper" && demoExpansionAllowed ? "paper-demo" : "research";
  const deployablePaperBudget = round(
    (predictionStatus === "paper-demo" ? predictionBudget?.budget ?? 0 : 0)
    + (futuresStatus === "paper-demo" ? futuresBudget?.budget ?? 0 : 0)
  );

  const blockers = unique([
    ...(!allocator ? ["missing capital allocator artifact"] : []),
    ...(!liveGate ? ["missing live-readiness gate artifact"] : []),
    ...(!competitive ? ["missing competitive-readiness artifact"] : []),
    ...(!twoTrack ? ["missing two-track readiness artifact"] : []),
    ...(allocator?.blockers ?? []),
    ...(liveGate?.blockers ?? []),
    ...(competitive?.globalBlockers ?? []),
    ...(twoTrack?.predictionMarkets?.blockers ?? []).map((item: string) => `prediction:${item}`),
    ...(twoTrack?.propFirms?.blockers ?? []).map((item: string) => `futures:${item}`)
  ]);

  const status: EdgeCompoundingControllerReport["status"] =
    deployablePaperBudget > 0 ? "paper-demo-ready" : blockers.length > 0 ? "blocked" : "research-only";

  const lanes: CompoundEdgeLane[] = [
    buildLane({
      lane: "prediction-markets",
      status: predictionStatus,
      budget: predictionBudget,
      score: readinessScore(competitive, "prediction"),
      blockers: [
        ...(predictionBudget?.status === "paper" ? [] : ["allocator has not assigned paper budget"]),
        ...competitiveBlockers(competitive, "prediction"),
        ...(twoTrack?.predictionMarkets?.blockers ?? [])
      ],
      mandate: [
        "Scan cross-venue and flow edges continuously, but place only paper fills until settlement-reviewed edge is proven.",
        "Increase stake ceilings only from realized resolved paper PnL and only after the allocator refreshes."
      ]
    }),
    buildLane({
      lane: "futures-prop",
      status: futuresStatus,
      budget: futuresBudget,
      score: readinessScore(competitive, "futures-core"),
      blockers: [
        ...(futuresBudget?.status === "paper" ? [] : ["allocator has not assigned futures demo budget"]),
        ...competitiveBlockers(competitive, "futures-core"),
        ...(twoTrack?.propFirms?.blockers ?? [])
      ],
      mandate: [
        "Run Topstep/ProjectX demo only when OOS, bracket, account, and daily-lock gates are green.",
        "Treat payout defense and rule compliance as alpha; no fallback or synthetic signal may route."
      ]
    }),
    buildLane({
      lane: "long-only-compounder",
      status: "locked",
      score: readinessScore(competitive, "long-only-compounder"),
      blockers: competitiveBlockers(competitive, "long-only-compounder"),
      mandate: [
        "Build rankings and research now; fund this sleeve only from proven surplus cashflow.",
        "Use it as the slow compounding sleeve, not as a rescue trade."
      ]
    }),
    {
      lane: "reserve",
      status: "compound",
      budget: round(Math.max(0, bankroll - deployablePaperBudget)),
      maxDailyLoss: 0,
      maxSingleTradeRisk: 0,
      score: 100,
      blockers: [],
      mandate: [
        "Preserve the bankroll first.",
        "Release capital only through refreshed gates and explicit founder live approval."
      ]
    }
  ];

  const report: EdgeCompoundingControllerReport = {
    command: "edge-compounding-controller",
    generatedAt,
    status,
    liveAllowed: false,
    demoExpansionAllowed,
    bankroll,
    currency,
    deployablePaperBudget,
    reserveBudget: round(Math.max(0, bankroll - deployablePaperBudget)),
    lanes,
    compoundingRules: [
      "Compound only positive realized net edge; paper/demo PnL can raise confidence but not live size.",
      "Allocate to the highest evidence lane first; idle capital stays reserve.",
      "Cut a lane back to research after a gate failure, max daily loss breach, stale artifact, or settlement mismatch.",
      "Long-only compounding is funded by surplus cashflow, not by weakening prediction or prop-firm risk limits."
    ],
    hermesMandate: {
      allowed: [
        "refresh evidence artifacts",
        "run paper/demo scans inside existing caps",
        "wake Bill workers on named blockers",
        "summarize promotion and capital-allocation deltas"
      ],
      forbidden: [
        "route live orders",
        "raise live or demo risk caps",
        "bypass promotion, live-readiness, or allocator gates",
        "treat LLM rationale as a sizing input"
      ]
    },
    runbook: [
      "npm run bill:prediction-review",
      "npm run bill:live-readiness-gate",
      "npm run bill:competitive-readiness",
      "npm run bill:cashflow-board",
      "npm run bill:capital-allocator",
      "npm run bill:compound-edges"
    ],
    blockers,
    paths: {
      outputPath,
      allocatorPath,
      liveReadinessGatePath,
      competitiveReadinessPath,
      twoTrackReadinessPath
    }
  };

  await mkdir(dirname(outputPath), { recursive: true });
  await writeFile(outputPath, `${JSON.stringify(report, null, 2)}\n`, "utf8");
  return report;
}
