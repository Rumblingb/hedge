import { execFile } from "node:child_process";
import { mkdir, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";

export type WorktreeFileCategory =
  | "governance-risk"
  | "strategy-research"
  | "data"
  | "execution-live"
  | "external-vendor"
  | "generated-cache"
  | "ops-docs"
  | "dependencies"
  | "unknown";

export interface WorktreeFileChange {
  path: string;
  status: string;
  category: WorktreeFileCategory;
}

export interface WorktreeInventoryItem {
  path: string;
  branch: string | null;
  head: string | null;
  dirtyFiles: number;
  categories: Record<WorktreeFileCategory, number>;
  changes: WorktreeFileChange[];
  intakeDecision: "canonical-active" | "review-selectively" | "quarantine";
  notes: string[];
}

export interface WorktreeConsolidationReport {
  command: "worktree-consolidation";
  generatedAt: string;
  outputPath: string;
  repoRoot: string;
  posture: "organized-blocked-for-live-money";
  worktrees: WorktreeInventoryItem[];
  branchPolicy: string[];
  intakeOrder: string[];
  hardRules: string[];
}

const DEFAULT_OUTPUT_PATH = ".rumbling-hedge/state/worktree-consolidation.latest.json";

const ALL_CATEGORIES: WorktreeFileCategory[] = [
  "governance-risk",
  "strategy-research",
  "data",
  "execution-live",
  "external-vendor",
  "generated-cache",
  "ops-docs",
  "dependencies",
  "unknown"
];

function runGit(args: string[], cwd: string): Promise<string> {
  return new Promise((resolve) => {
    execFile("git", args, { cwd }, (error, stdout) => {
      resolve(error ? "" : stdout.trim());
    });
  });
}

export function categorizeWorktreePath(path: string): WorktreeFileCategory {
  if (path.startsWith("tests/")) {
    const subject = path.replace(/^tests\//, "src/");
    const subjectCategory = categorizeWorktreePath(subject);
    return subjectCategory === "unknown" ? "strategy-research" : subjectCategory;
  }
  if (
    path === "src/cli.ts" ||
    path === "src/config.ts" ||
    path === "src/domain.ts" ||
    path.startsWith("src/engine/worktreeConsolidation")
  ) {
    return "governance-risk";
  }
  if (
    path === "package.json" ||
    path === "package-lock.json" ||
    path.startsWith("pnpm-lock.") ||
    path.startsWith("yarn.lock")
  ) {
    return "dependencies";
  }
  if (
    path.startsWith("data/") ||
    path.startsWith("src/data/") ||
    path.startsWith("src/research/freeMacroContext") ||
    path.includes("macro-context")
  ) {
    return "data";
  }
  if (
    path.startsWith("external/") ||
    path.startsWith("vendor/") ||
    path.startsWith("retired/") ||
    path.startsWith("node_modules/")
  ) {
    return "external-vendor";
  }
  if (
    path.startsWith("tmp/") ||
    path.startsWith(".rumbling-hedge/state/") ||
    path.endsWith(".latest.json") ||
    path.endsWith(".out") ||
    path.endsWith(".summary")
  ) {
    return "generated-cache";
  }
  if (
    path.startsWith("docs/") ||
    path.endsWith(".md") ||
    path.startsWith("ops/mac-mini/README") ||
    path.startsWith("ops/mac-mini/launchd/README") ||
    path.endsWith("README.md")
  ) {
    return "ops-docs";
  }
  if (
    path.startsWith("src/live/") ||
    path.startsWith("src/adapters/") ||
    path.startsWith("src/prediction/adapters/") ||
    path.includes("pendingTradeGate") ||
    path.includes("signalRouter") ||
    path.startsWith("src/prediction/execution/") ||
    path.startsWith("src/prediction/gengar") ||
    path.includes("Execution") ||
    path.includes("execution") ||
    path.includes("projectx") ||
    path.includes("topstep") ||
    path.includes("tradovate") ||
    path.includes("pickmytrade") ||
    path.startsWith("ops/start-") ||
    path.startsWith("scripts/deposit") ||
    path.startsWith("scripts/fund") ||
    path.startsWith("scripts/wire-up")
  ) {
    return "execution-live";
  }
  if (
    path.includes("risk") ||
    path.includes("Risk") ||
    path.includes("readiness") ||
    path.includes("Readiness") ||
    path.includes("goal") ||
    path.includes("Goal") ||
    path.includes("guard") ||
    path.includes("Guard") ||
    path.includes("allocator") ||
    path.includes("Allocator") ||
    path.includes("cashflow") ||
    path.includes("Cashflow") ||
    path.includes("hermes") ||
    path.includes("Hermes") ||
    path.includes("killSwitch")
  ) {
    return "governance-risk";
  }
  if (
    path.startsWith("src/engine/agenticLoop") ||
    path.startsWith("src/engine/domEdgeIntegration") ||
    path.startsWith("src/engine/edgeForensics") ||
    path.startsWith("src/engine/signalDecayLedger") ||
    path.startsWith("src/engine/macroConditionedPolicy") ||
    path.startsWith("src/engine/report") ||
    path.startsWith("src/engine/fusion") ||
    path.startsWith("src/engine/strategyFusion") ||
    path.startsWith("src/engine/tvDataFetcher") ||
    path.startsWith("src/engine/tvLiveBridge") ||
    path.startsWith("src/engine/tradovateDataFetcher") ||
    path.startsWith("src/strategies/") ||
    path.startsWith("src/research/") ||
    path.startsWith("src/prediction/") ||
    path.startsWith("src/engine/strategy") ||
    path.startsWith("src/engine/walkforward") ||
    path.startsWith("src/engine/backtest") ||
    path.startsWith("src/engine/rollingOos") ||
    path.startsWith("bill-core/") ||
    path.includes("alpha") ||
    path.includes("Strategy") ||
    path.includes("strategy")
  ) {
    return "strategy-research";
  }
  if (path.startsWith("ops/") || path.startsWith("scripts/")) {
    return "ops-docs";
  }
  return "unknown";
}

export function parseGitWorktreeList(raw: string): Array<{ path: string; head: string | null; branch: string | null }> {
  const items: Array<{ path: string; head: string | null; branch: string | null }> = [];
  let current: { path: string; head: string | null; branch: string | null } | null = null;
  for (const line of raw.split(/\r?\n/)) {
    if (line.startsWith("worktree ")) {
      if (current) items.push(current);
      current = { path: line.slice("worktree ".length), head: null, branch: null };
    } else if (current && line.startsWith("HEAD ")) {
      current.head = line.slice("HEAD ".length);
    } else if (current && line.startsWith("branch ")) {
      current.branch = line.slice("branch ".length).replace(/^refs\/heads\//, "");
    }
  }
  if (current) items.push(current);
  return items;
}

function parseStatus(raw: string): WorktreeFileChange[] {
  return raw
    .split(/\r?\n/)
    .map((line) => line.trimEnd())
    .filter(Boolean)
    .filter((line) => !line.startsWith("## "))
    .map((line) => {
      const status = line.slice(0, 2).trim() || "??";
      const path = line.slice(3).replace(/^"|"$/g, "");
      return { path, status, category: categorizeWorktreePath(path) };
    });
}

function emptyCategoryCounts(): Record<WorktreeFileCategory, number> {
  return Object.fromEntries(ALL_CATEGORIES.map((category) => [category, 0])) as Record<WorktreeFileCategory, number>;
}

function intakeDecision(path: string, repoRoot: string, dirtyFiles: number): WorktreeInventoryItem["intakeDecision"] {
  if (resolve(path) === resolve(repoRoot)) return "canonical-active";
  if (dirtyFiles === 0) return "review-selectively";
  return "quarantine";
}

function notesFor(item: Omit<WorktreeInventoryItem, "notes">): string[] {
  const notes: string[] = [];
  if (item.intakeDecision === "canonical-active") {
    notes.push("Canonical source root; finish and verify bounded changes here before promotion.");
  } else if (item.intakeDecision === "quarantine") {
    notes.push("Dirty sibling worktree; do not merge wholesale. Cherry-pick only reviewed files by lane.");
  } else {
    notes.push("Clean sibling worktree; still review patch scope before merge.");
  }
  if (item.categories["execution-live"] > 0) {
    notes.push("Contains execution/live files; require live-readiness and no-order dry verification before intake.");
  }
  if (item.categories["data"] > 0) {
    notes.push("Contains data changes; keep large/generated datasets out of source promotion unless explicitly required.");
  }
  if (item.categories["external-vendor"] > 0) {
    notes.push("Contains vendor/retired material; treat as reference unless a small adapter is extracted.");
  }
  return notes;
}

export async function buildWorktreeConsolidationReport(args: {
  repoRoot?: string;
  outputPath?: string;
  now?: () => string;
} = {}): Promise<WorktreeConsolidationReport> {
  const repoRoot = resolve(args.repoRoot ?? process.cwd());
  const outputPath = resolve(args.outputPath ?? DEFAULT_OUTPUT_PATH);
  const generatedAt = args.now?.() ?? new Date().toISOString();
  const rawWorktrees = await runGit(["worktree", "list", "--porcelain"], repoRoot);
  const worktreeRefs = parseGitWorktreeList(rawWorktrees);
  const worktrees: WorktreeInventoryItem[] = [];

  for (const ref of worktreeRefs) {
    const rawStatus = await runGit(["status", "--short", "--branch"], ref.path);
    const changes = parseStatus(rawStatus);
    const categories = emptyCategoryCounts();
    for (const change of changes) categories[change.category] += 1;
    const base = {
      path: ref.path,
      branch: ref.branch,
      head: ref.head,
      dirtyFiles: changes.length,
      categories,
      changes,
      intakeDecision: intakeDecision(ref.path, repoRoot, changes.length)
    };
    worktrees.push({ ...base, notes: notesFor(base) });
  }

  const report: WorktreeConsolidationReport = {
    command: "worktree-consolidation",
    generatedAt,
    outputPath,
    repoRoot,
    posture: "organized-blocked-for-live-money",
    worktrees,
    branchPolicy: [
      "Canonical root is /Users/brain/hedge until a clean trunk is explicitly chosen.",
      "Dirty sibling worktrees are evidence queues, not merge targets.",
      "Governance/risk changes can be reviewed first; execution/live changes require the strictest dry verification.",
      "Data, vendor, retired, and generated files stay out of source promotion unless a specific test needs them.",
      "No branch or worktree cleanup may delete user work without an explicit archive step and operator approval."
    ],
    intakeOrder: [
      "1. Finish current canonical changes and keep live/demo blocked until goal gates agree.",
      "2. Review sibling governance-risk files as selective cherry-pick candidates.",
      "3. Review strategy-research changes only when tied to OOS, bracket replay, or a failing current gate.",
      "4. Keep execution-live scripts quarantined until policy diff guard, no-order dry run, and adapter tests pass.",
      "5. Retire or archive vendor/generated/data dumps after a manifest records what was kept and why."
    ],
    hardRules: [
      "Do not run live order scripts from a dirty worktree.",
      "Do not merge any sibling worktree wholesale.",
      "Do not promote a strategy because a branch says it worked; require current artifacts.",
      "Do not let Hermes, n8n, or LLM agents route, size, promote, or widen risk.",
      "This audit submits no orders."
    ]
  };

  await mkdir(dirname(outputPath), { recursive: true });
  await writeFile(outputPath, `${JSON.stringify(report, null, 2)}\n`, "utf8");
  return report;
}
