import { readdir, readFile, writeFile, mkdir } from "node:fs/promises";
import { dirname, join, resolve } from "node:path";
import type { SupportedStrategyId } from "../domain.js";
import type { ForkIntegrationCard } from "./forkIntake.js";

export interface ForkAdoptionCandidate {
  upstream: string;
  fork: string;
  lane: string;
  priority: number;
  status: "adopt-pattern" | "watch-only" | "blocked";
  billUse: string;
  implementationSteps: string[];
  guardrails: string[];
  strategyFocus: SupportedStrategyId[];
}

export interface InstitutionalFramework {
  id: string;
  label: string;
  adoptedFrom: string[];
  publicResearchAnchors: string[];
  billPrinciple: string;
  implementation: string;
}

export interface ForkSynthesisReport {
  command: "fork-synthesis";
  generatedAt: string;
  inputDir: string;
  outputPath: string;
  markdownPath: string;
  cardsRead: number;
  adoptedCount: number;
  watchOnlyCount: number;
  blockedCount: number;
  adoptedPatterns: InstitutionalFramework[];
  candidates: ForkAdoptionCandidate[];
  strategyLabDirectives: Array<{
    strategyId: SupportedStrategyId;
    sourceForks: string[];
    directive: string;
  }>;
  blockers: string[];
}

export interface RunForkSynthesisOptions {
  inputDir?: string;
  outputPath?: string;
  markdownPath?: string;
  now?: () => string;
}

const DEFAULT_INPUT_DIR = ".rumbling-hedge/research/forks";
const DEFAULT_OUTPUT_PATH = ".rumbling-hedge/research/forks/_synthesis.latest.json";
const DEFAULT_MARKDOWN_PATH = ".rumbling-hedge/research/forks/_synthesis.latest.md";

const PUBLIC_RESEARCH_ANCHORS = {
  aqrTrendFollowing: "AQR: time-series momentum/trend following across futures, bonds, commodities, and currencies; evaluate robustness across long histories and economic regimes.",
  twoSigmaFactorParsimony: "Two Sigma/Venn: use parsimonious factor models to avoid overfit, illegible, impractical explanations of risk and return.",
  twoSigmaTrendDefinition: "Two Sigma/Venn: define factors from academic literature first, then test canonical lookbacks rather than inventing parameters ad hoc.",
  janeStreetSystems: "Jane Street: build critical trading/risk systems in-house, keep human judgment visible, and integrate trading/research/technology.",
  janeStreetJitter: "Jane Street: low-jitter systems reduce execution uncertainty; operational latency belongs in risk, not just engineering.",
  citadelPredictiveRisk: "Citadel Securities: combine predictive models, resilient platform design, and risk absorption before providing continuous liquidity.",
  hrtComputeRisk: "Hudson River Trading: research, modeling, and risk management require advanced computing environments and execution-quality accountability."
} as const;

const STRATEGY_FOCUS: Record<string, SupportedStrategyId[]> = {
  "financial multi-agent research": ["session-momentum", "opening-range-reversal", "liquidity-reversion", "ict-displacement"],
  "strategy design/backtesting UI": ["session-momentum", "opening-range-reversal", "liquidity-reversion"],
  "quant research platform": ["session-momentum", "opening-range-reversal", "liquidity-reversion"],
  "automated R&D": ["session-momentum", "opening-range-reversal", "liquidity-reversion", "ict-displacement"],
  "bot/backtest/paper/live architecture": ["session-momentum", "opening-range-reversal", "liquidity-reversion"],
  "Python strategy/backtesting framework": ["session-momentum", "opening-range-reversal", "liquidity-reversion"],
  "market making and connectors": ["liquidity-reversion"],
  "Polymarket market making": [],
  "prediction-market pricing agent": [],
  "prediction-market API": [],
  "official Polymarket Python client": [],
  "official Polymarket TypeScript client": [],
  "official Polymarket Rust client": [],
  "official Polymarket agent examples": [],
  "financial reinforcement learning": [],
  "market data and research terminal": ["session-momentum", "opening-range-reversal", "liquidity-reversion"],
  "durable agent graph orchestration": [],
  "typed agent IO": [],
  "multi-agent collaboration": [],
  "voice/video AI agent orchestration": []
};

const LANE_PRIORITY: Record<string, number> = {
  "quant research platform": 96,
  "automated R&D": 94,
  "financial multi-agent research": 92,
  "bot/backtest/paper/live architecture": 90,
  "Python strategy/backtesting framework": 88,
  "strategy design/backtesting UI": 84,
  "typed agent IO": 82,
  "durable agent graph orchestration": 80,
  "market data and research terminal": 76,
  "prediction-market pricing agent": 72,
  "prediction-market API": 70,
  "official Polymarket TypeScript client": 68,
  "official Polymarket Python client": 66,
  "official Polymarket Rust client": 64,
  "official Polymarket agent examples": 62,
  "market making and connectors": 58,
  "Polymarket market making": 54,
  "financial reinforcement learning": 44,
  "multi-agent collaboration": 40,
  "voice/video AI agent orchestration": 36
};

function statusForCard(card: ForkIntegrationCard): ForkAdoptionCandidate["status"] {
  if (/market making|reinforcement learning|voice|video|business|money-making/i.test(card.lane)) {
    return "watch-only";
  }
  if (/official Polymarket|prediction-market|prediction market/i.test(card.lane)) {
    return "watch-only";
  }
  return "adopt-pattern";
}

function implementationStepsFor(card: ForkIntegrationCard): string[] {
  if (/TradingAgents/i.test(card.upstream)) {
    return [
      "Map Bill research roles to analyst, risk, trader, and portfolio-manager verdicts.",
      "Require every strategy hypothesis to carry separate research, risk, and execution-gate evidence.",
      "Persist role verdicts as JSON so strategy-factory can reject unsupported discretionary claims."
    ];
  }
  if (/qlib/i.test(card.upstream)) {
    return [
      "Keep experiment metadata reproducible: dataset path, train/test windows, OOS windows, cost model, and profile id.",
      "Promote only rolling OOS evidence, not in-sample rank.",
      "Write compact experiment summaries instead of storing raw heavy experiment folders on SSD."
    ];
  }
  if (/RD-Agent/i.test(card.upstream)) {
    return [
      "Use R&D loops for hypothesis generation and experiment planning only.",
      "Cap autonomous iterations with compute locks and require tests before a hypothesis enters strategyFeed.",
      "Separate idea generation from execution so LLMs never directly decide orders."
    ];
  }
  if (/freqtrade|jesse/i.test(card.upstream)) {
    return [
      "Mirror dry-run/live separation with explicit paper-only defaults.",
      "Persist backtest reports with costs, rejected trades, and parameter sets.",
      "Keep strategy code small and typed before any scheduler adoption."
    ];
  }
  if (/Superalgos/i.test(card.upstream)) {
    return [
      "Use visual lifecycle ideas as board sections: idea, coded, backtested, OOS, paper, blocked.",
      "Expose blockers and promotion gates on OpenJarvis instead of burying them in logs.",
      "Avoid importing the runtime; keep Bill as the execution authority."
    ];
  }
  if (/langgraph/i.test(card.upstream)) {
    return [
      "Use checkpoint and retry concepts for scheduled Bill jobs.",
      "Keep human approval gates before execution-widening actions.",
      "Represent long loops as state transitions, not free-form agent chatter."
    ];
  }
  if (/pydantic-ai/i.test(card.upstream)) {
    return [
      "Validate every LLM-produced strategy, risk verdict, and research card against explicit schemas.",
      "Reject partial or vague outputs instead of repairing them silently.",
      "Prefer typed adapters over prompt-only contracts."
    ];
  }
  if (/OpenBB/i.test(card.upstream)) {
    return [
      "Treat market-data tooling as enrichment, not execution authority.",
      "Add sources only after freshness, licensing, and failure-mode checks.",
      "Summarize market context into compact cards for strategy-lab."
    ];
  }
  if (/oracle3|pmxt|clob-client|polymarket/i.test(card.upstream)) {
    return [
      "Use prediction-market clients and pricing ideas for shadow analysis first.",
      "Require liquidity, spread, entry-premium, and leader-consensus checks before paper execution.",
      "Never reuse keys or order routers from reference repos directly."
    ];
  }
  if (/hummingbot|poly-maker/i.test(card.upstream)) {
    return [
      "Adopt inventory and adverse-selection concepts as risk checks only.",
      "Do not run market making without L2 data, queue simulation, and exchange sandbox coverage.",
      "Use spread/liquidity stress tests before any market-making paper lane."
    ];
  }
  return [
    "Keep as reference-only until a concrete Bill interface exists.",
    "Extract small tested patterns instead of importing runtime code.",
    "Require OOS, cost stress, and paper-gate evidence before promotion."
  ];
}

function billUseFor(card: ForkIntegrationCard): string {
  if (/TradingAgents/i.test(card.upstream)) return "Role-separated research council for strategy hypotheses and risk verdicts.";
  if (/qlib/i.test(card.upstream)) return "Experiment tracking, rolling splits, and reproducible strategy-lab metadata.";
  if (/RD-Agent/i.test(card.upstream)) return "Bounded autonomous R&D loop for hypothesis generation and experiment planning.";
  if (/freqtrade|jesse/i.test(card.upstream)) return "Battle-tested paper/live boundary and strategy report ergonomics.";
  if (/Superalgos/i.test(card.upstream)) return "Strategy lifecycle board and promotion-state visibility.";
  if (/langgraph/i.test(card.upstream)) return "Durable job-state/checkpoint pattern for orchestration.";
  if (/pydantic-ai/i.test(card.upstream)) return "Schema-first LLM outputs for research and strategy cards.";
  if (/OpenBB/i.test(card.upstream)) return "Research/data terminal patterns for market context enrichment.";
  if (/oracle3/i.test(card.upstream)) return "Prediction-market fair-value and constraint-arbitrage shadow research.";
  if (/pmxt|clob-client|polymarket/i.test(card.upstream)) return "Prediction-market connector references behind shadow/paper gates.";
  if (/hummingbot|poly-maker/i.test(card.upstream)) return "Inventory, spread, and adverse-selection risk checks; no market-making runtime.";
  return card.intendedUse;
}

function buildCandidate(card: ForkIntegrationCard): ForkAdoptionCandidate {
  const status = statusForCard(card);
  const priority = status === "adopt-pattern"
    ? LANE_PRIORITY[card.lane] ?? 50
    : Math.min(49, LANE_PRIORITY[card.lane] ?? 35);
  return {
    upstream: card.upstream,
    fork: card.fork,
    lane: card.lane,
    priority,
    status,
    billUse: billUseFor(card),
    implementationSteps: implementationStepsFor(card),
    guardrails: card.guardrails,
    strategyFocus: STRATEGY_FOCUS[card.lane] ?? []
  };
}

function buildFrameworks(candidates: ForkAdoptionCandidate[]): InstitutionalFramework[] {
  const adopted = candidates.filter((candidate) => candidate.status === "adopt-pattern");
  const has = (pattern: RegExp) => adopted.filter((candidate) => pattern.test(candidate.upstream)).map((candidate) => candidate.fork);
  return [
    {
      id: "role-separated-investment-committee",
      label: "Role-separated investment committee",
      adoptedFrom: has(/TradingAgents|autogen/i),
      publicResearchAnchors: [
        PUBLIC_RESEARCH_ANCHORS.janeStreetSystems,
        PUBLIC_RESEARCH_ANCHORS.citadelPredictiveRisk
      ],
      billPrinciple: "Research, risk, and execution should be separate verdicts; no single LLM answer can promote a strategy.",
      implementation: "Strategy hypotheses must carry role-style evidence and still pass OOS/cost/paper gates."
    },
    {
      id: "reproducible-experiment-ledger",
      label: "Reproducible experiment ledger",
      adoptedFrom: has(/qlib|RD-Agent|freqtrade|jesse/i),
      publicResearchAnchors: [
        PUBLIC_RESEARCH_ANCHORS.aqrTrendFollowing,
        PUBLIC_RESEARCH_ANCHORS.twoSigmaTrendDefinition
      ],
      billPrinciple: "Every promoted result must be reproducible from data path, split windows, profile id, and cost model.",
      implementation: "Strategy-factory reads fork synthesis and reports experiment/research context alongside OOS evidence."
    },
    {
      id: "dry-run-first-operations",
      label: "Dry-run first operations",
      adoptedFrom: has(/freqtrade|jesse|Superalgos/i),
      publicResearchAnchors: [
        PUBLIC_RESEARCH_ANCHORS.twoSigmaFactorParsimony,
        PUBLIC_RESEARCH_ANCHORS.janeStreetSystems
      ],
      billPrinciple: "Backtest, OOS, paper/demo, and live are separate states with explicit blockers.",
      implementation: "Bill remains paper/demo-first and exposes lifecycle state on OpenJarvis."
    },
    {
      id: "microstructure-before-market-making",
      label: "Microstructure before market making",
      adoptedFrom: candidates.filter((candidate) => /hummingbot|poly-maker/i.test(candidate.upstream)).map((candidate) => candidate.fork),
      publicResearchAnchors: [
        PUBLIC_RESEARCH_ANCHORS.citadelPredictiveRisk,
        PUBLIC_RESEARCH_ANCHORS.hrtComputeRisk,
        PUBLIC_RESEARCH_ANCHORS.janeStreetJitter
      ],
      billPrinciple: "Market making is blocked without L2 data, queue/fill simulation, inventory controls, and adverse-selection tests.",
      implementation: "Use these forks as risk-pattern references only; do not route market-making orders."
    },
    {
      id: "schema-first-agent-io",
      label: "Schema-first agent I/O",
      adoptedFrom: has(/pydantic-ai|langgraph/i),
      publicResearchAnchors: [
        PUBLIC_RESEARCH_ANCHORS.twoSigmaFactorParsimony
      ],
      billPrinciple: "Agent output is data, not authority; invalid schemas fail closed.",
      implementation: "Research cards, strategy hypotheses, and strategy-factory artifacts stay machine-readable."
    }
  ].filter((framework) => framework.adoptedFrom.length > 0);
}

function buildStrategyDirectives(candidates: ForkAdoptionCandidate[]): ForkSynthesisReport["strategyLabDirectives"] {
  const byStrategy = new Map<SupportedStrategyId, ForkAdoptionCandidate[]>();
  for (const candidate of candidates.filter((item) => item.status === "adopt-pattern")) {
    for (const strategyId of candidate.strategyFocus) {
      byStrategy.set(strategyId, [...(byStrategy.get(strategyId) ?? []), candidate]);
    }
  }
  return [...byStrategy.entries()]
    .map(([strategyId, sourceCandidates]) => ({
      strategyId,
      sourceForks: sourceCandidates
        .sort((left, right) => right.priority - left.priority)
        .map((candidate) => candidate.fork)
        .slice(0, 6),
      directive: `Apply fork-derived discipline to ${strategyId}: reproducible split metadata, explicit dry-run/paper boundary, and separate research/risk/execution evidence before promotion.`
    }))
    .sort((left, right) => left.strategyId.localeCompare(right.strategyId));
}

async function readCards(inputDir: string): Promise<ForkIntegrationCard[]> {
  const files = await readdir(inputDir);
  const cards: ForkIntegrationCard[] = [];
  for (const file of files.sort()) {
    if (!file.endsWith(".json") || file.startsWith("_")) continue;
    const path = join(inputDir, file);
    try {
      const card = JSON.parse(await readFile(path, "utf8")) as ForkIntegrationCard;
      if (card?.fork && card?.upstream && card?.lane) {
        cards.push(card);
      }
    } catch {
      continue;
    }
  }
  return cards;
}

function renderMarkdown(report: ForkSynthesisReport): string {
  const candidates = report.candidates
    .slice(0, 12)
    .map((candidate) => `- ${candidate.fork}: ${candidate.status}, p${candidate.priority}, ${candidate.billUse}`)
    .join("\n");
  const frameworks = report.adoptedPatterns
    .map((framework) => `- ${framework.label}: ${framework.billPrinciple}\n  - anchors: ${framework.publicResearchAnchors.join("; ")}`)
    .join("\n");
  const directives = report.strategyLabDirectives
    .map((directive) => `- ${directive.strategyId}: ${directive.sourceForks.join(", ")}`)
    .join("\n");
  return [
    "# Bill/Hedge Fork Synthesis",
    "",
    `Generated: ${report.generatedAt}`,
    `Cards read: ${report.cardsRead}`,
    `Adopt/watch/blocked: ${report.adoptedCount}/${report.watchOnlyCount}/${report.blockedCount}`,
    "",
    "## Adopted Frameworks",
    frameworks || "- none",
    "",
    "## Strategy-Lab Directives",
    directives || "- none",
    "",
    "## Top Candidates",
    candidates || "- none",
    "",
    "## Blockers",
    report.blockers.map((blocker) => `- ${blocker}`).join("\n") || "- none",
    ""
  ].join("\n");
}

export async function runForkSynthesis(options: RunForkSynthesisOptions = {}): Promise<ForkSynthesisReport> {
  const inputDir = resolve(options.inputDir ?? DEFAULT_INPUT_DIR);
  const outputPath = resolve(options.outputPath ?? DEFAULT_OUTPUT_PATH);
  const markdownPath = resolve(options.markdownPath ?? DEFAULT_MARKDOWN_PATH);
  const generatedAt = options.now?.() ?? new Date().toISOString();
  const cards = await readCards(inputDir);
  const candidates = cards
    .map(buildCandidate)
    .sort((left, right) => right.priority - left.priority || left.fork.localeCompare(right.fork));
  const adoptedPatterns = buildFrameworks(candidates);
  const strategyLabDirectives = buildStrategyDirectives(candidates);
  const blockers = [
    ...(cards.length === 0 ? ["No fork integration cards were found. Run npm run bill:fork-intake first."] : []),
    ...(strategyLabDirectives.length === 0 ? ["No fork-derived strategy-lab directives were produced."] : [])
  ];

  const report: ForkSynthesisReport = {
    command: "fork-synthesis",
    generatedAt,
    inputDir,
    outputPath,
    markdownPath,
    cardsRead: cards.length,
    adoptedCount: candidates.filter((candidate) => candidate.status === "adopt-pattern").length,
    watchOnlyCount: candidates.filter((candidate) => candidate.status === "watch-only").length,
    blockedCount: candidates.filter((candidate) => candidate.status === "blocked").length,
    adoptedPatterns,
    candidates,
    strategyLabDirectives,
    blockers
  };

  await mkdir(dirname(outputPath), { recursive: true });
  await mkdir(dirname(markdownPath), { recursive: true });
  await writeFile(outputPath, `${JSON.stringify(report, null, 2)}\n`, "utf8");
  await writeFile(markdownPath, renderMarkdown(report), "utf8");
  return report;
}

export async function readLatestForkSynthesis(path = DEFAULT_OUTPUT_PATH): Promise<ForkSynthesisReport | null> {
  try {
    return JSON.parse(await readFile(resolve(path), "utf8")) as ForkSynthesisReport;
  } catch {
    return null;
  }
}
