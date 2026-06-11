import { readdir, readFile, stat, writeFile, mkdir } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { buildFounderNotesIntake } from "../research/founderNotes.js";
import { buildTrackPolicyFromEnv, type BillMarketTrackId } from "../research/tracks.js";

type LaneStatus = "blocked" | "research" | "shadow" | "paper-ready" | "live-ready";

interface ArtifactFreshness {
  path: string;
  present: boolean;
  ageMinutes: number | null;
}

interface LaneScore {
  lane: BillMarketTrackId;
  status: LaneStatus;
  score: number;
  dataScore: number;
  edgeScore: number;
  modelScore: number;
  executionScore: number;
  riskScore: number;
  capacityScore: number;
  reflexivityPenalty: number;
  blockers: string[];
  requiredData: string[];
  methodsToUse: string[];
  nextActions: string[];
}

export interface CompetitiveReadinessReport {
  command: "competitive-readiness";
  generatedAt: string;
  outputPath: string;
  headline: string;
  liveExecutionAllowed: boolean;
  portfolioScore: number;
  lanes: LaneScore[];
  globalBlockers: string[];
  dataShoppingList: string[];
  founderDirectivePriority: string[];
  operatingDoctrine: string[];
  scalingLawAnswer: {
    verdict: string;
    why: string[];
    practicalImplication: string;
  };
}

const DEFAULT_OUTPUT_PATH = ".rumbling-hedge/state/competitive-readiness.latest.json";

function clamp01(value: number): number {
  return Math.min(Math.max(value, 0), 1);
}

function score100(value: number): number {
  return Number((clamp01(value) * 100).toFixed(1));
}

async function readJsonSafe<T>(path: string): Promise<T | null> {
  try {
    return JSON.parse(await readFile(path, "utf8")) as T;
  } catch {
    return null;
  }
}

async function freshness(path: string, nowMs: number): Promise<ArtifactFreshness> {
  try {
    const info = await stat(path);
    return {
      path,
      present: true,
      ageMinutes: Number(((nowMs - info.mtimeMs) / 60_000).toFixed(1))
    };
  } catch {
    return { path, present: false, ageMinutes: null };
  }
}

async function countFiles(path: string): Promise<number> {
  try {
    return (await readdir(path)).length;
  } catch {
    return 0;
  }
}

function weightedScore(parts: Omit<LaneScore, "lane" | "status" | "score" | "blockers" | "requiredData" | "methodsToUse" | "nextActions">): number {
  const raw =
    (parts.dataScore * 0.22)
    + (parts.edgeScore * 0.24)
    + (parts.modelScore * 0.16)
    + (parts.executionScore * 0.16)
    + (parts.riskScore * 0.14)
    + (parts.capacityScore * 0.08)
    - parts.reflexivityPenalty;
  return score100(raw / 100);
}

function statusFromScore(score: number, blockers: string[], liveAllowed: boolean): LaneStatus {
  if (blockers.some((item) => item.includes("missing") || item.includes("unsafe-live"))) return "blocked";
  if (score >= 82 && liveAllowed) return "live-ready";
  if (score >= 70) return "paper-ready";
  if (score >= 52) return "shadow";
  return "research";
}

function num(value: unknown): number {
  return typeof value === "number" && Number.isFinite(value) ? value : 0;
}

function enabled(env: NodeJS.ProcessEnv, key: string): boolean {
  return env[key] === "true";
}

function methods(lane: BillMarketTrackId): string[] {
  switch (lane) {
    case "prediction":
      return [
        "cross-venue semantic arb with strict settlement/line/expiry matching",
        "copy-trading cohort shadowing",
        "fee-aware Kelly/min-ticket sizing",
        "candidate recurrence and calibration ledger",
        "flow acceleration on market probabilities"
      ];
    case "futures-core":
      return [
        "regime-gated trend/mean-reversion selection",
        "walk-forward with embargo",
        "Kronos/TimesFM forecast-as-signal, not pattern confirmation",
        "cross-asset macro context: rates, dollar, oil, metals, bonds",
        "risk parity and volatility targeting"
      ];
    case "options-us":
      return [
        "volatility risk premium and term-structure carry",
        "dealer gamma and charm/vanna context",
        "skew/put-call surface anomalies",
        "earnings/event vol crush filters",
        "defined-risk paper spreads before naked exposure"
      ];
    case "crypto-liquid":
      return [
        "cross-exchange/futures basis context",
        "funding-rate carry",
        "Kronos short-horizon state forecasts",
        "liquidation/open-interest regime filters",
        "calendar/session microstructure without HFT"
      ];
    case "macro-rates":
      return [
        "yield-curve and central-bank regime labeling",
        "CPI/NFP/FOMC event surprise mapping",
        "COT/positioning extremes",
        "VIX term-structure risk state",
        "macro-conditioned allocation gates for other lanes"
      ];
    case "long-only-compounder":
      return [
        "quality/value/momentum multi-factor ranking",
        "filing and earnings-call LLM extraction",
        "drawdown-aware rebalancing",
        "sector/correlation concentration caps",
        "cashflow-funded capital allocation"
      ];
  }
}

export async function buildCompetitiveReadinessReport(args: {
  baseDir?: string;
  env?: NodeJS.ProcessEnv;
  now?: () => string;
  outputPath?: string;
} = {}): Promise<CompetitiveReadinessReport> {
  const baseDir = resolve(args.baseDir ?? process.cwd());
  const env = args.env ?? process.env;
  const generatedAt = args.now?.() ?? new Date().toISOString();
  const nowMs = Date.parse(generatedAt);
  const outputPath = resolve(baseDir, args.outputPath ?? DEFAULT_OUTPUT_PATH);
  const stateDir = resolve(baseDir, ".rumbling-hedge/state");
  const runtimePredictionDir = resolve(baseDir, ".rumbling-hedge/runtime/prediction");
  const researchPredictionDir = resolve(baseDir, ".rumbling-hedge/research/prediction-market-analysis");

  const [predictionCycle, predictionReview, promotionState, strategyFactory, liveReadiness, health, timesfm, kronosHealth, macroContext, blessedEdges, orbOosReplay] = await Promise.all([
    readJsonSafe<any>(resolve(stateDir, "prediction-cycle.latest.json")),
    readJsonSafe<any>(resolve(stateDir, "prediction-review.latest.json")),
    readJsonSafe<any>(resolve(stateDir, "promotion-state.json")),
    readJsonSafe<any>(resolve(stateDir, "strategy-factory.latest.json")),
    readJsonSafe<any>(resolve(stateDir, "live-readiness.latest.json")),
    readJsonSafe<any>(resolve(baseDir, ".rumbling-hedge/logs/bill-health.latest.json")),
    readJsonSafe<any>(resolve(baseDir, ".rumbling-hedge/research/timesfm/readiness.json")),
    readJsonSafe<any>(resolve(stateDir, "kronos-health.latest.json")),
    readJsonSafe<any>(resolve(baseDir, ".rumbling-hedge/research/macro/free-macro-context.latest.json")),
    readJsonSafe<any>(resolve(stateDir, "blessed-edges.json")),
    readJsonSafe<any>(resolve(stateDir, "vol-regime-oos-replay.orb3m.latest.json"))
  ]);
  const [predictionFresh, strategyFresh, liveFresh, macroFresh] = await Promise.all([
    freshness(resolve(stateDir, "prediction-cycle.latest.json"), nowMs),
    freshness(resolve(stateDir, "strategy-factory.latest.json"), nowMs),
    freshness(resolve(stateDir, "live-readiness.latest.json"), nowMs),
    freshness(resolve(baseDir, ".rumbling-hedge/research/macro/free-macro-context.latest.json"), nowMs)
  ]);

  const trackPolicy = buildTrackPolicyFromEnv(env);
  const founderNotes = await buildFounderNotesIntake({
    now: () => generatedAt,
    outputPath: resolve(baseDir, ".rumbling-hedge/research/founder-notes/strategy-directives.latest.json")
  });
  const livePredictionArmed = env.BILL_PREDICTION_EXECUTION_MODE === "live"
    || env.BILL_PREDICTION_LIVE_EXECUTION_ENABLED === "true";
  const liveFuturesArmed = env.RH_LIVE_EXECUTION_ENABLED === "true";
  const liveExecutionAllowed = false;
  const predictionCounts = predictionCycle?.scan?.counts ?? predictionReview?.review?.counts ?? {};
  const venuesHealthy = num(predictionCycle?.venuesHealthy);
  const predictionFiles = await countFiles(runtimePredictionDir);
  const predictionResearchFiles = await countFiles(researchPredictionDir);

  const lanes: LaneScore[] = trackPolicy.tracks.map((track) => {
    const active = track.mode === "active";
    const blockers: string[] = [];
    const requiredData: string[] = [];
    const nextActions: string[] = [];
    let dataScore = 15;
    let edgeScore = 5;
    let modelScore = 10;
    let executionScore = active ? 20 : 5;
    let riskScore = 40;
    let capacityScore = 40;
    let reflexivityPenalty = 8;

    if (track.id === "prediction") {
      dataScore = score100((Math.min(venuesHealthy, 3) / 3) * 0.55 + Math.min(predictionFiles, 8) / 8 * 0.25 + Math.min(predictionResearchFiles, 8) / 8 * 0.2);
      edgeScore = score100(Math.min(num(predictionCounts["paper-trade"]), 3) / 3 * 0.7 + Math.min(num(predictionCounts.watch), 5) / 5 * 0.3);
      modelScore = score100(0.55 + (predictionCycle?.training ? 0.2 : 0) + (predictionCycle?.copyDemo?.enabled ? 0.1 : 0));
      executionScore = score100(active ? 0.65 : 0.2);
      riskScore = livePredictionArmed ? 20 : 75;
      capacityScore = 35;
      reflexivityPenalty = 18;
      if (venuesHealthy < 2) blockers.push("missing-healthy-venue-coverage");
      if (num(predictionCounts["paper-trade"]) === 0) blockers.push("missing-paper-candidates");
      if (livePredictionArmed) blockers.push("unsafe-live-prediction-armed");
      requiredData.push("deeper recurring PM snapshots with resolution outcomes", "maker/taker fee and fillability observations", "Metaculus/Insight/Manifold mirror coverage");
      nextActions.push("keep 60s scan cadence", "resolve historical PM candidates for calibration", "do not re-enable live until paper fills survive settlement review");
    } else if (track.id === "futures-core") {
      // Blessed-edge OOS replay path (same evidence chain liveReadinessGate accepts):
      // verified walkforward folds replayed OOS. Accept only when the replay maps to a
      // blessed edge and clears the blessed promotion criteria with every window positive.
      const blessedIds = new Set(
        (Array.isArray(blessedEdges?.edges) ? blessedEdges.edges : []).map((e: any) => String(e?.id))
      );
      const replayWindows = Array.isArray(orbOosReplay?.windows) ? orbOosReplay.windows : [];
      const replayBlessed = blessedIds.has(String(orbOosReplay?.strategy));
      const replayAllPositive = replayWindows.length >= 4
        && replayWindows.every((w: any) => num(w?.test?.trades) > 0 && num(w?.test?.netR) > 0);
      const replayAggregateSolid = num(orbOosReplay?.aggregateOos?.trades) >= 30
        && num(orbOosReplay?.aggregateOos?.profitFactor) >= 1.5;
      const blessedReplayDeployable = replayBlessed && replayAllPositive && replayAggregateSolid;
      const factoryOosWindows = num(strategyFactory?.rollingOos?.aggregate?.windowsEvaluated ?? strategyFactory?.oos?.windowsEvaluated);
      const oosWindows = Math.max(factoryOosWindows, blessedReplayDeployable ? replayWindows.length : 0);
      const deployable = Boolean(strategyFactory?.deployableNow ?? liveReadiness?.final?.report?.deployableNow) || blessedReplayDeployable;
      dataScore = score100(Math.min(oosWindows, 8) / 8 * 0.4 + (strategyFresh.present ? 0.2 : 0) + (liveFresh.present ? 0.15 : 0) + (macroFresh.present ? 0.1 : 0) + 0.15);
      edgeScore = deployable ? 70 : score100(Math.min(oosWindows, 8) / 8 * 0.35);
      modelScore = score100((timesfm ? 0.25 : 0) + (kronosHealth ? 0.25 : 0) + 0.25);
      executionScore = score100(active ? 0.45 : 0.15);
      riskScore = liveFuturesArmed ? 20 : 70;
      capacityScore = 65;
      reflexivityPenalty = 10;
      if (!deployable) blockers.push("missing-positive-oos-deployability");
      if (oosWindows < 4) blockers.push("missing-rolling-oos-depth");
      if (liveFuturesArmed) blockers.push("unsafe-live-futures-armed");
      requiredData.push("tick/L2 or at least bid-ask bars", "VIX term structure", "COT/dealer positioning", "Kronos historical forecast columns");
      nextActions.push(macroFresh.present ? "join free macro-context columns into futures backtests" : "run macro-context-free to create the first free macro regime artifact", "run Kronos/TimesFM historical forecast batch", "promote only strategies with positive deflated OOS expectancy");
    } else if (track.id === "options-us") {
      dataScore = env.POLYGON_API_KEY || env.ALPACA_API_KEY ? 45 : 20;
      edgeScore = 10;
      modelScore = 35;
      executionScore = 5;
      riskScore = 55;
      capacityScore = 55;
      reflexivityPenalty = 12;
      blockers.push("missing-options-chain-history-and-paper-router");
      requiredData.push("OPRA option chains", "IV surface history", "dealer gamma/GEX", "earnings calendar", "borrow/dividend/corporate actions");
      nextActions.push("build options chain recorder before strategies", "start with defined-risk spreads and VRP shadow PnL");
    } else if (track.id === "crypto-liquid") {
      dataScore = 30;
      edgeScore = 10;
      modelScore = kronosHealth ? 45 : 25;
      executionScore = 5;
      riskScore = 50;
      capacityScore = 60;
      reflexivityPenalty = 14;
      blockers.push("missing-venue-paper-router-and-orderbook-context");
      requiredData.push("exchange order books", "funding rates", "open interest", "liquidation feed", "basis/perp curves");
      nextActions.push("collect funding/OI before any crypto execution", "use Kronos as signal only after historical forecast backtest");
    } else if (track.id === "macro-rates") {
      const freshMacroContext = macroFresh.present && (macroFresh.ageMinutes ?? Number.POSITIVE_INFINITY) < 24 * 60;
      dataScore = score100((env.FRED_API_KEY ? 0.45 : 0) + (freshMacroContext ? 0.35 : macroFresh.present ? 0.2 : 0) + 0.1);
      edgeScore = 15;
      modelScore = macroContext?.derived?.riskRegime ? 45 : 35;
      executionScore = 0;
      riskScore = macroContext?.derived?.riskRegime === "stress" ? 85 : 75;
      capacityScore = 80;
      reflexivityPenalty = 5;
      blockers.push("context-lane-not-execution-lane");
      requiredData.push("FRED/rates history", "economic calendar surprises", "COT positioning", "yield curve", "VIX futures curve");
      nextActions.push(freshMacroContext ? "use free macro tail score as a sizing gate, not an execution signal" : "refresh the free Yahoo macro context artifact daily", "make macro-rates a gate for futures/options, not a standalone trader");
    } else {
      dataScore = 25;
      edgeScore = 10;
      modelScore = 30;
      executionScore = 0;
      riskScore = 80;
      capacityScore = 90;
      reflexivityPenalty = 4;
      blockers.push("capital-allocation-lane-not-cashflow-source-yet");
      requiredData.push("fundamentals", "filings", "earnings-call transcripts", "factor library", "corporate actions");
      nextActions.push("keep long-only research-only until active lanes generate cashflow evidence");
    }

    const score = weightedScore({ dataScore, edgeScore, modelScore, executionScore, riskScore, capacityScore, reflexivityPenalty });
    return {
      lane: track.id,
      status: statusFromScore(score, blockers, liveExecutionAllowed),
      score,
      dataScore,
      edgeScore,
      modelScore,
      executionScore,
      riskScore,
      capacityScore,
      reflexivityPenalty,
      blockers,
      requiredData,
      methodsToUse: methods(track.id),
      nextActions
    };
  });

  const globalBlockers: string[] = [];
  if (livePredictionArmed) globalBlockers.push("prediction live execution is armed");
  if (liveFuturesArmed) globalBlockers.push("futures live execution is armed");
  if ((health?.disk?.usedPct ?? 0) > 88) globalBlockers.push("disk pressure is high");
  if (lanes.every((lane) => lane.edgeScore < 35)) globalBlockers.push("no lane has enough edge evidence for live capital");

  const portfolioScore = score100(lanes.reduce((sum, lane) => sum + lane.score, 0) / Math.max(lanes.length, 1) / 100);
  const dataShoppingList = [...new Set(lanes.flatMap((lane) => lane.requiredData))];
  for (const item of founderNotes.directives.flatMap((directive) => directive.requiredData)) {
    if (!dataShoppingList.includes(item)) dataShoppingList.push(item);
  }
  const headline = portfolioScore >= 70
    ? "Bill is approaching paper/live competitiveness, but live remains approval-gated."
    : "Bill is not yet competitively profitable; build data depth and edge evidence before live capital.";

  const report: CompetitiveReadinessReport = {
    command: "competitive-readiness",
    generatedAt,
    outputPath,
    headline,
    liveExecutionAllowed,
    portfolioScore,
    lanes,
    globalBlockers,
    dataShoppingList,
    founderDirectivePriority: founderNotes.priorityOrder,
    operatingDoctrine: [
      "No live execution without positive OOS evidence after costs, fill simulation, and capacity limits.",
      "Use foundation time-series models as alpha candidates, then demand walk-forward proof.",
      "Treat macro/rates/news/options context as gates unless a venue-specific paper router exists.",
      "Prefer slow information alpha, relative value, and cross-lane confirmation; avoid HFT latency races.",
      "Every profitable-looking opportunity must survive settlement semantics, fees, slippage, and repeatability checks."
    ],
    scalingLawAnswer: {
      verdict: "Finance has conditional scaling laws, not LLM-style monotonic scaling.",
      why: [
        "More data helps only when it increases effective signal after non-stationarity and costs.",
        "Markets are reflexive: exploiting an edge reduces or removes that edge.",
        "The useful scaling axis is entropy reduction per dollar of risk, not tokens or parameters alone.",
        "RL/self-play is useful for execution/risk policy, but market simulators must be calibrated against real fill and regime data."
      ],
      practicalImplication: "Bill should scale data, models, and agents only behind lane-level evidence gates, with paper trading used as the market simulator correction layer."
    }
  };

  await mkdir(dirname(outputPath), { recursive: true });
  await writeFile(outputPath, `${JSON.stringify(report, null, 2)}\n`, "utf8");
  return report;
}
