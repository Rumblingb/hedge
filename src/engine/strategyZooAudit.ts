import { mkdir, readFile, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import {
  STRATEGY_CLASSIFICATION,
  SUPPORTED_STRATEGY_IDS,
  getClassification,
  isExecutable,
  isTestable,
  type Classification,
  type SupportedStrategyId
} from "../domain.js";
import { buildStrategyCatalog } from "../strategies/wctcEnsemble.js";

const DEFAULT_OUTPUT_PATH = ".rumbling-hedge/state/strategy-zoo-audit.latest.json";
const DEFAULT_PROP_MATRIX_PATH = ".rumbling-hedge/state/prop-firm-edge-matrix.latest.json";
const STRATEGY_FEATURE_MAP: Record<string, string[]> = {
  "donchian-breakout": ["range_pct"],
  "opening-stop-hunt": ["range_pct"],
  "orb-breakout": ["range_pct"],
  "regime-orb-breakout": ["range_pct", "rv_"],
  "volatility-regime": ["rv_"],
  "vol-scaled-breakout-momentum": ["range_pct", "volume_z", "rv_", "ret_"],
  "wq-alpha-012-rust": ["rv_", "volume_z"],
  "wq-alpha-009-rust": ["volume_z", "range_pct"],
  "wq-alpha-001-rust": ["ret_"],
  "ret-30-momentum": ["ret_30", "ret_15"],
  "short-term-reversal": ["ret_5", "ret_15"],
  "prop-momentum-scalp": ["volume_z", "ret_"],
  "prop-vwap-bounce": ["rv_", "range_pct"],
  "intraday-momentum": ["ret_", "volume_z"]
};

export interface StrategyZooAuditItem {
  strategyId: string;
  classification: Classification;
  registered: boolean;
  executable: boolean;
  testable: boolean;
  phase: "candidate-retest" | "incubate" | "quarantine" | "skeleton" | "execution-disabled";
  evidence: {
    propFirmLaneCount: number;
    bestPropFirmScore: number | null;
    bestPropFirmStatus: string | null;
    blockers: string[];
  };
  nextAction: string;
}

export interface StrategyZooAuditReport {
  command: "strategy-zoo-audit";
  generatedAt: string;
  outputPath: string;
  inputs: {
    propFirmMatrixPath: string;
    propFirmMatrixPresent: boolean;
  };
  counts: Record<string, number>;
  items: StrategyZooAuditItem[];
  shortlist: StrategyZooAuditItem[];
  rules: string[];
}

function round(value: number): number {
  return Number(value.toFixed(4));
}

async function readJsonSafe(path: string): Promise<any | null> {
  try {
    return JSON.parse(await readFile(path, "utf8"));
  } catch {
    return null;
  }
}

function strategyEvidence(strategyId: string, matrix: any): StrategyZooAuditItem["evidence"] {
  const lanes = Array.isArray(matrix?.lanes) ? matrix.lanes : [];
  const featureHints = STRATEGY_FEATURE_MAP[strategyId] ?? [];
  const matched = lanes.filter((lane: any) => {
    const laneId = String(lane?.laneId ?? "").toLowerCase();
    const feature = String(lane?.feature ?? "").toLowerCase();
    return laneId.includes(strategyId.toLowerCase())
      || featureHints.some((hint) => laneId.includes(hint.toLowerCase()) || feature.includes(hint.toLowerCase()));
  });
  const scored = matched
    .map((lane: any) => ({
      score: typeof lane?.score === "number" ? lane.score : null,
      status: String(lane?.status ?? "unknown"),
      blockers: Array.isArray(lane?.blockers) ? lane.blockers.map(String) : []
    }))
    .filter((lane: any) => lane.score !== null)
    .sort((left: any, right: any) => right.score - left.score);
  const best = scored[0];
  return {
    propFirmLaneCount: matched.length,
    bestPropFirmScore: best ? round(best.score) : null,
    bestPropFirmStatus: best?.status ?? null,
    blockers: [...new Set<string>(scored.flatMap((lane: any) => lane.blockers.map(String)))].slice(0, 8)
  };
}

function phaseFor(args: {
  classification: Classification;
  registered: boolean;
  evidence: StrategyZooAuditItem["evidence"];
}): StrategyZooAuditItem["phase"] {
  if (!args.registered) return "skeleton";
  if (args.classification === "QUARANTINED") return "quarantine";
  if (args.classification === "SKELETON") return "skeleton";
  if (args.classification === "GOLD" || args.classification === "SILVER") return "execution-disabled";
  if (args.evidence.bestPropFirmStatus === "research" || args.evidence.bestPropFirmScore !== null) return "candidate-retest";
  return "incubate";
}

function nextActionFor(item: Omit<StrategyZooAuditItem, "nextAction">): string {
  if (item.phase === "skeleton") return "Do not spend OOS budget until a registered implementation exists.";
  if (item.phase === "quarantine") return "Keep shadow-only; require a new independent filter and fresh OOS before retest.";
  if (item.phase === "execution-disabled") return "Execution still requires current goal/live-readiness/demo-fill gates.";
  if (item.phase === "candidate-retest") return "Run bounded OOS/bracket replay on the current normalized base; reject on negative worst fold.";
  return "Keep in low-priority research inventory until a hypothesis or matrix lane points to it.";
}

export async function buildStrategyZooAudit(args: {
  outputPath?: string;
  propFirmMatrixPath?: string;
  now?: () => string;
} = {}): Promise<StrategyZooAuditReport> {
  const outputPath = resolve(args.outputPath ?? DEFAULT_OUTPUT_PATH);
  const propFirmMatrixPath = resolve(args.propFirmMatrixPath ?? DEFAULT_PROP_MATRIX_PATH);
  const matrix = await readJsonSafe(propFirmMatrixPath);
  const catalog = buildStrategyCatalog();
  const ids = [...new Set([...SUPPORTED_STRATEGY_IDS, ...Object.keys(STRATEGY_CLASSIFICATION), ...Object.keys(catalog)])];

  const items = ids.sort().map((strategyId) => {
    const supported = (SUPPORTED_STRATEGY_IDS as readonly string[]).includes(strategyId);
    const classification = supported ? getClassification(strategyId as SupportedStrategyId) : "SKELETON";
    const registered = Boolean(catalog[strategyId]);
    const evidence = strategyEvidence(strategyId, matrix);
    const base = {
      strategyId,
      classification,
      registered,
      executable: supported ? isExecutable(strategyId as SupportedStrategyId) : false,
      testable: supported ? isTestable(strategyId as SupportedStrategyId) : false,
      phase: phaseFor({ classification, registered, evidence }),
      evidence
    };
    return { ...base, nextAction: nextActionFor(base) };
  });

  const counts = items.reduce<Record<string, number>>((acc, item) => {
    acc.total = (acc.total ?? 0) + 1;
    acc[`classification:${item.classification}`] = (acc[`classification:${item.classification}`] ?? 0) + 1;
    acc[`phase:${item.phase}`] = (acc[`phase:${item.phase}`] ?? 0) + 1;
    if (item.registered) acc.registered = (acc.registered ?? 0) + 1;
    return acc;
  }, {});

  const shortlist = items
    .filter((item) => item.phase === "candidate-retest")
    .sort((left, right) => (right.evidence.bestPropFirmScore ?? -1) - (left.evidence.bestPropFirmScore ?? -1))
    .slice(0, 12);

  const report: StrategyZooAuditReport = {
    command: "strategy-zoo-audit",
    generatedAt: args.now?.() ?? new Date().toISOString(),
    outputPath,
    inputs: {
      propFirmMatrixPath,
      propFirmMatrixPresent: matrix !== null
    },
    counts,
    items,
    shortlist,
    rules: [
      "This audit never promotes execution by itself.",
      "QUARANTINED strategies remain blocked until a new independent filter passes fresh OOS.",
      "BRONZE strategies can be retested but cannot route demo/live.",
      "Prop-firm matrix evidence is advisory until bracket replay and demo fills exist."
    ]
  };

  await mkdir(dirname(outputPath), { recursive: true });
  await writeFile(outputPath, `${JSON.stringify(report, null, 2)}\n`, "utf8");
  return report;
}
