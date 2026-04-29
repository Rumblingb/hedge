import { randomUUID } from "node:crypto";
import { mkdir, readFile, stat, writeFile } from "node:fs/promises";
import { existsSync } from "node:fs";
import os from "node:os";
import { dirname, join, resolve } from "node:path";
import { buildOllamaConfigFromEnv, embed, type OllamaConfig } from "../llm/ollama.js";
import { resolveRepoPathFromRoot } from "../utils/runtimePaths.js";
import {
  appendCorpusChunks,
  buildChunk,
  chunkText,
  corpusStats,
  readCorpusChunks,
  readManifest,
  resolveCorpusPaths,
  writeManifest,
  type CorpusChunk,
  type CorpusPaths
} from "./corpus.js";
import {
  buildCrawlerConfigFromEnv,
  digestGithubRepo,
  firecrawlHealthy,
  scrape,
  searchArxiv,
  type CrawlerConfig
} from "./crawler.js";
import { DEFAULT_THRESHOLDS, runFilterPipeline, type FilterDecision, type FilterThresholds } from "./filter.js";
import { writeStrategyHypothesisArtifacts, type StrategyHypothesis } from "./strategyHypotheses.js";
import { collectYouTubeTranscriptTarget, isYouTubeTarget } from "./youtube.js";

const DEFAULT_LATEST_REPORT_PATH = ".rumbling-hedge/research/researcher/latest-run.json";
const DEFAULT_RUN_REPORTS_DIR = ".rumbling-hedge/research/researcher/runs";
const DEFAULT_TARGET_STATE_PATH = ".rumbling-hedge/research/researcher/target-state.json";

export interface ResearcherPolicy {
  version: number;
  budgets: {
    dailyCrawlBudget: number;
    maxCorpusGb: number;
    maxConcurrentBrowsers: number;
    heartbeatMinutes: number;
    maxSftRunsPerWeek?: number;
  };
  quality: FilterThresholds & {
    minhashNgram?: number;
  };
  allowedDomains: string[];
  llm: {
    generateModel: string;
    embedModel: string;
    judgeModel: string;
    baseUrl: string;
  };
  eval: {
    evalThreshold: number;
    goldenPromptsPath: string;
  };
}

export interface Target {
  id: string;
  kind: "web" | "github-repo" | "arxiv-query" | "youtube-transcript";
  url?: string;
  query?: string;
  enabled?: boolean;
  priority?: number;
  cadence?: string;
  rationale?: string;
  limit?: number;
  tags?: string[];
  videos?: string[];
  language?: string;
}

export interface ResearcherRunInput {
  policyPath?: string;
  targetsPath?: string;
  targetIds?: string[];
  maxTargets?: number;
  skipJudge?: boolean;
  skipEmbed?: boolean;
  corpusPaths?: CorpusPaths;
  ollamaConfig?: OllamaConfig;
  crawlerConfig?: CrawlerConfig;
  workspaceRoot?: string;
  latestReportPath?: string;
  reportRunsDir?: string;
}

export interface ResearcherRunReport {
  runId: string;
  startedAt: string;
  finishedAt: string;
  targetsAttempted: number;
  targetsSucceeded: number;
  chunksCollected: number;
  rawChunksCollected?: number;
  novelChunksCollected?: number;
  chunksKept: number;
  chunksRejected: number;
  dedupRate: number;
  firecrawlUsed: boolean;
  judgeCalls: number;
  topKeptTitles: string[];
  strategyHypothesesCount: number;
  topStrategyHypotheses: string[];
  strategyArtifactPath?: string;
  transcriptArtifactsDeleted: number;
  rejectionSummary?: Array<{
    stage: FilterDecision["stage"] | "budget";
    reason: string;
    count: number;
  }>;
  topRejectedChunks?: Array<{
    targetId: string;
    title?: string;
    stage: FilterDecision["stage"] | "budget";
    reason: string;
    classifierScore?: number;
    judgeScore?: number;
    tags?: string[];
  }>;
  budgetRemaining: number;
  status?: "healthy" | "degraded";
  nextAction?: string;
  blockers?: string[];
  summaryLines?: string[];
  corpusStats: ReturnType<typeof corpusStats>;
  targetResults: Array<{
    targetId: string;
    kind: string;
    collected: number;
    kept: number;
    rejected: number;
    videosProcessed?: number;
    error?: string;
  }>;
}

interface TargetRunState {
  targets: Record<string, {
    lastAttemptedAt?: string;
    lastSucceededAt?: string;
    attempts?: number;
    successes?: number;
  }>;
}

export interface ResearcherWorkspacePaths {
  root: string;
  outbox: string;
  memoryDir: string;
}

function defaultResearcherWorkspaceRoot(env: NodeJS.ProcessEnv = process.env): string {
  return resolve(env.RESEARCHER_WORKSPACE_ROOT ?? join(env.OPENCLAW_HOME ?? join(os.homedir(), ".openclaw"), "workspace-researcher"));
}

function defaultPolicyPath(env: NodeJS.ProcessEnv = process.env): string {
  return resolve(env.RESEARCHER_POLICY_PATH ?? join(defaultResearcherWorkspaceRoot(env), "policy.json"));
}

function defaultTargetsPath(env: NodeJS.ProcessEnv = process.env): string {
  if (env.RESEARCHER_TARGETS_PATH) {
    return resolve(env.RESEARCHER_TARGETS_PATH);
  }
  const workspacePath = resolve(join(defaultResearcherWorkspaceRoot(env), "targets.json"));
  if (existsSync(workspacePath)) {
    return workspacePath;
  }
  const billTargets = resolveRepoPathFromRoot({
    importMetaUrl: import.meta.url,
    path: "config/researcher-targets.bill.json",
    cwd: process.cwd(),
    env
  });
  if (existsSync(billTargets)) {
    return billTargets;
  }
  return workspacePath;
}

function parsePositiveNumber(value: unknown, fallback: number): number {
  if (typeof value === "number" && Number.isFinite(value) && value > 0) return value;
  if (typeof value === "string") {
    const parsed = Number.parseFloat(value);
    if (Number.isFinite(parsed) && parsed > 0) return parsed;
  }
  return fallback;
}

function parseStringArray(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === "string" && item.trim().length > 0) : [];
}

function normalizeQuality(value: unknown): ResearcherPolicy["quality"] {
  const raw = (value ?? {}) as Record<string, unknown>;
  return {
    minChars: parsePositiveNumber(raw.minChars ?? raw.minChunkChars, DEFAULT_THRESHOLDS.minChars),
    maxChars: parsePositiveNumber(raw.maxChars ?? raw.maxChunkChars, DEFAULT_THRESHOLDS.maxChars),
    minhashThreshold: parsePositiveNumber(raw.minhashThreshold, DEFAULT_THRESHOLDS.minhashThreshold),
    classifierMinScore: parsePositiveNumber(raw.classifierMinScore, DEFAULT_THRESHOLDS.classifierMinScore),
    judgeTopFraction: parsePositiveNumber(raw.judgeTopFraction, DEFAULT_THRESHOLDS.judgeTopFraction),
    classifierSample: parsePositiveNumber(raw.classifierSample, DEFAULT_THRESHOLDS.classifierSample),
    minhashNgram: parsePositiveNumber(raw.minhashNgram, 5)
  };
}

export async function loadPolicy(path?: string, env: NodeJS.ProcessEnv = process.env): Promise<ResearcherPolicy> {
  const raw = JSON.parse(await readFile(resolve(path ?? defaultPolicyPath(env)), "utf8")) as Record<string, unknown>;
  const budgets = (raw.budgets ?? {}) as Record<string, unknown>;
  const llm = (raw.llm ?? {}) as Record<string, unknown>;
  const evalConfig = (raw.eval ?? {}) as Record<string, unknown>;
  return {
    version: typeof raw.version === "number" ? raw.version : 1,
    budgets: {
      dailyCrawlBudget: parsePositiveNumber(budgets.dailyCrawlBudget, 500),
      maxCorpusGb: parsePositiveNumber(budgets.maxCorpusGb, 20),
      maxConcurrentBrowsers: parsePositiveNumber(budgets.maxConcurrentBrowsers, 3),
      heartbeatMinutes: parsePositiveNumber(budgets.heartbeatMinutes, 60),
      maxSftRunsPerWeek: parsePositiveNumber(budgets.maxSftRunsPerWeek, 1)
    },
    quality: normalizeQuality(raw.quality),
    allowedDomains: parseStringArray(raw.allowedDomains),
    llm: {
      generateModel: typeof llm.generateModel === "string" ? llm.generateModel : "qwen2.5-coder:14b",
      embedModel: typeof llm.embedModel === "string" ? llm.embedModel : "nomic-embed-text:latest",
      judgeModel: typeof llm.judgeModel === "string" ? llm.judgeModel : "qwen2.5-coder:14b",
      baseUrl: typeof llm.baseUrl === "string" ? llm.baseUrl : "http://localhost:11434"
    },
    eval: {
      evalThreshold: parsePositiveNumber(evalConfig.evalThreshold, 200),
      goldenPromptsPath:
        typeof evalConfig.goldenPromptsPath === "string"
          ? evalConfig.goldenPromptsPath
          : `${defaultResearcherWorkspaceRoot(env)}/eval/golden-prompts.jsonl`
    }
  };
}

export async function loadTargets(path?: string, env: NodeJS.ProcessEnv = process.env): Promise<Target[]> {
  const raw = JSON.parse(await readFile(resolve(path ?? defaultTargetsPath(env)), "utf8")) as { targets: Target[] };
  return raw.targets.filter((target) => target.enabled !== false);
}

export function resolveResearcherWorkspacePaths(root?: string, env: NodeJS.ProcessEnv = process.env): ResearcherWorkspacePaths {
  const resolvedRoot = resolve(root ?? defaultResearcherWorkspaceRoot(env));
  return {
    root: resolvedRoot,
    outbox: resolve(resolvedRoot, "OUTBOX.md"),
    memoryDir: resolve(resolvedRoot, "memory")
  };
}

function buildResearcherOutboxEntry(report: ResearcherRunReport): string {
  const titles = report.topKeptTitles.length > 0 ? report.topKeptTitles.join("; ") : "none";
  const strategies = report.topStrategyHypotheses.length > 0 ? report.topStrategyHypotheses.join("; ") : "none";
  const status = report.status ?? "healthy";
  return `- ${report.finishedAt.slice(0, 10)} ${report.finishedAt.slice(11, 16)}Z — run ${report.runId} — ${status}, targets ${report.targetsSucceeded}/${report.targetsAttempted}, kept ${report.chunksKept}, strategies ${report.strategyHypothesesCount}, rejected ${report.chunksRejected}, dedup ${(report.dedupRate * 100).toFixed(1)}%, budget ${report.budgetRemaining}. Top kept: ${titles}. Strategy feed: ${strategies}`;
}

function buildResearcherRunState(report: Omit<ResearcherRunReport, "status" | "nextAction" | "blockers" | "summaryLines">): Pick<ResearcherRunReport, "status" | "nextAction" | "blockers" | "summaryLines"> {
  const targetErrors = report.targetResults
    .filter((result) => typeof result.error === "string" && result.error.length > 0)
    .map((result) => `${result.targetId}: ${result.error}`);
  const noNovelChunks = report.targetsSucceeded > 0 && report.chunksCollected === 0;
  const noRetainedChunks = report.chunksCollected > 0 && report.chunksKept === 0;
  const firecrawlWeakSpot = !report.firecrawlUsed;
  const topRejection = report.rejectionSummary?.[0];
  const topRejectionNote = topRejection
    ? `${topRejection.stage}: ${topRejection.reason} (${topRejection.count})`
    : undefined;
  const blockers = [
    ...targetErrors,
    ...(report.targetsSucceeded === 0 ? ["No researcher targets succeeded in the latest run."] : []),
    ...(noNovelChunks ? ["Selected researcher targets yielded no novel chunks in the latest run."] : []),
    ...(noRetainedChunks ? ["Researcher found novel material but retained no durable chunks in the latest run."] : [])
  ];
  const status = blockers.length > 0 ? "degraded" : "healthy";
  const nextAction = targetErrors[0]
    ? `Fix failing researcher targets before widening scope: ${targetErrors[0]}`
    : noNovelChunks
      ? "Refresh the target list; the latest run only hit already-covered material."
      : noRetainedChunks
      ? topRejectionNote
        ? `Review rejection diagnostics before loosening filters: ${topRejectionNote}.`
        : "Refresh the target list or loosen filtering; the latest run kept no chunks."
      : firecrawlWeakSpot
        ? "Restore Firecrawl access or keep researcher targets biased toward static-friendly sources."
        : "Keep ingesting and curate the next highest-priority researcher targets.";
  const summaryLines = [
    `status=${status}`,
    `targets=${report.targetsSucceeded}/${report.targetsAttempted}`,
    `chunks=${report.chunksKept}/${report.chunksCollected}`,
    `strategies=${report.strategyHypothesesCount}`,
    `firecrawl=${report.firecrawlUsed ? "available" : "unavailable"}`,
    `next=${nextAction}`
  ];

  return {
    status,
    nextAction,
    blockers,
    summaryLines
  };
}

function truncateForReport(value: string | undefined, limit: number): string | undefined {
  if (!value) return undefined;
  return value.length <= limit ? value : `${value.slice(0, limit - 1)}…`;
}

function buildRejectionSummary(rejected: FilterDecision[], budgetRejected: number): ResearcherRunReport["rejectionSummary"] {
  const counts = new Map<string, { stage: FilterDecision["stage"] | "budget"; reason: string; count: number }>();
  for (const decision of rejected) {
    const key = `${decision.stage}:${decision.reason}`;
    const current = counts.get(key);
    if (current) {
      current.count += 1;
    } else {
      counts.set(key, { stage: decision.stage, reason: decision.reason, count: 1 });
    }
  }
  if (budgetRejected > 0) {
    counts.set("budget:corpus-budget", { stage: "budget", reason: "corpus-budget", count: budgetRejected });
  }
  return [...counts.values()].sort((a, b) => b.count - a.count || a.stage.localeCompare(b.stage)).slice(0, 10);
}

function buildTopRejectedChunks(rejected: FilterDecision[]): ResearcherRunReport["topRejectedChunks"] {
  return [...rejected]
    .sort((a, b) => (b.chunk.classifierScore ?? -1) - (a.chunk.classifierScore ?? -1))
    .slice(0, 10)
    .map((decision) => ({
      targetId: decision.chunk.sourceId,
      title: truncateForReport(decision.chunk.title, 160),
      stage: decision.stage,
      reason: truncateForReport(decision.reason, 240) ?? decision.reason,
      classifierScore: decision.chunk.classifierScore,
      judgeScore: decision.chunk.judgeScore,
      tags: decision.chunk.tags?.slice(0, 8)
    }));
}

const RESEARCHER_TARGET_TOPIC_MAP: Record<string, string[]> = {
  prediction: ["prediction markets", "market settlement", "market liquidity"],
  "market-making": ["market making", "order book liquidity", "bid-ask spreads"],
  "crypto-liquid": ["crypto market microstructure", "bitcoin intraday direction", "short-horizon crypto pricing"],
  "short-horizon": ["short-horizon prediction markets", "intraday directional pricing", "microstructure timing"],
  "volatility-targeting": ["volatility targeting", "inverse volatility scaling", "risk targeting"],
  "execution-alpha": ["execution quality", "price improvement", "inventory-aware quoting"],
  liquidity: ["market liquidity", "order book depth", "execution quality"],
  "futures-core": ["futures execution", "futures microstructure", "roll and settlement"],
  microstructure: ["market microstructure", "order flow", "price impact"],
  "order-flow": ["order flow", "execution quality", "liquidity"],
  backtest: ["strategy backtesting", "transaction costs", "strategy evaluation"],
  oos: ["walk-forward validation", "out-of-sample robustness", "overfitting control"],
  "risk-review": ["risk management", "drawdown control", "transaction costs"],
  "macro-rates": ["macro rates", "inflation releases", "yield curve"],
  "event-driven": ["event-driven trading", "earnings surprises", "macro announcements"],
  "trend-following": ["trend following", "time-series momentum", "managed futures"],
  carry: ["carry", "roll yield", "term structure"],
  "market-neutral": ["market neutral", "relative value", "statistical arbitrage"],
  dispersion: ["options dispersion", "index-single-name correlation", "volatility relative value"],
  "options-us": ["options microstructure", "implied volatility", "options liquidity"],
  volatility: ["volatility forecasting", "implied volatility", "realized volatility"],
  crawler: ["finance data collection", "source provenance"],
  docs: ["trading system documentation", "execution runbooks"]
};

const DEFAULT_RESEARCHER_TOPICS = [
  "prediction markets",
  "market microstructure",
  "futures execution",
  "walk-forward validation"
];

function normalizeResearchTopicKey(value: string): string {
  return value.toLowerCase().trim();
}

function inferTopicsFromQuery(query: string): string[] {
  const normalized = normalizeResearchTopicKey(query).replace(/[^a-z0-9\s-]/g, " ");
  const inferred = new Set<string>();

  if (/(prediction|kalshi|polymarket|forecast)/.test(normalized)) {
    inferred.add("prediction markets");
  }
  if (/(bitcoin|btc|ethereum|eth|crypto|perpetual|funding rate)/.test(normalized)) {
    inferred.add("crypto market microstructure");
  }
  if (/(5[\s-]?minute|15[\s-]?minute|intraday|short[\s-]?horizon|up or down)/.test(normalized)) {
    inferred.add("short-horizon prediction markets");
  }
  if (/(0dte|1dte|short[\s-]?dated|same day expiring|straddle|iron condor|gamma scalp)/.test(normalized)) {
    inferred.add("options microstructure");
    inferred.add("volatility forecasting");
  }
  if (/(volatility targeting|target volatility|inverse volatility scaling|vol control|volatility scaling)/.test(normalized)) {
    inferred.add("volatility targeting");
  }
  if (/(microstructure|order book|liquidity|market making|bid ask|spread)/.test(normalized)) {
    inferred.add("market microstructure");
  }
  if (/(futures|contract|roll)/.test(normalized)) {
    inferred.add("futures execution");
  }
  if (/(walk[\s-]?forward|out[\s-]?of[\s-]?sample|overfit|robust)/.test(normalized)) {
    inferred.add("walk-forward validation");
  }
  if (/(event[\s-]?driven|earnings|announcement|macro)/.test(normalized)) {
    inferred.add("event-driven trading");
  }
  if (/(macro|rates|yield|inflation|cpi|fomc|payroll)/.test(normalized)) {
    inferred.add("macro rates");
  }
  if (/(trend[\s-]?following|time[\s-]?series momentum|managed futures|cta)/.test(normalized)) {
    inferred.add("trend following");
  }
  if (/(carry|roll yield|term structure|yield differential|forward premium)/.test(normalized)) {
    inferred.add("carry");
  }
  if (/(market neutral|relative value|statistical arbitrage|stat[\s-]?arb|pair trading)/.test(normalized)) {
    inferred.add("market neutral");
  }
  if (/(dispersion|correlation trading|index options|single stock options)/.test(normalized)) {
    inferred.add("options dispersion");
  }
  if (/(option|volatility|implied vol|surface|gamma|delta|vega)/.test(normalized)) {
    inferred.add("options and volatility");
  }
  if (/(execution|slippage|fill|market making|price improvement|inventory risk)/.test(normalized)) {
    inferred.add("execution quality");
  }

  return [...inferred];
}

function tokenizeResearchQuery(value: string): string[] {
  const stopWords = new Set([
    "and",
    "or",
    "the",
    "for",
    "with",
    "from",
    "into",
    "using",
    "strategy",
    "strategies",
    "trading",
    "market",
    "markets"
  ]);
  return value
    .toLowerCase()
    .replace(/[^a-z0-9\s-]/g, " ")
    .split(/\s+/)
    .map((word) => word.trim())
    .filter((word) => word.length >= 4 && !stopWords.has(word));
}

function arxivEntryMatchesTarget(args: {
  entry: Awaited<ReturnType<typeof searchArxiv>>[number];
  query: string;
  tags?: string[];
}): boolean {
  const text = `${args.entry.title} ${args.entry.summary}`.toLowerCase();
  const queryTokens = tokenizeResearchQuery(args.query);
  const queryHits = queryTokens.filter((token) => text.includes(token)).length;
  const topicPhrases = buildResearcherTopicList([{
    id: "arxiv-relevance-probe",
    kind: "arxiv-query",
    query: args.query,
    tags: args.tags
  }]).map((phrase) => phrase.toLowerCase());
  const topicHits = topicPhrases.filter((phrase) => text.includes(phrase)).length;

  return queryHits >= 2 || (queryHits >= 1 && topicHits >= 1) || topicHits >= 2;
}

function buildResearcherTopicList(targets: Target[]): string[] {
  const topics = new Set<string>();

  for (const target of targets) {
    for (const tag of target.tags ?? []) {
      const mapped = RESEARCHER_TARGET_TOPIC_MAP[normalizeResearchTopicKey(tag)] ?? [];
      for (const topic of mapped) {
        topics.add(topic);
      }
    }
    if (target.query) {
      for (const topic of inferTopicsFromQuery(target.query)) {
        topics.add(topic);
      }
    }
  }

  return topics.size > 0 ? [...topics].slice(0, 8) : DEFAULT_RESEARCHER_TOPICS;
}

export async function writeResearcherWorkspaceArtifacts(
  report: ResearcherRunReport,
  args: {
    workspaceRoot?: string;
    latestReportPath?: string;
    reportRunsDir?: string;
  } = {}
): Promise<{
  latestReportPath: string;
  runReportPath: string;
  outboxPath: string;
}> {
  const workspace = resolveResearcherWorkspacePaths(args.workspaceRoot);
  const latestReportPath = resolveRepoPathFromRoot({
    importMetaUrl: import.meta.url,
    path: args.latestReportPath ?? DEFAULT_LATEST_REPORT_PATH,
    cwd: process.cwd(),
    env: process.env
  });
  const reportRunsDir = resolveRepoPathFromRoot({
    importMetaUrl: import.meta.url,
    path: args.reportRunsDir ?? DEFAULT_RUN_REPORTS_DIR,
    cwd: process.cwd(),
    env: process.env
  });
  const runReportPath = resolve(reportRunsDir, `${report.runId}.json`);

  await mkdir(dirname(latestReportPath), { recursive: true });
  await mkdir(reportRunsDir, { recursive: true });
  await writeFile(latestReportPath, `${JSON.stringify(report, null, 2)}\n`, "utf8");
  await writeFile(runReportPath, `${JSON.stringify(report, null, 2)}\n`, "utf8");

  await mkdir(dirname(workspace.outbox), { recursive: true });
  const header = "# OUTBOX\n\nCompact, founder-facing run summaries. Most recent first. Keep each entry under 8 lines.\n\n---\n";
  const existing = await readFile(workspace.outbox, "utf8").catch(() => "");
  const body = existing.includes("---") ? existing.slice(existing.indexOf("---") + 3).trim() : existing.trim();
  const nextLines = [buildResearcherOutboxEntry(report)];
  if (body.length > 0) nextLines.push(body);
  await writeFile(workspace.outbox, `${header}\n${nextLines.join("\n")}\n`, "utf8");

  await mkdir(workspace.memoryDir, { recursive: true });
  await writeFile(
    resolve(workspace.memoryDir, `${report.finishedAt.slice(0, 10)}-${report.runId}.md`),
    [
      `# Researcher Run ${report.runId}`,
      "",
      `- Started: ${report.startedAt}`,
      `- Finished: ${report.finishedAt}`,
      `- Targets: ${report.targetsSucceeded}/${report.targetsAttempted}`,
      `- Chunks kept/rejected: ${report.chunksKept}/${report.chunksRejected}`,
      `- Strategy hypotheses: ${report.strategyHypothesesCount}`,
      `- Dedup rate: ${(report.dedupRate * 100).toFixed(1)}%`,
      `- Transcript artifacts deleted: ${report.transcriptArtifactsDeleted}`,
      `- Firecrawl available: ${report.firecrawlUsed}`,
      `- Judge calls: ${report.judgeCalls}`,
      `- Status: ${report.status ?? "healthy"}`,
      `- Next action: ${report.nextAction ?? "keep ingesting"}`,
      `- Blockers: ${report.blockers?.join("; ") || "none"}`,
      `- Top kept titles: ${report.topKeptTitles.join("; ") || "none"}`,
      `- Top strategy hypotheses: ${report.topStrategyHypotheses.join("; ") || "none"}`,
      `- Rejection summary: ${report.rejectionSummary?.map((item) => `${item.stage}:${item.reason} x${item.count}`).join("; ") || "none"}`,
      `- Top rejected chunks: ${report.topRejectedChunks?.map((item) => `${item.targetId}:${item.stage}:${item.title ?? "untitled"}`).join("; ") || "none"}`,
      `- Strategy artifact: ${report.strategyArtifactPath ?? "none"}`
    ].join("\n"),
    "utf8"
  );

  return { latestReportPath, runReportPath, outboxPath: workspace.outbox };
}

export async function readLatestResearcherRunReport(path: string = DEFAULT_LATEST_REPORT_PATH): Promise<ResearcherRunReport | null> {
  try {
    const resolvedPath = resolveRepoPathFromRoot({
      importMetaUrl: import.meta.url,
      path,
      cwd: process.cwd(),
      env: process.env
    });
    return JSON.parse(await readFile(resolvedPath, "utf8")) as ResearcherRunReport;
  } catch {
    return null;
  }
}

function matchesAllowed(url: string, allowed: string[]): boolean {
  try {
    const host = new URL(url).hostname;
    return allowed.some((d) => host === d || host.endsWith(`.${d}`));
  } catch {
    return false;
  }
}

function compareTargetSelection(left: Target, right: Target, existingSourceCounts: Map<string, number>): number {
  const leftCoverage = existingSourceCounts.get(left.id) ?? 0;
  const rightCoverage = existingSourceCounts.get(right.id) ?? 0;
  const leftCovered = leftCoverage > 0;
  const rightCovered = rightCoverage > 0;
  if (leftCovered !== rightCovered) {
    return leftCovered ? 1 : -1;
  }
  const priorityDelta = (left.priority ?? 5) - (right.priority ?? 5);
  if (priorityDelta !== 0) {
    return priorityDelta;
  }
  if (leftCoverage !== rightCoverage) {
    return leftCoverage - rightCoverage;
  }
  return left.id.localeCompare(right.id);
}

function targetStatePath(): string {
  return resolve(process.env.BILL_RESEARCHER_TARGET_STATE_PATH ?? DEFAULT_TARGET_STATE_PATH);
}

async function readTargetRunState(): Promise<TargetRunState> {
  try {
    return JSON.parse(await readFile(targetStatePath(), "utf8")) as TargetRunState;
  } catch {
    return { targets: {} };
  }
}

async function writeTargetRunState(state: TargetRunState): Promise<void> {
  const pathname = targetStatePath();
  await mkdir(dirname(pathname), { recursive: true });
  await writeFile(pathname, `${JSON.stringify(state, null, 2)}\n`, "utf8");
}

function cadenceMs(cadence: string | undefined): number {
  switch ((cadence ?? "").toLowerCase()) {
    case "hourly":
      return 60 * 60 * 1000;
    case "daily":
      return 24 * 60 * 60 * 1000;
    case "weekly":
      return 7 * 24 * 60 * 60 * 1000;
    case "monthly":
      return 28 * 24 * 60 * 60 * 1000;
    default:
      return 0;
  }
}

function targetDue(target: Target, state: TargetRunState, nowMs: number): boolean {
  const cadence = cadenceMs(target.cadence);
  if (cadence <= 0) {
    return true;
  }
  const last = state.targets[target.id]?.lastAttemptedAt;
  if (!last) {
    return true;
  }
  return nowMs - Date.parse(last) >= cadence;
}

async function fileSize(pathname: string): Promise<number> {
  try {
    return (await stat(pathname)).size;
  } catch {
    return 0;
  }
}

function selectChunksWithinCorpusBudget(args: {
  chunks: CorpusChunk[];
  currentBytes: number;
  maxCorpusGb: number;
}): { kept: CorpusChunk[]; rejectedForBudget: number } {
  const maxBytes = Math.max(0, args.maxCorpusGb) * 1024 * 1024 * 1024;
  if (maxBytes <= 0) {
    return { kept: [], rejectedForBudget: args.chunks.length };
  }
  let nextBytes = args.currentBytes;
  const kept: CorpusChunk[] = [];
  for (const chunk of args.chunks) {
    const encodedBytes = Buffer.byteLength(`${JSON.stringify(chunk)}\n`, "utf8");
    if (nextBytes + encodedBytes > maxBytes) {
      continue;
    }
    kept.push(chunk);
    nextBytes += encodedBytes;
  }
  return { kept, rejectedForBudget: args.chunks.length - kept.length };
}

async function collectFromTarget(
  target: Target,
  runId: string,
  crawlerConfig: CrawlerConfig,
  policy: ResearcherPolicy
): Promise<{
  chunks: CorpusChunk[];
  hypotheses: StrategyHypothesis[];
  transcriptArtifactsDeleted: number;
  videosProcessed?: number;
}> {
  if (isYouTubeTarget(target)) {
    return collectYouTubeTranscriptTarget(target, { runId, policy });
  }

  const chunks: CorpusChunk[] = [];
  if (target.kind === "web" && target.url) {
    if (!matchesAllowed(target.url, policy.allowedDomains)) {
      throw new Error(`domain not allowed: ${target.url}`);
    }
    const page = await scrape(target.url, crawlerConfig);
    if (!page || !page.markdown) {
      return {
        chunks: [],
        hypotheses: [],
        transcriptArtifactsDeleted: 0
      };
    }
    const pieces = chunkText(page.markdown, policy.quality.minChars, policy.quality.maxChars);
    for (const piece of pieces) {
      chunks.push(
        buildChunk({
          runId,
          sourceId: target.id,
          sourceKind: "web",
          url: page.url,
          title: page.title,
          text: piece,
          tags: target.tags
        })
      );
    }
    return {
      chunks,
      hypotheses: [],
      transcriptArtifactsDeleted: 0
    };
  }
  if (target.kind === "github-repo" && target.url) {
    const digest = await digestGithubRepo(target.url, crawlerConfig);
    if (!digest) {
      return {
        chunks: [],
        hypotheses: [],
        transcriptArtifactsDeleted: 0
      };
    }
    const header =
      `# ${digest.owner}/${digest.repo}\n\n` +
      (digest.description ? `${digest.description}\n\n` : "") +
      (digest.topics.length ? `Topics: ${digest.topics.join(", ")}\n\n` : "");
    const readmePieces = chunkText(header + digest.readme, policy.quality.minChars, policy.quality.maxChars);
    for (const piece of readmePieces) {
      chunks.push(
        buildChunk({
          runId,
          sourceId: target.id,
          sourceKind: "github-repo",
          url: target.url,
          title: `${digest.owner}/${digest.repo} README`,
          text: piece,
          tags: ["readme", ...(target.tags ?? [])]
        })
      );
    }
    for (const doc of digest.docs) {
      const pieces = chunkText(doc.content, policy.quality.minChars, policy.quality.maxChars);
      for (const piece of pieces) {
        chunks.push(
          buildChunk({
            runId,
            sourceId: target.id,
            sourceKind: "github-repo",
            url: `${target.url}/blob/main/${doc.path}`,
            title: `${digest.owner}/${digest.repo} ${doc.path}`,
            text: piece,
            tags: ["docs", ...(target.tags ?? [])]
          })
        );
      }
    }
    return {
      chunks,
      hypotheses: [],
      transcriptArtifactsDeleted: 0
    };
  }
  if (target.kind === "arxiv-query" && target.query) {
    const entries = (await searchArxiv(target.query, target.limit ?? 5, crawlerConfig))
      .filter((entry) => arxivEntryMatchesTarget({
        entry,
        query: target.query ?? "",
        tags: target.tags
      }));
    for (const e of entries) {
      const text = `# ${e.title}\n\nAuthors: ${e.authors.join(", ")}\nPublished: ${e.published}\nLink: ${e.link}\n\n${e.summary}`;
      const pieces = chunkText(text, policy.quality.minChars, policy.quality.maxChars);
      for (const piece of pieces) {
        chunks.push(
          buildChunk({
            runId,
            sourceId: target.id,
            sourceKind: "arxiv",
            url: e.link,
            title: e.title,
            text: piece,
            tags: ["arxiv", ...(target.tags ?? [])]
          })
        );
      }
    }
    return {
      chunks,
      hypotheses: [],
      transcriptArtifactsDeleted: 0
    };
  }
  throw new Error(`unsupported target ${target.id} kind=${target.kind}`);
}

export async function runResearcherPipeline(input: ResearcherRunInput = {}): Promise<ResearcherRunReport> {
  const runId = `run-${new Date().toISOString().replace(/[:.]/g, "-")}-${randomUUID().slice(0, 6)}`;
  const startedAt = new Date().toISOString();
  const policy = await loadPolicy(input.policyPath);
  const targets = await loadTargets(input.targetsPath);
  const corpusPaths = input.corpusPaths ?? resolveCorpusPaths();
  const existing = await readCorpusChunks(corpusPaths);
  const targetState = await readTargetRunState();
  const existingSourceCounts = new Map<string, number>();
  for (const chunk of existing) {
    existingSourceCounts.set(chunk.sourceId, (existingSourceCounts.get(chunk.sourceId) ?? 0) + 1);
  }
  const ollamaConfig = input.ollamaConfig ?? buildOllamaConfigFromEnv(process.env);
  const crawlerConfig =
    input.crawlerConfig ??
    ({
      ...buildCrawlerConfigFromEnv(process.env),
      firecrawlBaseUrl:
        buildCrawlerConfigFromEnv(process.env).firecrawlBaseUrl ?? policy.llm.baseUrl.replace("11434", "3002")
    } as CrawlerConfig);

  const dueTargets = input.targetIds
    ? targets
    : targets.filter((target) => targetDue(target, targetState, Date.now()));
  const dailyBudget = Math.max(0, Math.floor(policy.budgets.dailyCrawlBudget));
  const targetLimit = Math.min(input.maxTargets ?? dailyBudget, dailyBudget);
  const filtered = input.targetIds
    ? targets.filter((t) => input.targetIds!.includes(t.id))
    : [...dueTargets].sort((a, b) => compareTargetSelection(a, b, existingSourceCounts));
  const selectedTargets = filtered.slice(0, targetLimit);

  const firecrawlUsed = await firecrawlHealthy(crawlerConfig);
  const existingHashes = new Set(existing.map((c) => c.hash));

  const targetResults: ResearcherRunReport["targetResults"] = [];
  const collectedChunks: CorpusChunk[] = [];
  let rawChunksCollected = 0;
  const strategyHypotheses: StrategyHypothesis[] = [];
  let transcriptArtifactsDeleted = 0;

  for (const target of selectedTargets) {
    try {
      const collected = await collectFromTarget(target, runId, crawlerConfig, policy);
      rawChunksCollected += collected.chunks.length;
      const novel = collected.chunks.filter((c) => !existingHashes.has(c.hash));
      for (const c of novel) existingHashes.add(c.hash);
      collectedChunks.push(...novel);
      strategyHypotheses.push(...collected.hypotheses);
      transcriptArtifactsDeleted += collected.transcriptArtifactsDeleted;
      targetResults.push({
        targetId: target.id,
        kind: target.kind,
        collected: collected.chunks.length,
        kept: 0,
        rejected: collected.chunks.length - novel.length,
        videosProcessed: collected.videosProcessed
      });
      targetState.targets[target.id] = {
        lastAttemptedAt: new Date().toISOString(),
        lastSucceededAt: new Date().toISOString(),
        attempts: (targetState.targets[target.id]?.attempts ?? 0) + 1,
        successes: (targetState.targets[target.id]?.successes ?? 0) + 1
      };
    } catch (err) {
      targetState.targets[target.id] = {
        lastAttemptedAt: new Date().toISOString(),
        lastSucceededAt: targetState.targets[target.id]?.lastSucceededAt,
        attempts: (targetState.targets[target.id]?.attempts ?? 0) + 1,
        successes: targetState.targets[target.id]?.successes ?? 0
      };
      targetResults.push({
        targetId: target.id,
        kind: target.kind,
        collected: 0,
        kept: 0,
        rejected: 0,
        error: (err as Error).message.slice(0, 200)
      });
    }
  }
  await writeTargetRunState(targetState);

  const topicList = buildResearcherTopicList(selectedTargets);
  const filterResult = await runFilterPipeline(collectedChunks, existing, {
    thresholds: policy.quality,
    topics: topicList,
    ollamaConfig,
    useJudge: !input.skipJudge
  });

  if (!input.skipEmbed) {
    for (const chunk of filterResult.kept) {
      try {
        const result = await embed(chunk.text.slice(0, 1800), { model: policy.llm.embedModel }, ollamaConfig);
        chunk.embedding = result.embedding;
      } catch {
        // embed best-effort
      }
    }
  }

  const corpusBudget = selectChunksWithinCorpusBudget({
    chunks: filterResult.kept,
    currentBytes: await fileSize(corpusPaths.chunksJsonl),
    maxCorpusGb: policy.budgets.maxCorpusGb
  });
  await appendCorpusChunks(corpusBudget.kept, corpusPaths);
  for (const tr of targetResults) {
    const keptForTarget = corpusBudget.kept.filter((c) => c.sourceId === tr.targetId).length;
    const rejectedForTarget = filterResult.rejected.filter((d) => d.chunk.sourceId === tr.targetId).length;
    tr.kept = keptForTarget;
    tr.rejected = tr.rejected + rejectedForTarget;
  }

  const finishedAt = new Date().toISOString();
  const updatedManifest = await readManifest(corpusPaths);
  updatedManifest.updatedAt = finishedAt;
  updatedManifest.chunkCount = existing.length + corpusBudget.kept.length;
  updatedManifest.totalBytes = await fileSize(corpusPaths.chunksJsonl);
  updatedManifest.lastRunId = runId;
  updatedManifest.runs.push({
    runId,
    startedAt,
    finishedAt,
    targetsAttempted: selectedTargets.length,
    chunksKept: corpusBudget.kept.length,
    chunksRejected: filterResult.rejected.length + corpusBudget.rejectedForBudget
  });
  await writeManifest(updatedManifest, corpusPaths);

  const finalStats = corpusStats([...existing, ...corpusBudget.kept]);
  const baseReport = {
    runId,
    startedAt,
    finishedAt,
    targetsAttempted: selectedTargets.length,
    targetsSucceeded: targetResults.filter((t) => !t.error).length,
    chunksCollected: collectedChunks.length,
    rawChunksCollected,
    novelChunksCollected: collectedChunks.length,
    chunksKept: corpusBudget.kept.length,
    chunksRejected: filterResult.rejected.length + corpusBudget.rejectedForBudget,
    dedupRate:
      collectedChunks.length > 0
        ? filterResult.rejected.filter((r) => r.stage === "dedup").length / collectedChunks.length
        : 0,
    firecrawlUsed,
    judgeCalls: filterResult.judged,
    topKeptTitles: Array.from(new Set(corpusBudget.kept.map((chunk) => chunk.title).filter((value): value is string => Boolean(value)))).slice(0, 5),
    strategyHypothesesCount: strategyHypotheses.length,
    topStrategyHypotheses: Array.from(new Set(strategyHypotheses.map((hypothesis) => hypothesis.title))).slice(0, 5),
    transcriptArtifactsDeleted,
    rejectionSummary: buildRejectionSummary(filterResult.rejected, corpusBudget.rejectedForBudget),
    topRejectedChunks: buildTopRejectedChunks(filterResult.rejected),
    budgetRemaining: Math.max(0, dailyBudget - selectedTargets.length),
    corpusStats: finalStats,
    targetResults
  };
  const artifact = await writeStrategyHypothesisArtifacts({
    generatedAt: finishedAt,
    runId,
    count: strategyHypotheses.length,
    provider: process.env.BILL_CLOUD_API_KEY || process.env.NVIDIA_NIM_API_KEY || process.env.NVIDIA_API_KEY ? "cloud" : "ollama",
    model: process.env.BILL_CLOUD_REVIEW_MODEL || policy.llm.generateModel,
    hypotheses: strategyHypotheses
  });
  const strategyArtifactPath = artifact.latestPath;
  const report: ResearcherRunReport = {
    ...baseReport,
    strategyArtifactPath,
    ...buildResearcherRunState(baseReport)
  };

  await writeResearcherWorkspaceArtifacts(report, {
    workspaceRoot: input.workspaceRoot,
    latestReportPath: input.latestReportPath,
    reportRunsDir: input.reportRunsDir
  });

  return report;
}
