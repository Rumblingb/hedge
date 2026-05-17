import { existsSync } from "node:fs";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import type { AlphaCandidate, AlphaLabReport } from "./alphaLab.js";
import { TOPSTEP_50K_PARAMETERS } from "./propFirmPayout.js";

export interface PropFirmEdgeMatrixInput {
  label: string;
  timeframe: "5m" | "10m" | "15m" | "30m" | "1h" | "4h" | "1d" | string;
  path: string;
  present: boolean;
  bars?: number;
  symbols?: string[];
  blockers?: string[];
  topCandidates?: AlphaCandidate[];
}

export interface PropFirmEdgeLane {
  laneId: string;
  symbol: string;
  timeframe: string;
  feature: string;
  horizonBars: number;
  direction: "long" | "short";
  score: number;
  status: "reject" | "research" | "shadow-demo-candidate" | "demo-payout-candidate";
  expectedDailyTargetDollars: number;
  dailyLossLockDollars: number;
  maxContracts: number;
  evidence: {
    observations: number;
    testIc: number;
    cvPositiveFoldRate: number;
    cvMinNetEdgePct: number;
    netEdgePct: number;
    regimePassRate: number;
  };
  blockers: string[];
  nextValidation: string[];
}

export interface OptionsContextSummary {
  path: string;
  present: boolean;
  underlyings: string[];
  snapshots: number;
  note: string;
}

export interface PropFirmEdgeMatrixReport {
  command: "prop-firm-edge-matrix";
  generatedAt: string;
  outputPath: string;
  posture: "research-only" | "shadow-demo-ready" | "demo-payout-candidate";
  account: typeof TOPSTEP_50K_PARAMETERS;
  inputs: PropFirmEdgeMatrixInput[];
  optionsContext: OptionsContextSummary;
  lanes: PropFirmEdgeLane[];
  blockers: string[];
  operatingRules: string[];
  nextActions: string[];
}

const DEFAULT_OUTPUT = ".rumbling-hedge/state/prop-firm-edge-matrix.latest.json";

async function readJsonSafe<T>(path: string): Promise<T | null> {
  try {
    return JSON.parse(await readFile(path, "utf8")) as T;
  } catch {
    return null;
  }
}

function scoreCandidate(candidate: AlphaCandidate, timeframe: string): number {
  const ic = Math.min(1, Math.abs(candidate.testIc) / 0.08);
  const stability = Math.max(0, Math.min(1, candidate.stability));
  const folds = Math.max(0, Math.min(1, candidate.cvPositiveFoldRate));
  const edge = Math.max(0, Math.min(1, candidate.netEdgePct / 0.035));
  const regimePassRate = candidate.regimeValidation.length === 0
    ? 0
    : candidate.regimeValidation.filter((item) => item.verdict === "pass").length / candidate.regimeValidation.length;
  const sample = Math.max(0, Math.min(1, candidate.observations / 1200));
  const timeframeWeight = ["15m", "30m", "1h"].includes(timeframe) ? 1 : ["5m", "4h"].includes(timeframe) ? 0.92 : 0.82;
  const raw = (
    ic * 0.22
    + stability * 0.18
    + folds * 0.18
    + edge * 0.18
    + regimePassRate * 0.14
    + sample * 0.10
  ) * timeframeWeight;
  return Number(Math.max(0, Math.min(1, raw)).toFixed(4));
}

function laneStatus(score: number, blockers: string[]): PropFirmEdgeLane["status"] {
  if (blockers.length > 0 || score < 0.45) return "reject";
  if (score >= 0.72) return "demo-payout-candidate";
  if (score >= 0.58) return "shadow-demo-candidate";
  return "research";
}

function candidateBlockers(candidate: AlphaCandidate): string[] {
  return [
    ...candidate.blockers,
    ...(candidate.verdict === "reject" ? ["alpha-lab-rejected"] : []),
    ...(candidate.observations < 500 ? ["thin-observation-count"] : []),
    ...(candidate.cvPositiveFoldRate < 0.5 ? ["unstable-purged-folds"] : []),
    ...(candidate.cvMinNetEdgePct <= 0 ? ["negative-worst-fold-net-edge"] : []),
    ...(candidate.regimeValidation.filter((item) => item.verdict === "pass").length < 2 ? ["insufficient-regime-coverage"] : [])
  ];
}

function toLane(input: PropFirmEdgeMatrixInput, candidate: AlphaCandidate): PropFirmEdgeLane {
  const blockers = Array.from(new Set(candidateBlockers(candidate)));
  const score = scoreCandidate(candidate, input.timeframe);
  const status = laneStatus(score, blockers);
  const regimePassRate = candidate.regimeValidation.length === 0
    ? 0
    : candidate.regimeValidation.filter((item) => item.verdict === "pass").length / candidate.regimeValidation.length;
  const payoutCandidate = status === "demo-payout-candidate";
  return {
    laneId: `${candidate.symbol}-${input.timeframe}-${candidate.feature}-${candidate.horizonBars}-${candidate.direction}`,
    symbol: candidate.symbol,
    timeframe: input.timeframe,
    feature: candidate.feature,
    horizonBars: candidate.horizonBars,
    direction: candidate.direction,
    score,
    status,
    expectedDailyTargetDollars: payoutCandidate ? 300 : status === "shadow-demo-candidate" ? 150 : 0,
    dailyLossLockDollars: payoutCandidate ? 180 : 100,
    maxContracts: payoutCandidate ? 1 : 0,
    evidence: {
      observations: candidate.observations,
      testIc: Number(candidate.testIc.toFixed(6)),
      cvPositiveFoldRate: Number(candidate.cvPositiveFoldRate.toFixed(4)),
      cvMinNetEdgePct: Number(candidate.cvMinNetEdgePct.toFixed(6)),
      netEdgePct: Number(candidate.netEdgePct.toFixed(6)),
      regimePassRate: Number(regimePassRate.toFixed(4))
    },
    blockers,
    nextValidation: [
      "Replay against bracket-order assumptions with stop, target, and end-of-session flat rule.",
      "Require at least 20 non-synthetic paper/demo journaled trades before payout sizing.",
      "Recompute after fees/slippage and reject if worst purged fold turns negative."
    ]
  };
}

async function summarizeOptionsContext(path: string): Promise<OptionsContextSummary> {
  const abs = resolve(path);
  const report = await readJsonSafe<any>(abs);
  if (!report) {
    return {
      path: abs,
      present: false,
      underlyings: [],
      snapshots: 0,
      note: "Options context missing; options may gate risk, but cannot drive execution."
    };
  }
  const underlyings = Array.from(new Set([
    ...(Array.isArray(report.underlyings) ? report.underlyings.map(String) : []),
    ...(Array.isArray(report.snapshots) ? report.snapshots.map((item: any) => String(item?.underlying ?? "")).filter(Boolean) : [])
  ])).sort();
  return {
    path: abs,
    present: true,
    underlyings,
    snapshots: Array.isArray(report.snapshots) ? report.snapshots.length : underlyings.length,
    note: "Use options surface as a risk/regime gate for index futures until an options paper router exists."
  };
}

export async function buildPropFirmEdgeMatrix(args: {
  inputs: Array<{ label: string; timeframe: string; path: string }>;
  outputPath?: string;
  optionsContextPath?: string;
  now?: () => string;
}): Promise<PropFirmEdgeMatrixReport> {
  const outputPath = resolve(args.outputPath ?? DEFAULT_OUTPUT);
  const inputs: PropFirmEdgeMatrixInput[] = [];
  const lanes: PropFirmEdgeLane[] = [];

  for (const input of args.inputs) {
    const path = resolve(input.path);
    const report = await readJsonSafe<AlphaLabReport>(path);
    if (!report || !existsSync(path)) {
      inputs.push({ ...input, path, present: false, blockers: ["alpha-lab-report-missing"] });
      continue;
    }
    const row: PropFirmEdgeMatrixInput = {
      ...input,
      timeframe: input.timeframe,
      path,
      present: true,
      bars: report.bars,
      symbols: report.symbols,
      blockers: report.blockers,
      topCandidates: report.topCandidates.slice(0, 10)
    };
    inputs.push(row);
    for (const candidate of report.topCandidates.slice(0, 12)) {
      lanes.push(toLane(row, candidate));
    }
  }

  const ranked = lanes.sort((left, right) => right.score - left.score).slice(0, 30);
  const demoLanes = ranked.filter((lane) => lane.status === "demo-payout-candidate");
  const shadowLanes = ranked.filter((lane) => lane.status === "shadow-demo-candidate");
  const optionsContext = await summarizeOptionsContext(args.optionsContextPath ?? ".rumbling-hedge/state/options-complete-arsenal.json");
  const blockers = [
    ...(inputs.every((input) => !input.present) ? ["no-alpha-lab-inputs-present"] : []),
    ...(demoLanes.length === 0 ? ["no-demo-payout-candidate-survived-matrix"] : []),
    ...(optionsContext.present ? [] : ["options-context-missing"]),
    "live execution still requires clean source, current OOS gates, and journaled demo fills"
  ];
  const posture = demoLanes.length > 0 && blockers.length <= 1
    ? "demo-payout-candidate"
    : shadowLanes.length > 0
      ? "shadow-demo-ready"
      : "research-only";

  const report: PropFirmEdgeMatrixReport = {
    command: "prop-firm-edge-matrix",
    generatedAt: args.now?.() ?? new Date().toISOString(),
    outputPath,
    posture,
    account: TOPSTEP_50K_PARAMETERS,
    inputs,
    optionsContext,
    lanes: ranked,
    blockers,
    operatingRules: [
      "Prop-firm payout work starts with NQ/MNQ; all other symbols are context until they prove fillable edge.",
      "No lane can execute live from this matrix alone; it must pass current strategy-factory, live-readiness, and demo-fill gates.",
      "Challenge mode: one NQ max, three trades/day max, daily loss lock below 450 USD, no recovery trading.",
      "Funded mode: prefer MNQ payout defense and consistency days over fast combine-style sizing.",
      "Options signals are regime/risk gates until an options paper execution router exists."
    ],
    nextActions: demoLanes.length > 0
      ? [
          "Convert the top demo-payout candidate into a named strategy profile with bracket-order replay.",
          "Run walkforward and rolling OOS on the same timeframe, then route shadow demo only if gates pass.",
          "Journal 20 non-synthetic demo fills before considering payout sizing."
        ]
      : [
          "Keep alpha candidates in research/shadow; do not route orders.",
          "Run alpha-lab across more current 5m/15m/30m/60m data and require positive worst-fold net edge.",
          "Use options and macro context as filters, not standalone prop-firm execution."
        ]
  };

  await mkdir(dirname(outputPath), { recursive: true });
  await writeFile(outputPath, `${JSON.stringify(report, null, 2)}\n`, "utf8");
  return report;
}
