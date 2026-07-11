import { mkdir, readFile, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";

export type RuntimeOwner = "open-jarvis" | "hermes" | "bill" | "agency-os" | "researcher" | "openclaw";
export type WorkerLaneOwner = "bill" | "agency-os" | "researcher" | "openclaw";

export interface RuntimeWorkerNode {
  id: string;
  role: string;
  mission: string;
  alwaysOn: boolean;
  inputs: string[];
  outputs: string[];
  approvalBoundary?: string;
}

export interface RuntimeWorkerTeam {
  owner: WorkerLaneOwner;
  purpose: string;
  pinnedInRotation: boolean;
  primaryArtifacts: string[];
  workers: RuntimeWorkerNode[];
}

export interface RuntimeManifest {
  version: 1;
  architecture: {
    founderIngress: "open-jarvis";
    orchestrator: "hermes";
    marketRuntime: "bill";
    companyRuntime: "agency-os";
    researchRuntime: "researcher";
    fixerRuntime: "openclaw";
    changeControl: "founder-approval-required";
  };
  ingress: {
    owner: "open-jarvis";
    costMode: "hosted-budget-first";
    localBaseUrl: string;
    routingModel: string;
    fallbackModel?: string;
    webAccess: "browser-tools-hosted";
    notes: string[];
  };
  supervisor: {
    owner: "hermes";
    mode: "bounded-parallel";
    rotationEnabled: boolean;
    maxParallelWorkers: number;
    maxParallelByOwner: Record<WorkerLaneOwner, number>;
    rotationOrder: WorkerLaneOwner[];
    notes: string[];
  };
  workerCompute: {
    preflightBudgetMode: "free-until-ready";
    paidBudgetMode: "budget-tier";
    preferredBudgetFamilies: string[];
    notes: string[];
  };
  workerTopology: RuntimeWorkerTeam[];
}

export const DEFAULT_RUNTIME_MANIFEST_STATE_PATH = ".rumbling-hedge/state/runtime-manifest.json";

function readPositiveInt(env: NodeJS.ProcessEnv, key: string, fallback: number): number {
  const raw = env[key];
  if (!raw) return fallback;
  const parsed = Number.parseInt(raw, 10);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : fallback;
}

function parseBool(value: string | undefined, fallback: boolean): boolean {
  if (value == null) return fallback;
  const normalized = value.trim().toLowerCase();
  if (["1", "true", "yes", "on"].includes(normalized)) return true;
  if (["0", "false", "no", "off"].includes(normalized)) return false;
  return fallback;
}

function normalizeModel(value: string | undefined, fallback: string): string {
  if (!value) return fallback;
  return value.startsWith("ollama/") ? value.slice("ollama/".length) : value;
}

function buildWorkerTopology(): RuntimeWorkerTeam[] {
  return [
    {
      owner: "bill",
      purpose: "Market research, strategy hardening, paper execution, and live gating.",
      pinnedInRotation: true,
      primaryArtifacts: [
        ".rumbling-hedge/state",
        ".rumbling-hedge/logs",
        "journals",
        "data/prediction"
      ],
      workers: [
        {
          id: "market-scanner",
          role: "opportunity discovery",
          mission: "Continuously scan prediction, futures, options, crypto, and macro lanes for bounded opportunities.",
          alwaysOn: true,
          inputs: ["venue snapshots", "market feeds", "track policy"],
          outputs: ["opportunity board", "candidate rankings"]
        },
        {
          id: "data-collector",
          role: "collection",
          mission: "Keep raw market datasets fresh and route around degraded symbols or venues.",
          alwaysOn: true,
          inputs: ["scheduled jobs", "venue adapters", "researcher source proposals"],
          outputs: ["normalized datasets", "refresh diagnostics"]
        },
        {
          id: "data-processor",
          role: "processing",
          mission: "Normalize, dedupe, and label collected data so strategy evaluation uses stable inputs.",
          alwaysOn: true,
          inputs: ["raw datasets", "corpus context", "market metadata"],
          outputs: ["normalized bars", "feature inputs", "freshness artifacts"]
        },
        {
          id: "strategy-lab",
          role: "permutation search",
          mission: "Run bounded permutations, walk-forward checks, and ranking loops to harden strategy logic.",
          alwaysOn: true,
          inputs: ["normalized datasets", "runtime parameters", "research hypotheses"],
          outputs: ["oos reports", "profile rankings", "promotion evidence"]
        },
        {
          id: "risk-review",
          role: "realism and guardrails",
          mission: "Stress fees, spread, slippage, fill timing, and tail-loss assumptions before promotion.",
          alwaysOn: true,
          inputs: ["strategy-lab reports", "execution assumptions", "backtest outputs"],
          outputs: ["kill/go notes", "risk blockers", "promotion constraints"],
          approvalBoundary: "Required before any widening from paper to live."
        },
        {
          id: "execution-guard",
          role: "paper/live gate",
          mission: "Stage paper fills automatically and fail closed on live routing unless all approvals are explicit.",
          alwaysOn: true,
          inputs: ["committee verdicts", "promotion state", "risk controls"],
          outputs: ["paper fills", "live rejections", "execution audit trail"],
          approvalBoundary: "Founder approval required for live routing or risk-boundary changes."
        }
      ]
    },
    {
      owner: "agency-os",
      purpose: "Founder-ready company execution packets across AgentPay and adjacent business lanes.",
      pinnedInRotation: true,
      primaryArtifacts: [
        ".openclaw/workspace-agency-os/STATUS.md",
        ".openclaw/workspace-agency-os/OUTBOX.md"
      ],
      workers: [
        {
          id: "packet-builder",
          role: "founder packeting",
          mission: "Turn internal lane movement into one founder-ready packet each cycle.",
          alwaysOn: true,
          inputs: ["lane updates", "mission priorities", "founder requests"],
          outputs: ["status packets", "next actions"]
        },
        {
          id: "execution-runner",
          role: "company operations",
          mission: "Advance the currently active company lane with one concrete deliverable instead of internal drift.",
          alwaysOn: true,
          inputs: ["product lanes", "sales lanes", "growth tasks"],
          outputs: ["execution artifacts", "operating updates"]
        }
      ]
    },
    {
      owner: "researcher",
      purpose: "Web and GitHub ingestion feeding Bill's black box and the rest of the machine.",
      pinnedInRotation: false,
      primaryArtifacts: [
        ".rumbling-hedge/research/corpus",
        ".rumbling-hedge/research/researcher/latest-run.json"
      ],
      workers: [
        {
          id: "source-scout",
          role: "target discovery",
          mission: "Find worthwhile papers, venues, repos, and sources that can sharpen Bill's active lanes.",
          alwaysOn: true,
          inputs: ["targets.json", "policy.json", "Hermes requests"],
          outputs: ["crawl targets", "source proposals"]
        },
        {
          id: "crawler",
          role: "acquisition",
          mission: "Pull source material within domain and budget limits.",
          alwaysOn: true,
          inputs: ["target list", "Firecrawl", "GitHub sources"],
          outputs: ["raw documents", "crawl diagnostics"]
        },
        {
          id: "corpus-filter",
          role: "quality control",
          mission: "Dedupe, score, and retain only durable high-signal chunks.",
          alwaysOn: true,
          inputs: ["raw documents", "classifier scores", "judge scores"],
          outputs: ["kept chunks", "dedup stats", "quality blockers"]
        },
        {
          id: "eval-runner",
          role: "corpus evaluation",
          mission: "Re-score the private eval set when corpus growth crosses threshold so ingestion quality stays measurable.",
          alwaysOn: false,
          inputs: ["corpus deltas", "golden eval prompts"],
          outputs: ["eval scorecards", "quality summaries"]
        }
      ]
    },
    {
      owner: "openclaw",
      purpose: "Bounded implementation and repair work assigned by Hermes.",
      pinnedInRotation: false,
      primaryArtifacts: [
        ".openclaw/workspace-hermes/OUTBOX.md",
        ".rumbling-hedge/state/hermes-supervisor.json"
      ],
      workers: [
        {
          id: "ops-fixer",
          role: "runtime repair",
          mission: "Patch broken wrappers, launchd surfaces, and path drift that block the machine.",
          alwaysOn: true,
          inputs: ["Hermes incidents", "runtime failures", "ops scripts"],
          outputs: ["repairs", "prevention notes"]
        },
        {
          id: "code-patcher",
          role: "bounded implementation",
          mission: "Land narrow diffs inside Hedge or related runtimes without widening authority.",
          alwaysOn: true,
          inputs: ["Hermes task packets", "repo context", "tests"],
          outputs: ["patches", "verification notes"],
          approvalBoundary: "Required for authority widening, live-risk changes, or destructive operations."
        },
        {
          id: "docs-sync",
          role: "control-plane hygiene",
          mission: "Keep workspace instructions, manifests, and handoff files aligned with the actual control plane.",
          alwaysOn: true,
          inputs: ["runtime manifest", "workspace docs", "incident notes"],
          outputs: ["updated instructions", "topology sync notes"]
        }
      ]
    }
  ];
}

export function buildRuntimeManifest(env: NodeJS.ProcessEnv = process.env): RuntimeManifest {
  const routingModel = env.BILL_CLOUD_REVIEW_MODEL ?? "openrouter/qwen/qwen3-coder:free";
  const fallbackModel = normalizeModel(env.BILL_LOCAL_HEAVY_MODEL, "qwen2.5-coder:14b");
  return {
    version: 1,
    architecture: {
      founderIngress: "open-jarvis",
      orchestrator: "hermes",
      marketRuntime: "bill",
      companyRuntime: "agency-os",
      researchRuntime: "researcher",
      fixerRuntime: "openclaw",
      changeControl: "founder-approval-required"
    },
    ingress: {
      owner: "open-jarvis",
      costMode: "hosted-budget-first",
      localBaseUrl: env.BILL_OLLAMA_BASE_URL ?? env.OLLAMA_BASE_URL ?? "http://localhost:11434",
      routingModel,
      fallbackModel,
      webAccess: "browser-tools-hosted",
      notes: [
        "Keep OpenJarvis on hosted free or budget-tier models so the founder-facing surface matches the rest of the orchestrated control plane.",
        "Reserve local Ollama models for background fallback, cheap repair work, and degraded-mode continuity."
      ]
    },
    supervisor: {
      owner: "hermes",
      mode: "bounded-parallel",
      rotationEnabled: parseBool(env.HERMES_ROTATION_ENABLED, true),
      maxParallelWorkers: readPositiveInt(env, "HERMES_MAX_PARALLEL_WORKERS", 3),
      maxParallelByOwner: {
        bill: readPositiveInt(env, "HERMES_MAX_PARALLEL_BILL", 2),
        "agency-os": readPositiveInt(env, "HERMES_MAX_PARALLEL_AGENCY_OS", 1),
        researcher: readPositiveInt(env, "HERMES_MAX_PARALLEL_RESEARCHER", 1),
        openclaw: readPositiveInt(env, "HERMES_MAX_PARALLEL_OPENCLAW", 1)
      },
      rotationOrder: ["bill", "agency-os", "researcher", "openclaw"],
      notes: [
        "Hermes owns orchestration and should cap simultaneous workers instead of trying to run every lane at once.",
        "Keep Bill and Agency OS making progress every cycle, then rotate Researcher and OpenClaw through the spare slots."
      ]
    },
    workerCompute: {
      preflightBudgetMode: "free-until-ready",
      paidBudgetMode: "budget-tier",
      preferredBudgetFamilies: ["OpenRouter-free", "DeepSeek-class", "GPT-4o-mini-class", "Gemini-Flash-Lite-class"],
      notes: [
        "Use OpenRouter free models first for orchestration, coding, and research whenever quality is adequate.",
        "When paid worker models are enabled, keep them below the founder's $1.50 / 1M output ceiling unless the approval explicitly widens that cap."
      ]
    },
    workerTopology: buildWorkerTopology()
  };
}

export async function writeRuntimeManifestArtifact(args?: {
  manifest?: RuntimeManifest;
  env?: NodeJS.ProcessEnv;
  filePath?: string;
}): Promise<string> {
  const manifest = args?.manifest ?? buildRuntimeManifest(args?.env);
  const target = resolve(args?.filePath ?? DEFAULT_RUNTIME_MANIFEST_STATE_PATH);
  await mkdir(dirname(target), { recursive: true });
  await writeFile(target, `${JSON.stringify(manifest, null, 2)}\n`, "utf8");
  return target;
}

export async function readRuntimeManifestArtifact(filePath = DEFAULT_RUNTIME_MANIFEST_STATE_PATH): Promise<RuntimeManifest | null> {
  try {
    return JSON.parse(await readFile(resolve(filePath), "utf8")) as RuntimeManifest;
  } catch {
    return null;
  }
}
