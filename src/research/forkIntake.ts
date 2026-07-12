import { createHash } from "node:crypto";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { basename, dirname, resolve } from "node:path";

export interface ForkManifestEntry {
  upstream: string;
  fork: string;
  url: string;
  lane: string;
  use: string;
}

export interface ForkManifest {
  generated_at?: string;
  github_account?: string;
  forked?: ForkManifestEntry[];
}

export interface ForkIntegrationCard {
  id: string;
  generatedAt: string;
  upstream: string;
  fork: string;
  url: string;
  lane: string;
  intendedUse: string;
  sourceFiles: Array<{
    path: string;
    htmlUrl?: string;
    sha?: string;
    excerpt: string;
  }>;
  extractedSignals: string[];
  integrationNotes: string[];
  guardrails: string[];
}

export interface RunForkIntakeOptions {
  manifestPath?: string;
  outputDir?: string;
  maxRepos?: number;
  maxFilesPerRepo?: number;
  githubToken?: string;
  now?: () => string;
  fetchImpl?: typeof fetch;
}

export interface ForkIntakeReport {
  command: "fork-intake";
  generatedAt: string;
  manifestPath: string;
  outputDir: string;
  attempted: number;
  written: number;
  failed: number;
  cards: Array<{
    id: string;
    upstream: string;
    fork: string;
    outputPath: string;
    sourceFileCount: number;
    signalCount: number;
  }>;
  failures: Array<{
    fork: string;
    reason: string;
  }>;
}

const DEFAULT_MANIFEST_PATH = ".rumbling-hedge/state/github-fork-manifest.latest.json";
const DEFAULT_OUTPUT_DIR = ".rumbling-hedge/research/forks";

const CANDIDATE_DOC_PATHS = [
  "README.md",
  "ARCHITECTURE.md",
  "ROADMAP.md",
  "docs/README.md",
  "docs/architecture.md",
  "docs/quickstart.md",
  "examples/README.md",
  "agents/README.md",
  "strategies/README.md"
];

const SIGNAL_RULES: Array<{ label: string; pattern: RegExp }> = [
  { label: "agent role separation", pattern: /\b(agent|analyst|researcher|risk|trader|supervisor|graph)\b/i },
  { label: "backtest or paper/live separation", pattern: /\b(backtest|paper|dry.?run|live|simulation|walk.?forward)\b/i },
  { label: "market data connectors", pattern: /\b(connector|exchange|api|broker|data provider|clob|kalshi|polymarket)\b/i },
  { label: "risk and execution controls", pattern: /\b(risk|position|inventory|slippage|spread|stop|drawdown|kill.?switch)\b/i },
  { label: "research automation loop", pattern: /\b(research|experiment|evaluation|hypothesis|dataset|model)\b/i },
  { label: "typed or schema-first IO", pattern: /\b(schema|pydantic|typed|json|validation|structured)\b/i },
  { label: "voice or realtime orchestration", pattern: /\b(voice|realtime|livekit|room|audio|video)\b/i }
];

function safeCardId(fork: string): string {
  return fork.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
}

function trimExcerpt(value: string, maxChars = 2400): string {
  return value
    .replace(/\r/g, "")
    .replace(/[ \t]+/g, " ")
    .replace(/\n{3,}/g, "\n\n")
    .trim()
    .slice(0, maxChars);
}

function dedupe(values: string[]): string[] {
  return Array.from(new Set(values.filter(Boolean)));
}

function buildHeaders(token?: string): Record<string, string> {
  return {
    Accept: "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
    ...(token ? { Authorization: `Bearer ${token}` } : {})
  };
}

async function githubJson<T>(args: {
  repo: string;
  path: string;
  token?: string;
  fetchImpl: typeof fetch;
}): Promise<T | null> {
  const url = `https://api.github.com/repos/${args.repo}/${args.path}`;
  const response = await args.fetchImpl(url, { headers: buildHeaders(args.token) });
  if (response.status === 404) return null;
  if (!response.ok) {
    throw new Error(`GitHub API ${response.status} for ${args.repo}/${args.path}`);
  }
  return await response.json() as T;
}

interface GitHubContentFile {
  type?: string;
  path?: string;
  name?: string;
  sha?: string;
  download_url?: string | null;
  html_url?: string;
}

async function fetchText(url: string, fetchImpl: typeof fetch): Promise<string> {
  const response = await fetchImpl(url);
  if (!response.ok) {
    throw new Error(`download failed ${response.status} for ${url}`);
  }
  return await response.text();
}

async function loadCandidateFiles(args: {
  repo: string;
  token?: string;
  maxFiles: number;
  fetchImpl: typeof fetch;
}): Promise<ForkIntegrationCard["sourceFiles"]> {
  const found: ForkIntegrationCard["sourceFiles"] = [];
  for (const docPath of CANDIDATE_DOC_PATHS) {
    if (found.length >= args.maxFiles) break;
    const item = await githubJson<GitHubContentFile>({
      repo: args.repo,
      path: `contents/${encodeURIComponent(docPath).replace(/%2F/g, "/")}`,
      token: args.token,
      fetchImpl: args.fetchImpl
    }).catch(() => null);
    if (!item || item.type !== "file" || !item.download_url || !item.path) {
      continue;
    }
    const text = await fetchText(item.download_url, args.fetchImpl).catch(() => "");
    const excerpt = trimExcerpt(text);
    if (!excerpt) continue;
    found.push({
      path: item.path,
      htmlUrl: item.html_url,
      sha: item.sha,
      excerpt
    });
  }
  return found;
}

function extractSignals(entry: ForkManifestEntry, sourceFiles: ForkIntegrationCard["sourceFiles"]): string[] {
  const corpus = [
    entry.lane,
    entry.use,
    ...sourceFiles.map((file) => file.excerpt)
  ].join("\n");
  return SIGNAL_RULES
    .filter((rule) => rule.pattern.test(corpus))
    .map((rule) => rule.label);
}

function buildIntegrationNotes(entry: ForkManifestEntry, signals: string[]): string[] {
  const notes = [
    `Use for ${entry.lane}; intended path: ${entry.use}`,
    "Distill patterns into Bill/Hedge interfaces before any runtime adoption.",
    "Prefer adapters, schema cards, and tests over vendoring code."
  ];
  if (signals.includes("backtest or paper/live separation")) {
    notes.push("Compare its backtest/paper/live boundary against Bill promotion gates.");
  }
  if (signals.includes("risk and execution controls")) {
    notes.push("Extract risk-control patterns into paper-only gates before execution work.");
  }
  if (signals.includes("market data connectors")) {
    notes.push("Evaluate connector ideas against current source freshness and licensing constraints.");
  }
  return notes;
}

function buildCard(entry: ForkManifestEntry, sourceFiles: ForkIntegrationCard["sourceFiles"], generatedAt: string): ForkIntegrationCard {
  const signals = extractSignals(entry, sourceFiles);
  const id = `${safeCardId(entry.fork)}-${createHash("sha1").update(entry.upstream).digest("hex").slice(0, 8)}`;
  return {
    id,
    generatedAt,
    upstream: entry.upstream,
    fork: entry.fork,
    url: entry.url,
    lane: entry.lane,
    intendedUse: entry.use,
    sourceFiles,
    extractedSignals: signals,
    integrationNotes: buildIntegrationNotes(entry, signals),
    guardrails: [
      "Reference only; do not wire external code into live trading directly.",
      "Any adopted idea must pass unit tests, walk-forward/OOS checks, slippage/fee stress, and paper-only promotion.",
      "Keep local runtime lean by persisting this compact card instead of cloning the repository."
    ]
  };
}

export async function runForkIntake(options: RunForkIntakeOptions = {}): Promise<ForkIntakeReport> {
  const manifestPath = resolve(options.manifestPath ?? DEFAULT_MANIFEST_PATH);
  const outputDir = resolve(options.outputDir ?? DEFAULT_OUTPUT_DIR);
  const generatedAt = options.now?.() ?? new Date().toISOString();
  const maxRepos = Math.max(1, options.maxRepos ?? 24);
  const maxFiles = Math.max(1, options.maxFilesPerRepo ?? 4);
  const fetchImpl = options.fetchImpl ?? fetch;
  const token = options.githubToken ?? process.env.GITHUB_TOKEN ?? process.env.GH_TOKEN;
  const manifest = JSON.parse(await readFile(manifestPath, "utf8")) as ForkManifest;
  const entries = (manifest.forked ?? []).slice(0, maxRepos);
  const cards: ForkIntakeReport["cards"] = [];
  const failures: ForkIntakeReport["failures"] = [];

  await mkdir(outputDir, { recursive: true });

  for (const entry of entries) {
    try {
      const sourceFiles = await loadCandidateFiles({
        repo: entry.fork,
        token,
        maxFiles,
        fetchImpl
      });
      const card = buildCard(entry, sourceFiles, generatedAt);
      const outputPath = resolve(outputDir, `${safeCardId(entry.fork)}.json`);
      await mkdir(dirname(outputPath), { recursive: true });
      await writeFile(outputPath, `${JSON.stringify(card, null, 2)}\n`, "utf8");
      cards.push({
        id: card.id,
        upstream: card.upstream,
        fork: card.fork,
        outputPath,
        sourceFileCount: sourceFiles.length,
        signalCount: card.extractedSignals.length
      });
    } catch (error) {
      failures.push({
        fork: entry.fork,
        reason: error instanceof Error ? error.message : String(error)
      });
    }
  }

  const latestPath = resolve(outputDir, "_latest-report.json");
  const report: ForkIntakeReport = {
    command: "fork-intake",
    generatedAt,
    manifestPath,
    outputDir,
    attempted: entries.length,
    written: cards.length,
    failed: failures.length,
    cards,
    failures
  };
  await writeFile(latestPath, `${JSON.stringify(report, null, 2)}\n`, "utf8");
  await writeFile(resolve(outputDir, "_README.md"), [
    "# Bill Fork Intake Cards",
    "",
    `Generated: ${generatedAt}`,
    `Cards: ${cards.length}/${entries.length}`,
    "",
    "These cards are compact repo summaries. They intentionally replace local clones for the 24/7 Bill runtime.",
    "",
    ...cards.map((card) => `- ${basename(card.outputPath)}: ${card.fork} (${card.sourceFileCount} files, ${card.signalCount} signals)`)
  ].join("\n"));

  return report;
}

