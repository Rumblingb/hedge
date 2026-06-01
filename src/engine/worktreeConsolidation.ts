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

export interface WorktreeClearanceQueueItem {
  priority: number;
  lane: WorktreeFileCategory;
  dirtyFiles: number;
  sampleFiles: string[];
  action: string;
  requiredEvidence: string[];
}

export interface WorktreeLaneSummary {
  lane: WorktreeFileCategory;
  dirtyFiles: number;
  sampleFiles: string[];
  action: string;
  requiredEvidence: string[];
}

export interface CanonicalSourceSummary {
  path: string | null;
  branch: string | null;
  head: string | null;
  dirtyFiles: number;
  intakeDecision: WorktreeInventoryItem["intakeDecision"] | "missing";
  categories: Record<WorktreeFileCategory, number>;
  executionLiveFiles: string[];
  unknownFiles: string[];
  laneSummaries: WorktreeLaneSummary[];
}

export interface DirtySiblingWorktreeSummary {
  count: number;
  worktrees: Array<{
    path: string;
    branch: string | null;
    head: string | null;
    dirtyFiles: number;
    categories: Record<WorktreeFileCategory, number>;
    topFiles: string[];
    intakeDecision: WorktreeInventoryItem["intakeDecision"];
  }>;
}

export interface WorktreeConsolidationReport {
  command: "worktree-consolidation";
  generatedAt: string;
  outputPath: string;
  repoRoot: string;
  posture: "organized-blocked-for-live-money";
  canonicalSource: CanonicalSourceSummary;
  dirtySiblingWorktrees: DirtySiblingWorktreeSummary;
  worktrees: WorktreeInventoryItem[];
  sourceCleanBlockers: string[];
  clearanceQueue: WorktreeClearanceQueueItem[];
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
  if (path === ".gitignore") {
    return "ops-docs";
  }
  if (path.startsWith("tests/")) {
    if (
      path.startsWith("tests/test_bill_next_research_actions") ||
      path.startsWith("tests/test_bill_research_closed_loop_contract") ||
      path.startsWith("tests/test_sync_bill_obsidian")
    ) {
      return "governance-risk";
    }
    const subject = path.replace(/^tests\//, "src/");
    const subjectCategory = categorizeWorktreePath(subject);
    return subjectCategory === "unknown" ? "strategy-research" : subjectCategory;
  }
  if (
    path === "src/cli.ts" ||
    path === "src/config.ts" ||
    path === "src/domain.ts" ||
    path === "src/engine/autonomyStatus.ts" ||
    path === "src/engine/dashboardSnapshot.ts" ||
    path.startsWith("src/promotion/") ||
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
    path.startsWith("scripts/data_freshness_gate") ||
    path.startsWith("scripts/cftc_tff_positioning_ingest") ||
    path.startsWith("scripts/refresh_futures_research_data") ||
    path.startsWith("scripts/realtime_data_bridge") ||
    path.startsWith("scripts/realtime_data_preflight") ||
    path.startsWith("scripts/realtime_cron") ||
    path.startsWith("scripts/pipeline_monitor") ||
    path.includes("macro-context")
  ) {
    return "data";
  }
  if (
    path.startsWith("external/") ||
    path.startsWith("vendor/") ||
    path.startsWith("retired/") ||
    path.startsWith("research-repos") ||
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
    path === ".env.example" ||
    path.endsWith(".env.example") ||
    path.includes("/env/") ||
    path.endsWith(".plist.template") ||
    path.startsWith("docs/") ||
    path.endsWith(".md") ||
    path.startsWith("ops/mac-mini/README") ||
    path.startsWith("ops/mac-mini/launchd/README") ||
    path.endsWith("README.md")
  ) {
    return "ops-docs";
  }
  if (
    path.startsWith("scripts/master_bridge") ||
    path.startsWith("scripts/60m_exec_bridge") ||
    path.startsWith("scripts/pre_trade_check") ||
    path.startsWith("scripts/position_sizing_engine") ||
    path.startsWith("scripts/cron_position_sizing") ||
    path.startsWith("scripts/topstep") ||
    path.startsWith("scripts/verify_master_bridge_firewall") ||
    path.startsWith("scripts/verify_60m_exec_bridge_firewall") ||
    path.startsWith("scripts/verify_signal_router_firewall") ||
    path.startsWith("scripts/trade_journal") ||
    path.startsWith("scripts/pm_arb_scanner") ||
    path.startsWith("ops/mac-mini/bin/bill-pm-auto-execute-loop") ||
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
    path.startsWith("scripts/swap-and-fund") ||
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
    path.includes("worktreeConsolidation") ||
    path.includes("kill_switch") ||
    path.startsWith("scripts/bill_fund_os_completion_audit") ||
    path.startsWith("scripts/bill_next_research_actions") ||
    path.startsWith("scripts/bill_research_closed_loop_contract") ||
    path.startsWith("scripts/cron_state_validator") ||
    path.startsWith("scripts/sync_bill_obsidian") ||
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
    path.startsWith("src/utils/markets") ||
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
    path.startsWith("scripts/vol_regime_oos_replay") ||
    path.startsWith("scripts/backtrader_research_loop") ||
    path.startsWith("scripts/futures_cost_slippage_gate") ||
    path.startsWith("scripts/futures_evidence_triage") ||
    path.startsWith("scripts/futures_no_edge_ledger") ||
    path.startsWith("scripts/research_seed_triage") ||
    path === "backtrader_verify.py" ||
    path.startsWith("scripts/prediction-market-analysis-import") ||
    path.startsWith("scripts/verify_prediction_market_analysis_artifacts") ||
    path.startsWith("scripts/prediction_market_calibration_gate") ||
    path.startsWith("scripts/prediction_research_watchlist") ||
    path.startsWith("scripts/prediction_category_drilldown") ||
    path.startsWith("scripts/prediction_narrow_scan_runner") ||
    path.startsWith("scripts/prediction_evidence_triage") ||
    path.startsWith("scripts/prediction_resolved_outcome_join") ||
    path.startsWith("scripts/prediction_no_edge_ledger") ||
    path.startsWith("scripts/polymarket_clob_recorder") ||
    path.startsWith("scripts/polymarket_clob_persistence_lab") ||
    path.startsWith("scripts/polymarket_clob_edge_gate") ||
    path.startsWith("scripts/signal_quality_advisor") ||
    path.startsWith("scripts/probe-60m-signals") ||
    path.startsWith("ops/mac-mini/bin/60m-strategy-eval-shadow") ||
    path.startsWith("scripts/dom_proxy_ohlcv") ||
    path.startsWith("scripts/kalman_pairs") ||
    path.startsWith("scripts/whale_flow_signal") ||
    path.startsWith("scripts/rolling_window_optimizer") ||
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

function buildSourceCleanBlockers(worktrees: WorktreeInventoryItem[], repoRoot: string): string[] {
  const blockers: string[] = [];
  const canonical = worktrees.find((item) => resolve(item.path) === resolve(repoRoot));
  if (!canonical) {
    blockers.push("canonical source root was not found in git worktree list");
    return blockers;
  }
  if (canonical.dirtyFiles > 0) {
    blockers.push(`canonical source root has ${canonical.dirtyFiles} dirty files`);
  }
  if (canonical.categories["execution-live"] > 0) {
    blockers.push(`canonical source root has ${canonical.categories["execution-live"]} dirty execution/live files`);
  }
  if (canonical.categories.unknown > 0) {
    blockers.push(`canonical source root has ${canonical.categories.unknown} unclassified dirty files`);
  }
  const quarantined = worktrees.filter((item) => item.intakeDecision === "quarantine");
  if (quarantined.length > 0) {
    blockers.push(`${quarantined.length} dirty sibling worktree(s) remain quarantine/selective-intake only`);
  }
  return blockers;
}

function clearancePlanFor(
  category: WorktreeFileCategory,
  dirtyFiles: number,
  sampleFiles: string[]
): Omit<WorktreeClearanceQueueItem, "priority" | "lane" | "dirtyFiles" | "sampleFiles"> {
  switch (category) {
    case "governance-risk":
      return {
        action: "Review first as the control-plane lane; keep execution locked while verifying gates and Obsidian sync.",
        requiredEvidence: [
          "npm run --silent typecheck",
          "npm run --silent test",
          "npm run --silent bill:live-readiness-gate || true",
          "npm run --silent bill:obsidian-sync"
        ]
      };
    case "execution-live":
      return {
        action: "Keep quarantined until every route, adapter, and bridge change passes no-order firewall checks.",
        requiredEvidence: [
          "npm run --silent bill:verify-master-bridge-firewall",
          "npm run --silent bill:verify-60m-bridge-firewall",
          "npm run --silent bill:verify-topstep-demo-bridge-firewall",
          "npm run --silent bill:verify-signal-router-firewall",
          "npm run --silent bill:verify-prediction-funding-firewall",
          "BILL_ENABLE_FUTURES_DEMO_EXECUTION=false and RH_TOPSTEP_READ_ONLY=true"
        ]
      };
    case "strategy-research":
      return {
        action: "Promote only strategy work tied to current OOS, walk-forward, slippage, or shadow evidence.",
        requiredEvidence: [
          "npm run --silent bill:research-seed-triage",
          "npm run --silent bill:strategy-zoo-audit",
          "npm run --silent bill:walkforward-matrix",
          "npm run --silent bill:futures-evidence-triage",
          "npm run --silent bill:prediction-evidence-triage"
        ]
      };
    case "data":
      return {
        action: "Manifest datasets and freshness; do not commit large/generated market data unless explicitly required.",
        requiredEvidence: [
          "npm run --silent data-quality <dataset>",
          "npm run --silent bill:data-freshness-gate",
          "npm run --silent bill:realtime-data-preflight || true",
          "npm run --silent bill:cftc-tff-positioning || true",
          "dataset source, timestamp, symbol universe, and fallback status recorded in Obsidian"
        ]
      };
    case "dependencies":
      return {
        action: "Audit package changes separately; dependency drift must be justified by a tool or data-source need.",
        requiredEvidence: [
          "npm install --package-lock-only only if dependency set intentionally changed",
          "npm run --silent typecheck",
          "npm run --silent test"
        ]
      };
    case "ops-docs":
      return {
        action: "Consolidate useful docs into Obsidian indexes; retire duplicate README claims that lack current artifacts.",
        requiredEvidence: [
          "npm run --silent bill:obsidian-sync",
          "updated Research-Catalog or Agent-Hermes index links",
          "status label: active, candidate, research-only, quarantine, or retired"
        ]
      };
    case "external-vendor":
      return {
        action: "Treat as reference material; extract small adapters or notes rather than merging vendor trees.",
        requiredEvidence: [
          "resource inventory entry with upstream path/source",
          "local adapter test if code is imported",
          "no vendor tree staged into the canonical source lane"
        ]
      };
    case "generated-cache":
      return {
        action: "Keep as machine evidence only; never use generated state files as source-clean promotion material.",
        requiredEvidence: [
          "state artifact linked from Obsidian if useful",
          "source diff excludes generated cache files"
        ]
      };
    case "unknown":
      return {
        action: "Classify before promotion; unknown dirty files block source-clean readiness.",
        requiredEvidence: [
          "add explicit category rule or archive note",
          "rerun npm run --silent bill:worktree-consolidation"
        ]
      };
  }
}

function buildClearanceQueue(worktrees: WorktreeInventoryItem[]): WorktreeClearanceQueueItem[] {
  const canonical = worktrees.find((item) => item.intakeDecision === "canonical-active");
  if (!canonical) return [];
  const priorities: Record<WorktreeFileCategory, number> = {
    "governance-risk": 1,
    "execution-live": 2,
    "strategy-research": 3,
    data: 4,
    dependencies: 5,
    "ops-docs": 6,
    "external-vendor": 7,
    "generated-cache": 8,
    unknown: 9
  };
  return ALL_CATEGORIES
    .filter((category) => canonical.categories[category] > 0)
    .map((category) => {
      const sampleFiles = canonical.changes
        .filter((change) => change.category === category)
        .slice(0, 8)
        .map((change) => change.path);
      const plan = clearancePlanFor(category, canonical.categories[category], sampleFiles);
      return {
        priority: priorities[category],
        lane: category,
        dirtyFiles: canonical.categories[category],
        sampleFiles,
        ...plan
      };
    })
    .sort((a, b) => a.priority - b.priority);
}

function buildCanonicalSourceSummary(worktrees: WorktreeInventoryItem[], repoRoot: string): CanonicalSourceSummary {
  const canonical = worktrees.find((item) => resolve(item.path) === resolve(repoRoot));
  if (!canonical) {
    return {
      path: null,
      branch: null,
      head: null,
      dirtyFiles: 0,
      intakeDecision: "missing",
      categories: emptyCategoryCounts(),
      executionLiveFiles: [],
      unknownFiles: [],
      laneSummaries: []
    };
  }
  const clearanceQueue = buildClearanceQueue(worktrees);
  return {
    path: canonical.path,
    branch: canonical.branch,
    head: canonical.head,
    dirtyFiles: canonical.dirtyFiles,
    intakeDecision: canonical.intakeDecision,
    categories: canonical.categories,
    executionLiveFiles: canonical.changes
      .filter((change) => change.category === "execution-live")
      .slice(0, 20)
      .map((change) => change.path),
    unknownFiles: canonical.changes
      .filter((change) => change.category === "unknown")
      .slice(0, 20)
      .map((change) => change.path),
    laneSummaries: clearanceQueue.map((item) => ({
      lane: item.lane,
      dirtyFiles: item.dirtyFiles,
      sampleFiles: item.sampleFiles,
      action: item.action,
      requiredEvidence: item.requiredEvidence
    }))
  };
}

function buildDirtySiblingWorktreeSummary(worktrees: WorktreeInventoryItem[]): DirtySiblingWorktreeSummary {
  const quarantined = worktrees.filter((item) => item.intakeDecision === "quarantine");
  return {
    count: quarantined.length,
    worktrees: quarantined.map((item) => ({
      path: item.path,
      branch: item.branch,
      head: item.head,
      dirtyFiles: item.dirtyFiles,
      categories: item.categories,
      topFiles: item.changes.slice(0, 12).map((change) => change.path),
      intakeDecision: item.intakeDecision
    }))
  };
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
    canonicalSource: buildCanonicalSourceSummary(worktrees, repoRoot),
    dirtySiblingWorktrees: buildDirtySiblingWorktreeSummary(worktrees),
    worktrees,
    sourceCleanBlockers: buildSourceCleanBlockers(worktrees, repoRoot),
    clearanceQueue: buildClearanceQueue(worktrees),
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
