import { readdir, readFile, stat } from "node:fs/promises";
import { resolve } from "node:path";
import { loadLatestResearchStrategyFeed } from "../research/strategyFeed.js";
import { buildTrackPolicyFromEnv, type BillMarketTrackId, type BillTrackPolicy } from "../research/tracks.js";
import { resolveRuntimeRepoRoot } from "../utils/runtimePaths.js";
import { buildFundPlan, type FundPlan } from "./fundPlan.js";

const DEFAULT_STATE_DIR = ".rumbling-hedge/state";
const DEFAULT_RESEARCHER_DIR = ".rumbling-hedge/research/researcher";
const DEFAULT_RESEARCH_DATA_DIR = "data/research";
const DEFAULT_SOURCE_CATALOG_PATH = ".rumbling-hedge/research/source-catalog.json";
const DEFAULT_BILL_HEALTH_PATH = ".rumbling-hedge/logs/bill-health.latest.json";

export interface ArtifactFreshness {
  status: "fresh" | "stale" | "missing";
  observedAt?: string;
  ageMinutes?: number;
  maxAgeMinutes: number;
  summary: string;
}

export interface PredictionCandidateSummary {
  candidateId?: string;
  verdict?: string;
  netEdgePct?: number;
  grossEdgePct?: number;
  matchScore?: number;
  recommendedStake?: number;
  venuePair?: string;
  history?: {
    observations?: number;
    watchCycles?: number;
    paperCycles?: number;
    bestGrossEdgePct?: number;
    bestNetEdgePct?: number;
    latestGrossEdgePct?: number;
    latestNetEdgePct?: number;
    latestShortfallPct?: number;
    trend?: string;
  };
}

export interface PredictionSummary {
  posture: string;
  counts: {
    reject: number;
    watch: number;
    paperTrade: number;
  };
  topCandidate: PredictionCandidateSummary | null;
  readyForPaper: boolean;
  blockers: string[];
  recommendation?: string;
  freshness?: ArtifactFreshness;
  recentLearning?: {
    totalCycles?: number;
    structuralWatchCycles?: number;
    economicBlockCycles?: number;
    dominantCandidate?: {
      candidateId?: string;
      observations?: number;
      bestGrossEdgePct?: number;
      latestGrossEdgePct?: number;
      latestShortfallPct?: number;
      trend?: string;
    };
  };
}

export interface CopyDemoSummary {
  timestamp?: string;
  status: "actionable" | "watch-only" | "idle";
  actionableIdeas: number;
  totalIdeas: number;
  summary?: string;
  blockers: string[];
  freshness?: ArtifactFreshness;
  topIdea?: {
    id?: string;
    slug?: string;
    action?: string;
  };
}

export interface LaneSummary {
  accountId?: string;
  label?: string;
  primaryStrategy?: string;
  focusSymbol?: string;
  action?: string;
}

export interface FuturesSummary {
  deployable: boolean;
  posture?: {
    mode?: string;
    reportStatus?: string;
    selectedProfile?: string;
    whyNotTrading?: string[];
    evidencePlan?: {
      mode?: string;
      rationale?: string;
      laneDirective?: string;
    };
  };
  sampleSequence?: number;
  laneCount: number;
  lanes: LaneSummary[];
  freshness?: ArtifactFreshness;
  datasetFreshness?: ArtifactFreshness;
  warnings?: string[];
}

export interface ResearchSummary {
  runId?: string;
  startedAt?: string;
  finishedAt?: string;
  targetsAttempted?: number;
  targetsSucceeded?: number;
  chunksCollected?: number;
  chunksKept?: number;
  firecrawlUsed?: boolean;
  dedupRate?: number;
  topKeptTitles: string[];
  strategyHypothesesCount?: number;
  topStrategyHypotheses?: string[];
  strategyFocusStrategies?: string[];
  strategyFocusSymbols?: string[];
  status?: "healthy" | "degraded";
  nextAction?: string;
  blockers?: string[];
  freshness?: ArtifactFreshness;
}

export interface TrackReadinessSummary {
  id: BillMarketTrackId;
  mode: "active" | "research-only" | "disabled";
  posture: "actionable" | "shadow" | "collecting" | "setup-debt" | "idle";
  artifactCount: number;
  latestArtifactAt?: string;
  configuredSources: number;
  missingConfigSources: number;
  automationReadySources: number;
  trackedSymbols: string[];
  nextAction: string;
  notes: string[];
  freshness?: ArtifactFreshness;
}

export interface OpportunityAction {
  lane: BillMarketTrackId | "researcher";
  stage: "execute" | "shadow" | "collect" | "configure" | "research";
  priority: number;
  summary: string;
  reason: string;
}

export interface OpportunitySnapshot {
  timestamp: string;
  prediction: PredictionSummary;
  copyDemo: CopyDemoSummary;
  futures: FuturesSummary;
  research: ResearchSummary;
  runtimeHealth: {
    status: "healthy" | "degraded" | "critical";
    observedAt?: string;
    warnings: string[];
    summaryLines: string[];
  };
  trackBoard: TrackReadinessSummary[];
  fundPlan: FundPlan;
  primaryAction: OpportunityAction;
  actionQueue: OpportunityAction[];
  attention: string[];
}

export interface OpportunitySnapshotOptions {
  baseDir?: string;
  stateDir?: string;
  researchDir?: string;
  researchDataDir?: string;
  sourceCatalogPath?: string;
  env?: NodeJS.ProcessEnv;
  now?: () => string;
}

interface SourceCatalogEntry {
  id?: string;
  name?: string;
  tracks?: BillMarketTrackId[];
  configured?: boolean;
  automationReady?: boolean;
  mode?: string;
  priority?: string;
  reason?: string;
  collectionCommand?: string | null;
}

async function readJsonSafe<T>(path: string): Promise<T | null> {
  try {
    const raw = await readFile(path, "utf8");
    return JSON.parse(raw) as T;
  } catch {
    return null;
  }
}

async function readJsonArtifact<T>(path: string): Promise<{ data: T | null; mtime?: string }> {
  try {
    const [raw, info] = await Promise.all([
      readFile(path, "utf8"),
      stat(path)
    ]);

    return {
      data: JSON.parse(raw) as T,
      mtime: info.mtime.toISOString()
    };
  } catch {
    return { data: null };
  }
}

async function listFilesWithMtime(dir: string): Promise<Array<{ path: string; mtime: string }>> {
  try {
    const names = await readdir(dir);
    const files = await Promise.all(names.map(async (name) => {
      const path = resolve(dir, name);
      const info = await stat(path);
      if (!info.isFile()) {
        return null;
      }

      return {
        path,
        mtime: info.mtime.toISOString()
      };
    }));

    return files.filter((value): value is { path: string; mtime: string } => Boolean(value));
  } catch {
    return [];
  }
}

function latestTimestamp(items: Array<{ mtime: string }>): string | undefined {
  return items
    .map((item) => item.mtime)
    .sort((left, right) => right.localeCompare(left))[0];
}

function parseTimestamp(value: string | undefined): number | null {
  if (!value) return null;
  const parsed = Date.parse(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function formatAgeMinutes(ageMinutes: number): string {
  if (ageMinutes < 1) return "<1m";
  if (ageMinutes < 60) return `${Math.round(ageMinutes)}m`;
  if (ageMinutes < 1440) return `${(ageMinutes / 60).toFixed(ageMinutes >= 600 ? 0 : 1)}h`;
  return `${(ageMinutes / 1440).toFixed(ageMinutes >= 14400 ? 0 : 1)}d`;
}

function buildFreshness(args: {
  label: string;
  observedAt?: string;
  now: string;
  maxAgeMinutes: number;
}): ArtifactFreshness {
  const observedMs = parseTimestamp(args.observedAt);
  const nowMs = parseTimestamp(args.now) ?? Date.now();
  if (observedMs === null) {
    return {
      status: "missing",
      maxAgeMinutes: args.maxAgeMinutes,
      summary: `${args.label} artifact is missing a usable timestamp.`
    };
  }

  const ageMinutes = Math.max(0, (nowMs - observedMs) / 60_000);
  if (ageMinutes > args.maxAgeMinutes) {
    return {
      status: "stale",
      observedAt: args.observedAt,
      ageMinutes,
      maxAgeMinutes: args.maxAgeMinutes,
      summary: `${args.label} is stale at ${formatAgeMinutes(ageMinutes)} old.`
    };
  }

  return {
    status: "fresh",
    observedAt: args.observedAt,
    ageMinutes,
    maxAgeMinutes: args.maxAgeMinutes,
    summary: `${args.label} is current at ${formatAgeMinutes(ageMinutes)} old.`
  };
}

function firstTimestamp(...values: Array<string | undefined>): string | undefined {
  return values.find((value) => parseTimestamp(value) !== null);
}


function predictionHasCrossVenueEdge2(doc: any): boolean {
  const review = doc?.review ?? doc;
  return !!(review && review.crossVenueEdgeDetected);
}
function derivePredictionPosture(counts: Record<string, number> | undefined, crossVenueEdgeDetected: boolean): string {
  if ((counts?.["paper-trade"] ?? 0) > 0) return "paper-trade-candidates";
  if ((counts?.watch ?? 0) > 0) return "watch-only";
  if ((counts?.reject ?? 0) > 0) return "reject-only";
  if (crossVenueEdgeDetected) return "cross-venue-edge-found";
  return "no-cross-venue-edge-yet";
}

function summarizePrediction(doc: { review?: any; ts?: string }, learningDoc: any): PredictionSummary {
  const review = doc?.review ?? doc;
  const counts = review?.counts ?? {};
  const topCandidate = review?.topCandidate ?? null;
  const cycleSummary = learningDoc?.recentCycleSummary;

  return {
    posture: derivePredictionPosture(counts, predictionHasCrossVenueEdge2(doc)),
    counts: {
      reject: counts.reject ?? 0,
      watch: counts.watch ?? 0,
      paperTrade: counts["paper-trade"] ?? 0
    },
    topCandidate,
    readyForPaper: Boolean(review?.readyForPaper),
    blockers: Array.isArray(review?.blockers) ? review.blockers : [],
    recommendation: review?.recommendation,
    recentLearning: cycleSummary
      ? {
          totalCycles: cycleSummary.totalCycles,
          structuralWatchCycles: cycleSummary.structuralWatchCycles,
          economicBlockCycles: cycleSummary.economicBlockCycles,
          dominantCandidate: cycleSummary.dominantCandidate
            ? {
                candidateId: cycleSummary.dominantCandidate.candidateId,
                observations: cycleSummary.dominantCandidate.observations,
                bestGrossEdgePct: cycleSummary.dominantCandidate.bestGrossEdgePct,
                latestGrossEdgePct: cycleSummary.dominantCandidate.latestGrossEdgePct,
                latestShortfallPct: cycleSummary.dominantCandidate.latestShortfallPct,
                trend: cycleSummary.dominantCandidate.trend
              }
            : undefined
        }
      : undefined
  };
}

function summarizeCopyDemo(doc: { ideas?: any[]; blockers?: string[]; summary?: string; ts?: string }): CopyDemoSummary {
  const ideas = Array.isArray(doc?.ideas) ? doc.ideas : [];
  const actionableIdeas = ideas.filter((idea) => idea?.action === "shadow-buy");
  const topActionable = actionableIdeas[0] ?? null;
  const topWatch = ideas.find((idea) => idea?.action !== "shadow-buy") ?? null;
  const top = topActionable ?? topWatch;
  const status = actionableIdeas.length > 0
    ? "actionable"
    : ideas.length > 0
      ? "watch-only"
      : "idle";

  return {
    timestamp: doc?.ts,
    status,
    actionableIdeas: actionableIdeas.length,
    totalIdeas: ideas.length,
    summary: doc?.summary,
    blockers: Array.isArray(doc?.blockers) ? doc.blockers : [],
    topIdea: top
      ? {
          id: top.id,
          slug: top.slug,
          action: top.action
        }
      : undefined
  };
}

function summarizeFutures(doc: { posture?: any; sampling?: any }): FuturesSummary {
  const posture = doc?.posture ?? {};
  const sampling = doc?.sampling ?? {};
  const lanes = Array.isArray(sampling?.lanes) ? sampling.lanes : [];

  const laneSummaries: LaneSummary[] = lanes.map((lane: any) => ({
    accountId: lane?.accountId,
    label: lane?.label,
    primaryStrategy: lane?.primaryStrategy,
    focusSymbol: lane?.focusSymbol,
    action: lane?.action
  }));

  return {
    deployable: Boolean(posture?.deployableNow),
    posture: {
      mode: posture?.mode,
      reportStatus: posture?.reportStatus,
      selectedProfile: posture?.selectedProfileDescription,
      whyNotTrading: Array.isArray(posture?.whyNotTrading) ? posture.whyNotTrading : [],
      evidencePlan: posture?.evidencePlan
        ? {
            mode: posture.evidencePlan.mode,
            rationale: posture.evidencePlan.rationale,
            laneDirective: posture.evidencePlan.laneDirective
          }
        : undefined
    },
    sampleSequence: sampling?.sampleSequence,
    laneCount: sampling?.laneCount ?? laneSummaries.length,
    lanes: laneSummaries
  };
}

function summarizeResearch(doc: { runId?: string; startedAt?: string; finishedAt?: string; targetsAttempted?: number; targetsSucceeded?: number; chunksCollected?: number; chunksKept?: number; firecrawlUsed?: boolean; dedupRate?: number; topKeptTitles?: string[]; strategyHypothesesCount?: number; topStrategyHypotheses?: string[]; status?: string; nextAction?: string; blockers?: string[] }): ResearchSummary {
  return {
    runId: doc?.runId,
    startedAt: doc?.startedAt,
    finishedAt: doc?.finishedAt,
    targetsAttempted: doc?.targetsAttempted,
    targetsSucceeded: doc?.targetsSucceeded,
    chunksCollected: doc?.chunksCollected,
    chunksKept: doc?.chunksKept,
    firecrawlUsed: doc?.firecrawlUsed,
    dedupRate: doc?.dedupRate,
    topKeptTitles: Array.isArray(doc?.topKeptTitles) ? doc.topKeptTitles : [],
    strategyHypothesesCount: doc?.strategyHypothesesCount,
    topStrategyHypotheses: Array.isArray(doc?.topStrategyHypotheses) ? doc.topStrategyHypotheses : [],
    status: doc?.status === "degraded" ? "degraded" : doc?.runId ? "healthy" : "degraded",
    nextAction: typeof doc?.nextAction === "string" ? doc.nextAction : undefined,
    blockers: Array.isArray(doc?.blockers) ? doc.blockers : []
  };
}

function trackSymbols(policy: BillTrackPolicy, id: BillMarketTrackId): string[] {
  switch (id) {
    case "prediction":
      return ["Polymarket", "Kalshi", "Manifold"];
    case "futures-core":
      return policy.futuresSymbols;
    case "options-us":
      return policy.optionsUnderlyings;
    case "crypto-liquid":
      return policy.cryptoSymbols;
    case "macro-rates":
      return policy.macroSeries;
    case "long-only-compounder":
      return policy.longOnlySymbols;
  }
}

async function researchTrackArtifacts(baseDir: string, id: BillMarketTrackId): Promise<Array<{ path: string; mtime: string }>> {
  const researchDataDir = resolve(baseDir, DEFAULT_RESEARCH_DATA_DIR);

  switch (id) {
    case "prediction":
      return listFilesWithMtime(resolve(researchDataDir, "prediction"));
    case "futures-core":
      return listFilesWithMtime(resolve(researchDataDir, "market-bars"));
    case "options-us":
      return listFilesWithMtime(resolve(researchDataDir, "options"));
    case "crypto-liquid":
      return listFilesWithMtime(resolve(researchDataDir, "crypto-bars"));
    case "macro-rates":
      return listFilesWithMtime(resolve(researchDataDir, "macro"));
    case "long-only-compounder": {
      const [equities, filings, fundamentals] = await Promise.all([
        listFilesWithMtime(resolve(researchDataDir, "equities")),
        listFilesWithMtime(resolve(researchDataDir, "filings")),
        listFilesWithMtime(resolve(researchDataDir, "fundamentals"))
      ]);
      return [...equities, ...filings, ...fundamentals];
    }
  }
}

function sourceStatsForTrack(sources: SourceCatalogEntry[], trackId: BillMarketTrackId): {
  configuredSources: number;
  missingConfigSources: number;
  automationReadySources: number;
  activeCollectionSource?: SourceCatalogEntry;
  missingPrimarySource?: SourceCatalogEntry;
} {
  const relevant = sources.filter((source) => source.tracks?.includes(trackId));
  const liveCapable = relevant.filter((source) => source.mode !== "catalog-only");
  const missingConfig = [...liveCapable]
    .filter((source) => source.mode === "missing-config")
    .sort((left, right) => {
      const leftScore = (left.automationReady ? 20 : 0) + (left.priority === "primary" ? 10 : 0) + (left.collectionCommand ? 5 : 0);
      const rightScore = (right.automationReady ? 20 : 0) + (right.priority === "primary" ? 10 : 0) + (right.collectionCommand ? 5 : 0);
      return rightScore - leftScore;
    });

  return {
    configuredSources: liveCapable.filter((source) => Boolean(source.configured)).length,
    missingConfigSources: missingConfig.length,
    automationReadySources: liveCapable.filter((source) => Boolean(source.automationReady)).length,
    activeCollectionSource: liveCapable.find((source) => Boolean(source.configured) && Boolean(source.collectionCommand)),
    missingPrimarySource: missingConfig[0]
  };
}

async function summarizeTrackBoard(args: {
  baseDir: string;
  policy: BillTrackPolicy;
  prediction: PredictionSummary;
  copyDemo: CopyDemoSummary;
  futures: FuturesSummary;
  sources: SourceCatalogEntry[];
  research: ResearchSummary;
}): Promise<TrackReadinessSummary[]> {
  const summaries: TrackReadinessSummary[] = [];

  for (const track of args.policy.tracks) {
    const artifacts = await researchTrackArtifacts(args.baseDir, track.id);
    const stats = sourceStatsForTrack(args.sources, track.id);
    let posture: TrackReadinessSummary["posture"] = "idle";
    let nextAction = "No action configured.";
    const notes: string[] = [...track.notes];

    if (track.id === "prediction") {
      const predictionStale = args.prediction.freshness?.status === "stale" || args.prediction.freshness?.status === "missing";
      posture = predictionStale
        ? "collecting"
        : args.prediction.readyForPaper
        ? "actionable"
        : args.copyDemo.status === "actionable" || args.prediction.counts.watch > 0
          ? "shadow"
          : "collecting";
      nextAction = predictionStale
        ? "Refresh the prediction review artifact before trusting the current execution posture."
        : args.prediction.readyForPaper
        ? "Paper the approved cross-venue candidate."
        : args.copyDemo.status === "actionable"
          ? "Shadow the approved copy-demo idea while the core lane stays selective."
          : args.prediction.recommendation ?? "Collect more venue overlap and wait for a cleaner spread.";
      if (args.prediction.freshness) {
        notes.push(args.prediction.freshness.summary);
      }
      if (args.prediction.recentLearning?.dominantCandidate?.candidateId) {
        notes.push(`Dominant recurring pair: ${args.prediction.recentLearning.dominantCandidate.candidateId}.`);
      }
    } else if (track.id === "futures-core") {
      const futuresStale = args.futures.freshness?.status === "stale"
        || args.futures.freshness?.status === "missing"
        || args.futures.datasetFreshness?.status === "stale";
      posture = futuresStale
        ? "collecting"
        : args.futures.deployable
          ? "actionable"
          : args.futures.laneCount > 0
            ? "shadow"
            : "idle";
      nextAction = futuresStale
        ? args.futures.warnings?.[0] ?? args.futures.datasetFreshness?.summary ?? "Refresh the futures dataset and rerun the demo lane sampler before trusting the board."
        : args.futures.deployable
        ? "Advance the top futures demo lane from shadow monitoring toward reviewed demo routing."
        : args.futures.laneCount > 0
          ? "Keep the demo lanes sampling and compare lane outcomes before promotion."
          : "No demo lanes are active; restore the overnight paper loop.";
      if (args.futures.freshness) {
        notes.push(args.futures.freshness.summary);
      }
      if (args.futures.datasetFreshness) {
        notes.push(args.futures.datasetFreshness.summary);
      }
      for (const warning of args.futures.warnings ?? []) {
        notes.push(warning);
      }
    } else if (track.id === "crypto-liquid") {
      posture = artifacts.length > 0 ? "collecting" : stats.missingConfigSources > 0 ? "setup-debt" : "idle";
      nextAction = artifacts.length > 0
        ? "Keep collecting crypto bars and feed them into training."
        : stats.missingPrimarySource?.reason ?? "Enable a crypto-capable data source.";
    } else if (track.id === "options-us") {
      posture = artifacts.length > 0 ? "collecting" : stats.missingConfigSources > 0 ? "setup-debt" : "idle";
      nextAction = artifacts.length > 0
        ? "Use the collected options surfaces to rank later paper paths."
        : stats.missingPrimarySource?.reason ?? "Configure the first keyed options source.";
    } else if (track.id === "macro-rates") {
      posture = artifacts.length > 0 ? "collecting" : stats.missingConfigSources > 0 ? "setup-debt" : "idle";
      nextAction = artifacts.length > 0
        ? "Keep refreshing macro/rates context for regime labels."
        : stats.missingPrimarySource?.reason ?? "Configure the macro context source.";
    } else if (track.id === "long-only-compounder") {
      posture = artifacts.length > 0 ? "collecting" : stats.missingConfigSources > 0 ? "setup-debt" : "idle";
      nextAction = artifacts.length > 0
        ? "Rank quality compounders and stage a shadow long-only sleeve funded from surplus cashflow."
        : stats.missingPrimarySource?.reason ?? "Configure the first durable equities/fundamentals source.";
    }

    summaries.push({
      id: track.id,
      mode: track.mode,
      posture,
      artifactCount: artifacts.length,
      latestArtifactAt: latestTimestamp(artifacts),
      configuredSources: stats.configuredSources,
      missingConfigSources: stats.missingConfigSources,
      automationReadySources: stats.automationReadySources,
      trackedSymbols: trackSymbols(args.policy, track.id),
      nextAction,
      notes,
      freshness:
        track.id === "prediction"
          ? args.prediction.freshness
          : track.id === "futures-core"
            ? args.futures.datasetFreshness ?? args.futures.freshness
            : undefined
    });
  }

  return summaries;
}

function buildActionQueue(args: {
  prediction: PredictionSummary;
  copyDemo: CopyDemoSummary;
  futures: FuturesSummary;
  trackBoard: TrackReadinessSummary[];
  research: ResearchSummary;
}): OpportunityAction[] {
  const actions: OpportunityAction[] = [];
  const predictionStale = args.prediction.freshness?.status === "stale" || args.prediction.freshness?.status === "missing";
  const futuresStale = args.futures.freshness?.status === "stale"
    || args.futures.freshness?.status === "missing"
    || args.futures.datasetFreshness?.status === "stale";
  const researchStale = args.research.freshness?.status === "stale" || args.research.freshness?.status === "missing";

  if (predictionStale) {
    actions.push({
      lane: "prediction",
      stage: "collect",
      priority: 95,
      summary: "Refresh the prediction review lane before trusting the board",
      reason: args.prediction.freshness?.summary ?? "Prediction review freshness is unknown."
    });
  } else if (args.prediction.readyForPaper && args.prediction.topCandidate?.candidateId) {
    actions.push({
      lane: "prediction",
      stage: "execute",
      priority: 100,
      summary: `Paper candidate ${args.prediction.topCandidate.candidateId}`,
      reason: "The cross-venue prediction lane has a candidate that cleared the paper gate."
    });
  } else if (args.copyDemo.status === "actionable" && args.copyDemo.topIdea?.slug) {
    actions.push({
      lane: "prediction",
      stage: "shadow",
      priority: 90,
      summary: `Shadow copy-demo idea ${args.copyDemo.topIdea.slug}`,
      reason: "The public leader cohort produced an actionable in-domain consensus idea."
    });
  } else {
    actions.push({
      lane: "prediction",
      stage: "collect",
      priority: 70,
      summary: "Keep the prediction lane in collection and review mode",
      reason: args.prediction.recommendation ?? "No current prediction idea is strong enough to paper."
    });
  }

  if (futuresStale) {
    actions.push({
      lane: "futures-core",
      stage: "collect",
      priority: 72,
      summary: "Refresh futures data before trusting demo-lane posture",
      reason: args.futures.warnings?.[0] ?? args.futures.datasetFreshness?.summary ?? args.futures.freshness?.summary ?? "Futures inputs are stale."
    });
  } else if (args.futures.laneCount > 0) {
    actions.push({
      lane: "futures-core",
      stage: args.futures.deployable ? "execute" : "shadow",
      priority: args.futures.deployable ? 85 : 78,
      summary: args.futures.deployable
        ? "Advance the strongest futures demo lane"
        : "Keep futures demo lanes sampling overnight",
      reason: args.futures.deployable
        ? "A futures profile is deployable, but the adapter remains guarded."
        : args.futures.posture?.evidencePlan?.rationale
          ?? args.futures.posture?.whyNotTrading?.[0]
          ?? "The futures system is still proving itself in demo. This lane stays ahead of generic collection because it is the nearest path to cashflow."
    });
  }

  for (const track of args.trackBoard.filter((track) =>
    track.id === "options-us"
    || track.id === "crypto-liquid"
    || track.id === "macro-rates"
    || track.id === "long-only-compounder"
  )) {
    actions.push({
      lane: track.id,
      stage: track.posture === "setup-debt" ? "configure" : "collect",
      priority:
        track.id === "options-us" ? 55
        : track.id === "crypto-liquid" ? 50
        : track.id === "long-only-compounder" ? 48
        : 45,
      summary: track.nextAction,
      reason: track.posture === "setup-debt"
        ? "The track is in-domain but blocked on source setup."
        : track.id === "long-only-compounder"
          ? "The compounder lane should be built as a reserve-fed sleeve, not treated like another fast execution loop."
          : "The track should keep collecting evidence without widening into execution yet."
    });
  }

  actions.push({
    lane: "researcher",
    stage: args.research.runId && !researchStale ? "research" : "collect",
    priority: args.research.runId && !researchStale ? 40 : 52,
    summary: args.research.nextAction ?? (args.research.runId && !researchStale
      ? "Researcher has a fresh run; keep ingesting and curating"
      : "Researcher needs a validated run"),
    reason: args.research.blockers?.[0]
      ?? args.research.freshness?.summary
      ?? (args.research.runId
        ? "The researcher lane is generating corpus updates and should keep feeding the machine."
        : "No validated researcher run is available yet.")
  });

  return actions.sort((left, right) => right.priority - left.priority);
}

function buildAttention(snapshot: OpportunitySnapshot): string[] {
  const attention: string[] = [];

  if (snapshot.prediction.freshness?.status === "stale" || snapshot.prediction.freshness?.status === "missing") {
    attention.push(snapshot.prediction.freshness.summary);
  }
  if (snapshot.copyDemo.freshness?.status === "stale" || snapshot.copyDemo.freshness?.status === "missing") {
    attention.push(snapshot.copyDemo.freshness.summary);
  }
  if (snapshot.futures.freshness?.status === "stale" || snapshot.futures.freshness?.status === "missing") {
    attention.push(snapshot.futures.freshness.summary);
  }
  if (snapshot.futures.datasetFreshness?.status === "stale") {
    attention.push(snapshot.futures.datasetFreshness.summary);
  }
  if (snapshot.research.freshness?.status === "stale" || snapshot.research.freshness?.status === "missing") {
    attention.push(snapshot.research.freshness.summary);
  }

  if (!snapshot.prediction.readyForPaper) {
    const dominant = snapshot.prediction.recentLearning?.dominantCandidate;
    if (dominant?.candidateId) {
      attention.push(`Prediction lane still lacks a paper candidate. Dominant pair ${dominant.candidateId} has shortfall ${dominant.latestShortfallPct ?? "unknown"}% and trend ${dominant.trend ?? "unknown"}.`);
    } else {
      attention.push("Prediction lane still lacks a paper candidate edge after multiple cycles.");
    }
  }
  if (snapshot.copyDemo.status !== "actionable") {
    attention.push("Copy-demo lane is idle or watch-only under the founder-approved domain filter.");
  }
  if (!snapshot.futures.deployable) {
    attention.push("Futures demo lanes are running, but no deployable profile is ready for reviewed routing yet.");
  }
  if ((snapshot.research.strategyFocusStrategies?.length ?? 0) > 0 || (snapshot.research.strategyFocusSymbols?.length ?? 0) > 0) {
    attention.push(`Research strategy feed is biasing ${snapshot.research.strategyFocusStrategies?.join(", ") || "current strategies"} on ${snapshot.research.strategyFocusSymbols?.join(", ") || "current futures symbols"}.`);
  }

  const setupDebtTracks = snapshot.trackBoard.filter((track) => track.posture === "setup-debt");
  if (setupDebtTracks.length > 0) {
    attention.push(`Research tracks still have setup debt: ${setupDebtTracks.map((track) => track.id).join(", ")}.`);
  }
  if (!snapshot.research.runId) {
    attention.push("Researcher has not produced a validated run yet.");
  } else if (!snapshot.research.firecrawlUsed) {
    attention.push("Researcher is still running without Firecrawl; hardened/JS-heavy sites remain a weak spot.");
  }
  for (const blocker of snapshot.research.blockers ?? []) {
    attention.push(`Researcher: ${blocker}`);
  }
  for (const line of snapshot.runtimeHealth.summaryLines) {
    attention.push(line);
  }

  return attention;
}

function buildRuntimeHealth(args: {
  billHealthDoc: any;
  prediction: PredictionSummary;
  copyDemo: CopyDemoSummary;
  futures: FuturesSummary;
  research: ResearchSummary;
  trackBoard: TrackReadinessSummary[];
  now: string;
}): OpportunitySnapshot["runtimeHealth"] {
  const warnings = Array.isArray(args.billHealthDoc?.warnings)
    ? [...args.billHealthDoc.warnings]
    : [];
  const freshnessWarnings = [
    args.prediction.freshness,
    args.copyDemo.freshness,
    args.futures.freshness,
    args.futures.datasetFreshness,
    args.research.freshness
  ]
    .filter((value): value is ArtifactFreshness => Boolean(value))
    .filter((value) => value.status !== "fresh")
    .map((value) => value.summary);
  const summaryLines = Array.from(new Set([
    ...warnings.slice(0, 4),
    ...freshnessWarnings.slice(0, 4)
  ])).slice(0, 8);
  const observedAt = firstTimestamp(args.billHealthDoc?.timestamp);
  const status = freshnessWarnings.some((line) => line.includes("missing"))
    ? "critical"
    : summaryLines.length > 0
      ? "degraded"
      : "healthy";

  return {
    status,
    observedAt,
    warnings,
    summaryLines
  };
}

export async function buildOpportunitySnapshot(options?: OpportunitySnapshotOptions): Promise<OpportunitySnapshot> {
  const env = options?.env ?? process.env;
  const baseDir = resolveRuntimeRepoRoot({
    importMetaUrl: import.meta.url,
    cwd: process.cwd(),
    explicitBaseDir: options?.baseDir,
    env
  });
  const stateDir = resolve(baseDir, options?.stateDir ?? DEFAULT_STATE_DIR);
  const researchDir = resolve(baseDir, options?.researchDir ?? DEFAULT_RESEARCHER_DIR);
  const sourceCatalogPath = resolve(baseDir, options?.sourceCatalogPath ?? DEFAULT_SOURCE_CATALOG_PATH);
  const now = options?.now ? options.now() : new Date().toISOString();

  const reviewArtifact = await readJsonArtifact<{ review?: any; ts?: string }>(resolve(stateDir, "prediction-review.latest.json"));
  const copyArtifact = await readJsonArtifact<{ ideas?: unknown[]; blockers?: string[]; summary?: string; ts?: string }>(resolve(stateDir, "prediction-copy-demo.latest.json"));
  const futuresArtifact = await readJsonArtifact<{ ts?: string; posture?: any; sampling?: any; data?: any }>(resolve(stateDir, "futures-demo.latest.json"));
  const researchArtifact = await readJsonArtifact<any>(resolve(researchDir, "latest-run.json"));
  const learningArtifact = await readJsonArtifact<any>(resolve(stateDir, "prediction-learning.latest.json"));
  const sourceCatalog = await readJsonSafe<SourceCatalogEntry[]>(sourceCatalogPath);
  const billHealthArtifact = await readJsonArtifact<any>(resolve(baseDir, DEFAULT_BILL_HEALTH_PATH));

  const policy = buildTrackPolicyFromEnv(env);
  const prediction = summarizePrediction(reviewArtifact.data ?? {}, learningArtifact.data ?? {});
  prediction.freshness = buildFreshness({
    label: "Prediction review",
    observedAt: firstTimestamp(reviewArtifact.data?.ts, reviewArtifact.data?.review?.ts, learningArtifact.data?.ts, reviewArtifact.mtime),
    now,
    maxAgeMinutes: 180
  });
  const copyDemo = summarizeCopyDemo(copyArtifact.data ?? {});
  copyDemo.freshness = buildFreshness({
    label: "Copy-demo",
    observedAt: firstTimestamp(copyArtifact.data?.ts, copyArtifact.mtime),
    now,
    maxAgeMinutes: 360
  });
  const futures = summarizeFutures(futuresArtifact.data ?? {});
  futures.freshness = buildFreshness({
    label: "Futures demo lane",
    observedAt: firstTimestamp(futuresArtifact.data?.sampling?.ts, futuresArtifact.data?.ts, futuresArtifact.mtime),
    now,
    maxAgeMinutes: 720
  });
  const selectedDatasetPath = typeof futuresArtifact.data?.data?.path === "string"
    ? resolve(futuresArtifact.data.data.path)
    : undefined;
  const requestedDatasetPath = typeof futuresArtifact.data?.data?.requestedPath === "string"
    ? resolve(futuresArtifact.data.data.requestedPath)
    : undefined;
  const selectedDatasetMatchesRequested = !selectedDatasetPath || !requestedDatasetPath || selectedDatasetPath === requestedDatasetPath;
  const datasetObservedAt = typeof futuresArtifact.data?.data?.inspection?.endTs === "string"
    ? futuresArtifact.data.data.inspection.endTs
    : undefined;
  const staleHours = Number(futuresArtifact.data?.data?.preflight?.priorStatus?.staleHours ?? Number.NaN);
  const shouldRefresh = Boolean(futuresArtifact.data?.data?.preflight?.priorStatus?.shouldRefresh);
  futures.datasetFreshness = datasetObservedAt
    ? buildFreshness({
        label: "Futures dataset",
        observedAt: datasetObservedAt,
        now,
        maxAgeMinutes: 720
      })
    : Number.isFinite(staleHours)
      ? {
          status: staleHours * 60 > 720 ? "stale" : "fresh",
          observedAt: futuresArtifact.data?.data?.inspection?.endTs,
          ageMinutes: staleHours * 60,
          maxAgeMinutes: 720,
          summary: staleHours * 60 > 720
            ? `Futures dataset is stale at ${formatAgeMinutes(staleHours * 60)} old.`
            : `Futures dataset is current at ${formatAgeMinutes(staleHours * 60)} old.`
        }
      : shouldRefresh
        ? {
            status: "stale",
            maxAgeMinutes: 720,
            summary: "Futures dataset requested refresh before the latest sampler run."
          }
        : undefined;
  const priorStatusReasons = Array.isArray(futuresArtifact.data?.data?.preflight?.priorStatus?.reasons)
    ? futuresArtifact.data.data.preflight.priorStatus.reasons
    : [];
  const preflightWarnings = Array.isArray(futuresArtifact.data?.data?.preflight?.warnings)
    ? futuresArtifact.data.data.preflight.warnings
    : [];
  futures.warnings = [
    ...((futures.datasetFreshness?.status !== "fresh" || selectedDatasetMatchesRequested) ? priorStatusReasons : []),
    ...preflightWarnings
  ];
  const research = summarizeResearch(researchArtifact.data ?? {});
  const researchStrategyFeed = await loadLatestResearchStrategyFeed(resolve(researchDir, "strategy-hypotheses.latest.json"));
  research.strategyFocusStrategies = researchStrategyFeed?.preferredStrategies ?? [];
  research.strategyFocusSymbols = researchStrategyFeed?.preferredSymbols ?? [];
  research.topStrategyHypotheses = research.topStrategyHypotheses?.length
    ? research.topStrategyHypotheses
    : (researchStrategyFeed?.topStrategyTitles ?? []);
  research.strategyHypothesesCount = research.strategyHypothesesCount ?? researchStrategyFeed?.strategyCount;
  research.freshness = buildFreshness({
    label: "Researcher latest run",
    observedAt: firstTimestamp(researchArtifact.data?.finishedAt, researchArtifact.data?.startedAt, researchArtifact.mtime),
    now,
    maxAgeMinutes: 24 * 60
  });
  if (!research.nextAction) {
    research.nextAction = research.runId && research.freshness.status === "fresh"
      ? "Keep ingesting and curating the next highest-priority researcher targets."
      : "Run the researcher lane again and refresh the corpus artifacts.";
  }
  research.blockers = Array.from(new Set([
    ...(research.blockers ?? []),
    ...(
      research.firecrawlUsed === false
      && !(research.blockers ?? []).some((blocker) => blocker.toLowerCase().includes("firecrawl"))
        ? ["Firecrawl fallback is unavailable or disabled, so hardened sites remain weak."]
        : []
    ),
    ...(research.freshness.status !== "fresh" ? [research.freshness.summary] : [])
  ]));
  if ((research.blockers?.length ?? 0) > 0) {
    research.status = "degraded";
  }
  const trackBoard = await summarizeTrackBoard({
    baseDir,
    policy,
    prediction,
    copyDemo,
    futures,
    sources: Array.isArray(sourceCatalog) ? sourceCatalog : [],
    research
  });
  const runtimeHealth = buildRuntimeHealth({
    billHealthDoc: billHealthArtifact.data ?? {},
    prediction,
    copyDemo,
    futures,
    research,
    trackBoard,
    now
  });
  const actionQueue = buildActionQueue({
    prediction,
    copyDemo,
    futures,
    trackBoard,
    research
  });
  const fundPlan = buildFundPlan({
    env,
    policy,
    trackBoard,
    runtimeHealth,
    primaryAction: actionQueue[0] ?? null
  });

  const snapshot: OpportunitySnapshot = {
    timestamp: now,
    prediction,
    copyDemo,
    futures,
    research,
    runtimeHealth,
    trackBoard,
    fundPlan,
    primaryAction: actionQueue[0] ?? {
      lane: "prediction",
      stage: "collect",
      priority: 0,
      summary: "No action available",
      reason: "No track produced a current action."
    },
    actionQueue,
    attention: []
  };

  snapshot.attention = buildAttention(snapshot);
  return snapshot;
}
