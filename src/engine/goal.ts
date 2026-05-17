import { mkdir, readFile, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { buildCompetitiveReadinessReport, type CompetitiveReadinessReport } from "./competitiveReadiness.js";
import { buildStrategyZooAudit, type StrategyZooAuditReport } from "./strategyZooAudit.js";
import { writeLiveReadinessGate, type LiveReadinessGateReport } from "./liveReadinessGate.js";
import { buildResearchFabricReport, type ResearchFabricReport } from "./researchFabric.js";

export type GoalStage = "research" | "demo-shadow" | "demo-execution" | "live-blocked";

export interface GoalGap {
  id: string;
  stage: GoalStage;
  severity: "blocker" | "warning" | "task";
  summary: string;
  closeWith: string;
}

export interface GoalReport {
  command: "goal";
  generatedAt: string;
  outputPath: string;
  posture: "live-blocked" | "demo-blocked" | "demo-shadow-ready" | "demo-execution-ready";
  demoCanBeNext: boolean;
  liveCanBeNext: boolean;
  noOrdersSubmitted: true;
  artifacts: {
    researchFabric: string;
    liveReadinessGate: string;
    competitiveReadiness: string;
    propFirmEdgeMatrix: string;
    strategyZooAudit: string;
  };
  selectedBase: string | null;
  readiness: {
    liveGateReadyForLive: boolean;
    liveGateReadyForDemoExpansion: boolean;
    portfolioScore: number;
    strongestLanes: Array<{ lane: string; status: string; score: number; blockers: string[] }>;
  };
  gaps: GoalGap[];
  nextDemoSteps: string[];
  nextLiveSteps: string[];
  canonicalRules: string[];
}

const DEFAULT_OUTPUT = ".rumbling-hedge/state/goal.latest.json";

async function readJsonSafe<T>(path: string): Promise<T | null> {
  try {
    return JSON.parse(await readFile(path, "utf8")) as T;
  } catch {
    return null;
  }
}

function addUniqueGap(gaps: GoalGap[], gap: GoalGap): void {
  if (gaps.some((existing) => existing.id === gap.id)) return;
  gaps.push(gap);
}

function liveGateGaps(liveGate: LiveReadinessGateReport): GoalGap[] {
  return liveGate.checks
    .filter((item) => !item.passed)
    .map((item) => ({
      id: `live-gate-${item.name}`,
      stage: item.name.includes("demo") ? "demo-execution" : "live-blocked",
      severity: item.severity,
      summary: item.summary,
      closeWith: item.name.includes("rolling-oos")
        ? "Rerun strategy-factory/rolling OOS on the selected normalized base until deployable windows meet the gate."
        : item.name.includes("source-clean")
          ? "Commit or intentionally park source changes before promotion; dirty research is allowed, dirty live source is not."
          : item.name.includes("strategy")
            ? "Produce a current strategy-factory artifact with walk-forward and stressed live-readiness passing."
            : "Refresh the named artifact or clear the named operational gate, then rerun npm run goal."
    }));
}

function researchFabricGaps(fabric: ResearchFabricReport): GoalGap[] {
  const gaps: GoalGap[] = [];
  for (const blocker of fabric.integration.blockers) {
    const text = String(blocker);
    if (/DOM/i.test(text)) {
      addUniqueGap(gaps, {
        id: "dom-real-depth-tape",
        stage: "research",
        severity: "blocker",
        summary: "DOM is still proxy evidence, not production order-book evidence.",
        closeWith: "Move DOM capture into repo state and record symbol, venue/account, ladder depth, bid/ask sizes, tape, and replay window."
      });
    } else if (/TimesFM/i.test(text)) {
      addUniqueGap(gaps, {
        id: "timesfm-blocked",
        stage: "research",
        severity: "task",
        summary: text,
        closeWith: "Cache weights under a stable path and only run TimesFM when ram-guard permits the heavy slot."
      });
    } else if (/contradiction|ORB|deployable\/SILVER/i.test(text)) {
      addUniqueGap(gaps, {
        id: "orb-contradiction",
        stage: "live-blocked",
        severity: "blocker",
        summary: "Loose ORB deployability notes contradict the current gates.",
        closeWith: "Keep ORB non-promotable until current factory/live-readiness artifacts show deployable rolling OOS windows."
      });
    } else if (/dirty sibling worktree/i.test(text)) {
      addUniqueGap(gaps, {
        id: "sibling-worktree-selective-intake",
        stage: "research",
        severity: "task",
        summary: text,
        closeWith: "Cherry-pick only governance/data modules from hedge-goal-live, then rerun typecheck and gates."
      });
    }
  }
  return gaps;
}

function competitiveGaps(report: CompetitiveReadinessReport): GoalGap[] {
  const gaps: GoalGap[] = [];
  for (const lane of report.lanes) {
    for (const blocker of lane.blockers) {
      addUniqueGap(gaps, {
        id: `lane-${lane.lane}-${blocker}`,
        stage: lane.lane === "futures-core" ? "demo-execution" : "research",
        severity: blocker.includes("unsafe-live") || blocker.includes("missing-positive-oos") ? "blocker" : "task",
        summary: `${lane.lane}: ${blocker}`,
        closeWith: lane.nextActions[0] ?? "Close the lane-specific blocker and rerun competitive-readiness."
      });
    }
  }
  return gaps;
}

function propFirmMatrixGaps(report: any | null): GoalGap[] {
  if (!report) {
    return [{
      id: "prop-firm-edge-matrix-missing",
      stage: "demo-execution",
      severity: "blocker",
      summary: "Prop-firm edge matrix is missing.",
      closeWith: "Run alpha-lab across the available timeframes, then run npm run bill:prop-firm-edge-matrix."
    }];
  }
  const gaps: GoalGap[] = [];
  if (report.posture !== "demo-payout-candidate") {
    addUniqueGap(gaps, {
      id: "prop-firm-no-demo-payout-candidate",
      stage: "demo-execution",
      severity: "blocker",
      summary: "No prop-firm payout lane survived the multi-timeframe edge matrix.",
      closeWith: "Keep lanes in research/shadow until worst purged fold, regime validation, and bracket replay pass."
    });
  }
  for (const blocker of report.blockers ?? []) {
    if (String(blocker).includes("live execution")) continue;
    addUniqueGap(gaps, {
      id: `prop-firm-${String(blocker).replace(/[^a-z0-9]+/gi, "-").toLowerCase()}`,
      stage: "demo-execution",
      severity: "blocker",
      summary: `Prop-firm matrix: ${blocker}`,
      closeWith: "Close the matrix blocker without weakening evidence thresholds, then rerun npm run goal."
    });
  }
  return gaps;
}

function strategyZooGaps(report: StrategyZooAuditReport | null): GoalGap[] {
  if (!report) {
    return [{
      id: "strategy-zoo-audit-missing",
      stage: "research",
      severity: "task",
      summary: "Strategy zoo audit is missing.",
      closeWith: "Run npm run bill:strategy-zoo-audit before retesting individual strategy families."
    }];
  }
  const gaps: GoalGap[] = [];
  const skeletons = report.counts["phase:skeleton"] ?? 0;
  if (skeletons > 0) {
    addUniqueGap(gaps, {
      id: "strategy-zoo-skeletons",
      stage: "research",
      severity: "task",
      summary: `${skeletons} strategy ids are classified but not registered in the runtime catalog.`,
      closeWith: "Either implement/register the skeleton ids or remove them from the active supported-strategy list before OOS budget is spent."
    });
  }
  if (report.shortlist.length === 0) {
    addUniqueGap(gaps, {
      id: "strategy-zoo-no-shortlist",
      stage: "research",
      severity: "task",
      summary: "No strategy-zoo item has enough linked matrix evidence for prioritized retest.",
      closeWith: "Use alpha-lab/matrix features to create explicit strategy mappings before expensive walk-forward sweeps."
    });
  }
  return gaps;
}

export async function buildGoalReport(args: {
  baseDir?: string;
  outputPath?: string;
  env?: NodeJS.ProcessEnv;
  now?: () => string;
} = {}): Promise<GoalReport> {
  const baseDir = resolve(args.baseDir ?? process.cwd());
  const generatedAt = args.now?.() ?? new Date().toISOString();
  const outputPath = resolve(baseDir, args.outputPath ?? DEFAULT_OUTPUT);
  const env = args.env ?? process.env;

  const [fabric, liveGate, competitive, strategyZoo] = await Promise.all([
    buildResearchFabricReport({ outputPath: resolve(baseDir, ".rumbling-hedge/state/research-fabric.latest.json") }),
    writeLiveReadinessGate({ baseDir, env, now: () => generatedAt }),
    buildCompetitiveReadinessReport({ baseDir, env, now: () => generatedAt }),
    buildStrategyZooAudit({ outputPath: resolve(baseDir, ".rumbling-hedge/state/strategy-zoo-audit.latest.json"), now: () => generatedAt })
  ]);
  const propFirmEdgeMatrix = await readJsonSafe<any>(resolve(baseDir, ".rumbling-hedge/state/prop-firm-edge-matrix.latest.json"));

  const futuresDemo = await readJsonSafe<any>(resolve(baseDir, ".rumbling-hedge/state/futures-demo.latest.json"));
  const hasNonFallbackDemo = Number(futuresDemo?.execution?.submittedCount ?? 0) > 0
    && !(futuresDemo?.execution?.submitted ?? []).some((entry: any) => String(entry?.signal?.strategyId ?? entry?.strategyId ?? "").includes("demo-fallback"));

  const gaps = [
    ...liveGateGaps(liveGate),
    ...researchFabricGaps(fabric),
    ...competitiveGaps(competitive),
    ...strategyZooGaps(strategyZoo),
    ...propFirmMatrixGaps(propFirmEdgeMatrix)
  ];
  if (!hasNonFallbackDemo) {
    addUniqueGap(gaps, {
      id: "demo-fill-evidence",
      stage: "demo-execution",
      severity: "blocker",
      summary: "No recent non-fallback demo fill evidence is available.",
      closeWith: "Run paper/demo shadow lanes first; require replayable non-synthetic demo fills before widening execution."
    });
  }

  const liveBlockers = gaps.filter((gap) => gap.severity === "blocker" && gap.stage === "live-blocked");
  const demoBlockers = gaps.filter((gap) => gap.severity === "blocker" && gap.stage === "demo-execution");
  const demoCanBeNext = liveGate.readyForDemoExpansion && demoBlockers.length === 0;
  const liveCanBeNext = liveGate.readyForLive && liveBlockers.length === 0 && competitive.liveExecutionAllowed;
  const posture = liveCanBeNext
    ? "demo-execution-ready"
    : demoCanBeNext
      ? "demo-shadow-ready"
      : demoBlockers.length > 0
        ? "demo-blocked"
        : "live-blocked";

  const strongestLanes = [...competitive.lanes]
    .sort((a, b) => b.score - a.score)
    .slice(0, 3)
    .map((lane) => ({ lane: lane.lane, status: lane.status, score: lane.score, blockers: lane.blockers }));

  const report: GoalReport = {
    command: "goal",
    generatedAt,
    outputPath,
    posture,
    demoCanBeNext,
    liveCanBeNext,
    noOrdersSubmitted: true,
    artifacts: {
      researchFabric: ".rumbling-hedge/state/research-fabric.latest.json",
      liveReadinessGate: ".rumbling-hedge/state/live-readiness-gate.latest.json",
      competitiveReadiness: ".rumbling-hedge/state/competitive-readiness.latest.json",
      propFirmEdgeMatrix: ".rumbling-hedge/state/prop-firm-edge-matrix.latest.json",
      strategyZooAudit: ".rumbling-hedge/state/strategy-zoo-audit.latest.json"
    },
    selectedBase: fabric.data.selectedBase,
    readiness: {
      liveGateReadyForLive: liveGate.readyForLive,
      liveGateReadyForDemoExpansion: liveGate.readyForDemoExpansion,
      portfolioScore: competitive.portfolioScore,
      strongestLanes
    },
    gaps,
    nextDemoSteps: demoCanBeNext
      ? [
          "Run topstep-demo-preflight with read-only/account locks verified.",
          "Route only approved demo lanes with one-contract max, bracket required, and no fallback signals.",
          "Append every fill to the replayable journal and rerun goal before widening."
        ]
      : gaps
          .filter((gap) => gap.stage === "demo-execution" && gap.severity === "blocker")
          .slice(0, 5)
          .map((gap) => gap.closeWith),
    nextLiveSteps: liveCanBeNext
      ? ["Require explicit operator approval, confirm account lock, then run live preflight in read-only verification before any order route."]
      : [
          "Do not route live futures or prediction-market capital.",
          "Close live-readiness blockers with current artifacts, not notes.",
          "Demand positive OOS after costs, paper/demo fill evidence, and clean source before live approval."
        ],
    canonicalRules: [
      "Notes and research claims cannot override gates.",
      "Demo expansion requires current readiness artifacts and non-fallback routing evidence.",
      "Live remains prohibited until live-readiness, competitive-readiness, OOS, source, and execution gates all agree.",
      "This command submits no orders."
    ]
  };

  await mkdir(dirname(outputPath), { recursive: true });
  await writeFile(outputPath, `${JSON.stringify(report, null, 2)}\n`, "utf8");
  return report;
}
