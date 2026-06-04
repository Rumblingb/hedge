import { existsSync, readFileSync, readdirSync, statSync } from "node:fs";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { dirname, join, resolve } from "node:path";
import { inspectBarsFromCsv, loadBarsFromCsv } from "../data/csv.js";
import { assessBarsForResearch } from "../data/quality.js";

export interface ResearchFabricDataset {
  label: string;
  path: string;
  present: boolean;
  rows?: number;
  symbols?: string[];
  startTs?: string;
  endTs?: string;
  expectedStepSeconds?: number;
  pass?: boolean;
  failedChecks?: string[];
  wallClockEndLagMinutes?: number;
  note?: string;
  error?: string;
}

export interface ResearchFabricReport {
  command: "research-fabric";
  generatedAt: string;
  outputPath: string;
  data: {
    datasets: ResearchFabricDataset[];
    selectedBase: string | null;
    blockers: string[];
  };
  models: {
    timesFm: unknown;
    kronos: unknown;
    rustWq: unknown;
  };
  pipelines: {
    strategyFactory: unknown;
    liveReadinessGate: unknown;
    predictionReview: unknown;
    openJarvisBoard: string | null;
    n8nWorkflows: Array<{ path: string; active?: boolean; name?: string; error?: string }>;
    obsidianNotes: Array<{ path: string; mtime: string; sizeBytes: number }>;
  };
  externalSources: {
    siblingWorktrees: Array<{ path: string; head?: string; dirtyFiles?: number; status?: string; error?: string }>;
    dom: {
      snapshot: unknown;
      blockers: string[];
    };
    researchNotes: Array<{ path: string; status: "useful" | "contradiction" | "stale" | "reference"; summary: string }>;
  };
  integration: {
    canonicalRule: string[];
    blockers: string[];
    nextActions: string[];
  };
}

const DEFAULT_OUTPUT = ".rumbling-hedge/state/research-fabric.latest.json";

const DATASETS = [
  ["5m-60d-six-market", "data/free/ALL-6MARKETS-5m-60d-normalized.csv", 30],
  ["15m-60d-six-market", "data/free/ALL-6MARKETS-15m-60d-normalized.csv", 60],
  ["30m-60d-six-market", "data/free/ALL-6MARKETS-30m-60d-normalized.csv", 120],
  ["60m-60d-six-market", "data/free/ALL-6MARKETS-60m-60d-normalized.csv", 240],
  ["15m-60d-nq-es", "data/free/ALL-2MARKETS-NQ-ES-15m-60d-fresh.csv", 60],
  ["1d-5y-nq-es", "data/free/ALL-2MARKETS-NQ-ES-1d-5y-fresh.csv", 4320],
  ["1m-3yr-nq-kaggle", "data/free/NQ-1m-3yr.csv", 1],
  ["5m-3yr-nq-kaggle", "data/free/NQ-5m-3yr.csv", 5],
  ["1m-20yr-es-kaggle", "data/free/ES-1m-20yr.csv", 1],
  ["5m-20yr-es-kaggle", "data/free/ES-5m-20yr.csv", 5],
  ["1d-23yr-es-continuous", "data/free/ES-daily-2000-2022-continuous.csv", 1440]
] as const;

async function readJsonSafe(path: string): Promise<unknown> {
  try {
    return JSON.parse(await readFile(path, "utf8"));
  } catch {
    return null;
  }
}

async function readTextSafe(path: string): Promise<string | null> {
  try {
    return await readFile(path, "utf8");
  } catch {
    return null;
  }
}

async function runGit(args: string[], cwd: string): Promise<string | null> {
  const { execFile } = await import("node:child_process");
  return new Promise((resolve) => {
    execFile("git", args, { cwd }, (error, stdout) => {
      resolve(error ? null : stdout.trim());
    });
  });
}

function listFilesSafe(dir: string): string[] {
  try {
    return readdirSync(dir).map((name) => join(dir, name));
  } catch {
    return [];
  }
}

async function inspectDataset(baseDir: string, label: string, relativePath: string, maxEndLagMinutes: number): Promise<ResearchFabricDataset> {
  const path = resolve(baseDir, relativePath);
  if (!existsSync(path)) {
    return { label, path, present: false, note: "missing" };
  }

  try {
    const [inspection, bars] = await Promise.all([
      inspectBarsFromCsv(path),
      loadBarsFromCsv(path)
    ]);
    const quality = assessBarsForResearch(bars, {
      minCoveragePct: 0.95,
      maxEndLagMinutes,
      maxWallClockEndLagMinutes: 180,
      requiredSymbols: inspection.symbols
    });
    const wallClockCheck = quality.checks.find((check) => check.name === "maxWallClockEndLagMinutes");
    const wallClockEndLagMinutes = wallClockCheck?.passed
      ? undefined
      : Number((wallClockCheck?.reason.match(/observed ([\d.]+)/)?.[1] ?? "NaN"));
    const failedChecks = quality.checks.filter((check) => !check.passed).map((check) => check.name);
    return {
      label,
      path,
      present: true,
      rows: inspection.dataRows,
      symbols: inspection.symbols,
      startTs: inspection.startTs,
      endTs: inspection.endTs,
      expectedStepSeconds: quality.expectedStepSeconds,
      pass: quality.pass,
      failedChecks,
      wallClockEndLagMinutes: Number.isFinite(wallClockEndLagMinutes) ? wallClockEndLagMinutes : undefined,
      note: failedChecks.length === 1 && failedChecks[0] === "maxWallClockEndLagMinutes"
        ? "internally complete, but wall-clock freshness needs market-calendar interpretation"
        : undefined
    };
  } catch (error) {
    return {
      label,
      path,
      present: true,
      error: error instanceof Error ? error.message : String(error)
    };
  }
}

function summarizeN8nWorkflows(baseDir: string): ResearchFabricReport["pipelines"]["n8nWorkflows"] {
  return [
    ...listFilesSafe(resolve(baseDir, "ops/n8n")),
    ...listFilesSafe(resolve(process.env.HOME ?? "/Users/brain", "n8n_workflows"))
  ]
    .filter((path) => path.endsWith(".json"))
    .map((path) => {
      try {
        const raw = JSON.parse(readFileSync(path, "utf8")) as Record<string, unknown>;
        return {
          path,
          active: raw.active === true,
          name: typeof raw.name === "string" ? raw.name : undefined
        };
      } catch (error) {
        return { path, error: error instanceof Error ? error.message : String(error) };
      }
    });
}

function summarizeObsidianNotes(): ResearchFabricReport["pipelines"]["obsidianNotes"] {
  const roots = [
    resolve(process.env.HOME ?? "/Users/brain", "Documents/memorybrain/Agent-Shared"),
    resolve(process.env.HOME ?? "/Users/brain", "Documents/memorybrain/Agent-Hermes")
  ];
  const out: ResearchFabricReport["pipelines"]["obsidianNotes"] = [];
  const stack = [...roots];
  const patterns = /(strategy|research|oos|kronos|timesfm|bill|trading|macro|readiness)/i;

  while (stack.length > 0 && out.length < 80) {
    const current = stack.pop()!;
    if (!existsSync(current)) continue;
    const stat = statSync(current);
    if (stat.isDirectory()) {
      for (const child of listFilesSafe(current)) stack.push(child);
      continue;
    }
    if (current.endsWith(".md") && patterns.test(current)) {
      out.push({ path: current, mtime: stat.mtime.toISOString(), sizeBytes: stat.size });
    }
  }

  return out.sort((a, b) => b.mtime.localeCompare(a.mtime)).slice(0, 40);
}

async function summarizeSiblingWorktrees(): Promise<ResearchFabricReport["externalSources"]["siblingWorktrees"]> {
  const candidates = [
    resolve(process.env.HOME ?? "/Users/brain", "worktrees/hedge-goal-live"),
    resolve(process.env.HOME ?? "/Users/brain", ".openclaw.retired-2026-05-12/bases/hedge")
  ];
  const summaries: ResearchFabricReport["externalSources"]["siblingWorktrees"] = [];

  for (const path of candidates) {
    if (!existsSync(path)) continue;
    try {
      const head = await runGit(["rev-parse", "HEAD"], path);
      const status = await runGit(["status", "--short"], path);
      summaries.push({
        path,
        head: head ?? undefined,
        dirtyFiles: status ? status.split("\n").filter(Boolean).length : 0,
        status: status ? "dirty" : "clean"
      });
    } catch (error) {
      summaries.push({ path, error: error instanceof Error ? error.message : String(error) });
    }
  }

  return summaries;
}

function summarizeDom(snapshot: unknown): ResearchFabricReport["externalSources"]["dom"] {
  const data = snapshot as Record<string, unknown> | null;
  const blockers = [
    "DOM snapshot is outside repo state path; canonical jobs may miss it",
    "DOM artifact has no symbol, venue/account, ladder depth, bid/ask sizes, trade tape, or replay window",
    "Current DOM script uses OHLCV proxies; it is not true order-book evidence"
  ];
  if (!data) {
    return { snapshot: null, blockers: ["DOM snapshot missing"] };
  }
  if (typeof data.timestamp !== "string") blockers.push("DOM artifact has no timestamp");
  if (!Array.isArray(data.signals)) blockers.push("DOM artifact has no signal list");
  return { snapshot: data, blockers };
}

function summarizeExternalResearchNotes(): ResearchFabricReport["externalSources"]["researchNotes"] {
  const notes = [
    {
      path: resolve(process.env.HOME ?? "/Users/brain", "Documents/memorybrain/Agent-Shared/final-quant-audit-2026-05-15.md"),
      status: "contradiction" as const,
      summary: "Promotes ORB as live-deployable/SILVER, but current factory and live-readiness block ORB with zero deployable rolling OOS windows."
    },
    {
      path: resolve(process.env.HOME ?? "/Users/brain", "Documents/memorybrain/Agent-Hermes/daily/deep-strategy-analysis-2026-05-17.md"),
      status: "useful" as const,
      summary: "Claims wq-trend-mom and ORB 30m OOS strength; must be treated as hypothesis until reproduced in TS factory/Rust with signed R parsing and shared normalized data."
    },
    {
      path: resolve(process.env.HOME ?? "/Users/brain", ".hermes/cache/documents/dom_framework.txt"),
      status: "reference" as const,
      summary: "Useful DOM taxonomy and formulas, but requires real depth/tape capture before strategy validation."
    },
    {
      path: resolve(process.env.HOME ?? "/Users/brain", "quant_research/findings_summary.md"),
      status: "reference" as const,
      summary: "Supports OFI, lead-lag, and volatility-regime research direction; not deployment evidence."
    },
    {
      path: resolve(process.env.HOME ?? "/Users/brain", ".hermes/skills/quant-research-workflow/SKILL.md"),
      status: "useful" as const,
      summary: "Contains an important R-multiple verification warning and OOS discipline that should govern Python/Rust results."
    }
  ];

  return notes.filter((note) => existsSync(note.path));
}

export async function buildResearchFabricReport(options: { baseDir?: string; outputPath?: string } = {}): Promise<ResearchFabricReport> {
  const baseDir = resolve(options.baseDir ?? process.cwd());
  const outputPath = resolve(baseDir, options.outputPath ?? DEFAULT_OUTPUT);
  const datasets = await Promise.all(DATASETS.map(([label, path, maxLag]) => inspectDataset(baseDir, label, path, maxLag)));
  const usable = datasets.filter((dataset) =>
    dataset.present
    && !dataset.error
    && dataset.rows
    && dataset.rows > 0
    && !dataset.failedChecks?.some((check) => check !== "maxWallClockEndLagMinutes")
  );
  const selectedBase = usable.find((dataset) => dataset.label === "15m-60d-six-market")?.path
    ?? usable[0]?.path
    ?? null;
  const dataBlockers = [
    ...(usable.length === 0 ? ["no usable normalized futures dataset found"] : []),
    ...datasets
      .filter((dataset) => dataset.error)
      .map((dataset) => `${dataset.label}: ${dataset.error}`),
    ...datasets
      .filter((dataset) => dataset.present && dataset.failedChecks?.some((check) => check !== "maxWallClockEndLagMinutes"))
      .map((dataset) => `${dataset.label}: failed ${dataset.failedChecks?.join(", ")}`)
  ];

  const timesFm = await readJsonSafe(resolve(baseDir, ".rumbling-hedge/state/timesfm-status.audit.json"))
    ?? await readJsonSafe(resolve(baseDir, ".rumbling-hedge/research/timesfm/readiness.json"));
  const kronos = await readJsonSafe(resolve(baseDir, ".rumbling-hedge/state/kronos-health.latest.json"));
  const rustWq = await readJsonSafe(resolve(baseDir, ".rumbling-hedge/state/rust-wq-guardrailed.json"));
  const strategyFactory = await readJsonSafe(resolve(baseDir, ".rumbling-hedge/state/strategy-factory.latest.json"));
  const liveReadinessGate = await readJsonSafe(resolve(baseDir, ".rumbling-hedge/state/live-readiness-gate.latest.json"));
  const predictionReview = await readJsonSafe(resolve(baseDir, ".rumbling-hedge/state/prediction-review.latest.json"));
  const openJarvisBoard = await readTextSafe(resolve(baseDir, ".rumbling-hedge/state/openjarvis-board.md"));
  const home = process.env.HOME ?? "/Users/brain";
  const externalDomSnapshot = await readJsonSafe(resolve(home, ".rumbling-hedge/state/dom_micro_edges.json"));
  const siblingWorktrees = await summarizeSiblingWorktrees();
  const dom = summarizeDom(externalDomSnapshot);
  const researchNotes = summarizeExternalResearchNotes();

  const modelBlockers = [
    ...((timesFm as any)?.status === "blocked" ? ["TimesFM blocked: weights/cache or memory not ready"] : []),
    ...(!kronos ? ["Kronos health artifact missing"] : []),
    ...((rustWq as any)?.profitable === false ? ["Rust WQ latest guardrailed artifact is not profitable"] : [])
  ];
  const gateBlockers = [
    ...((strategyFactory as any)?.status === "blocked" ? ["strategy-factory blocked"] : []),
    ...((liveReadinessGate as any)?.readyForLive === false ? ["live-readiness gate red"] : []),
    ...((predictionReview as any)?.readyForPaper === false ? ["prediction review has no paper candidates"] : [])
  ];
  const externalBlockers = [
    ...dom.blockers,
    ...researchNotes
      .filter((note) => note.status === "contradiction")
      .map((note) => `${note.path}: ${note.summary}`),
    ...siblingWorktrees
      .filter((worktree) => (worktree.dirtyFiles ?? 0) > 0)
      .map((worktree) => `${worktree.path}: dirty sibling worktree with ${worktree.dirtyFiles} changed/untracked files; review before cherry-picking`)
  ];

  const report: ResearchFabricReport = {
    command: "research-fabric",
    generatedAt: new Date().toISOString(),
    outputPath,
    data: {
      datasets,
      selectedBase,
      blockers: dataBlockers
    },
    models: {
      timesFm,
      kronos,
      rustWq
    },
    pipelines: {
      strategyFactory,
      liveReadinessGate,
      predictionReview,
      openJarvisBoard,
      n8nWorkflows: summarizeN8nWorkflows(baseDir),
      obsidianNotes: summarizeObsidianNotes()
    },
    externalSources: {
      siblingWorktrees,
      dom,
      researchNotes
    },
    integration: {
      canonicalRule: [
        "All strategy ideas must enter as a research profile or prediction policy before promotion.",
        "All bar research must reference a normalized dataset path and quality report.",
        "Python/Rust discoveries are hypotheses until TS walk-forward, rolling OOS, and live-readiness artifacts agree.",
        "TimesFM/Kronos forecasts are context features only until they pass independent OOS contribution tests.",
        "Obsidian/n8n notes can create directives, but cannot bypass no-edge, data-quality, or execution gates."
      ],
      blockers: [...dataBlockers, ...modelBlockers, ...gateBlockers, ...externalBlockers],
      nextActions: [
        "Run strategy-factory on the selected normalized 15m/30m/60m datasets with explicit profile IDs.",
        "Add market-calendar-aware freshness so weekend/holiday closed-market data is not mislabeled as feed stale.",
        "Convert promising Python-only strategies into TS research profiles before any more promotion claims.",
        "Move DOM collection into the repo state/data tree and capture real depth/tape fields before using DOM signals for routing.",
        "Review hedge-goal-live governance modules for selective import; do not import its promotion claims without rerunning current gates.",
        "Keep TimesFM blocked until weights are cached and memory pressure is acceptable.",
        "Feed this report into n8n/Obsidian as the single daily research handoff."
      ]
    }
  };

  await mkdir(dirname(outputPath), { recursive: true });
  await writeFile(outputPath, `${JSON.stringify(report, null, 2)}\n`, "utf8");
  return report;
}
