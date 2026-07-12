import type { BillMarketTrackId, BillTrackPolicy } from "../research/tracks.js";
import type { OpportunityAction, TrackReadinessSummary } from "./orchestrator.js";

export interface FundCapitalBucket {
  id: "reserve" | "active-risk" | "incubation" | "compounder";
  label: string;
  targetPct: number;
  deployedPct: number;
  status: "ready" | "building" | "held";
  mandate: string;
}

export interface FundTrackDirective {
  id: BillMarketTrackId;
  role: "cashflow" | "incubation" | "context" | "compounder";
  mode: TrackReadinessSummary["mode"];
  posture: TrackReadinessSummary["posture"];
  suggestedCapitalPct: number;
  branchCondition: string;
  summary: string;
}

export interface FundGrowthStep {
  stage: "stabilize-core" | "branch-adjacent" | "seed-compounder" | "compound";
  title: string;
  status: "now" | "next" | "later";
  condition: string;
  action: string;
}

export interface FundPlan {
  mode: "stabilize-core" | "branch-adjacent" | "seed-compounder" | "compound";
  nextCapitalMove: string;
  reservePolicy: string;
  buckets: FundCapitalBucket[];
  tracks: FundTrackDirective[];
  growthLadder: FundGrowthStep[];
  notes: string[];
}

function readPct(env: NodeJS.ProcessEnv, key: string, fallback: number): number {
  const raw = env[key];
  if (!raw) return fallback;
  const parsed = Number.parseFloat(raw);
  if (!Number.isFinite(parsed)) return fallback;
  return Math.max(0, Math.min(100, Number(parsed.toFixed(2))));
}

function roundPct(value: number): number {
  return Number(value.toFixed(2));
}

function roleForTrack(id: BillMarketTrackId): FundTrackDirective["role"] {
  switch (id) {
    case "prediction":
    case "futures-core":
      return "cashflow";
    case "options-us":
    case "crypto-liquid":
      return "incubation";
    case "macro-rates":
      return "context";
    case "long-only-compounder":
      return "compounder";
  }
}

function suggestedCapitalPct(track: TrackReadinessSummary): number {
  switch (track.id) {
    case "prediction":
      return track.mode === "active" ? 15 : 0;
    case "futures-core":
      return track.mode === "active" ? 10 : 0;
    case "options-us":
      return track.mode !== "disabled" ? 4 : 0;
    case "crypto-liquid":
      return track.mode !== "disabled" ? 3 : 0;
    case "macro-rates":
      return track.mode !== "disabled" ? 1 : 0;
    case "long-only-compounder":
      return track.mode !== "disabled" ? 10 : 0;
  }
}

function branchCondition(track: TrackReadinessSummary): string {
  switch (track.id) {
    case "prediction":
      return "Keep active while cross-venue net edge can survive fees and liquidity.";
    case "futures-core":
      return "Keep active while demo lanes are sampling cleanly and promotion evidence is improving.";
    case "options-us":
      return "Only widen after source setup is complete and its own paper path exists.";
    case "crypto-liquid":
      return "Only widen after a venue-specific paper path and risk model exist.";
    case "macro-rates":
      return "Use as context, not as a stand-alone cashflow sleeve.";
    case "long-only-compounder":
      return "Seed only from realized cashflow after core tracks are stable and reserve capital stays intact.";
  }
}

function trackSummary(track: TrackReadinessSummary): string {
  if (track.posture === "actionable") {
    return `${track.id} is the nearest capital-ready lane.`;
  }
  if (track.posture === "shadow") {
    return `${track.id} is close enough to learn from shadow or paper behavior without widening authority.`;
  }
  if (track.posture === "setup-debt") {
    return `${track.id} is blocked by missing market-data or operational setup.`;
  }
  if (track.posture === "collecting") {
    return `${track.id} is accumulating evidence but is not yet eligible for a wider sleeve.`;
  }
  return `${track.id} is parked until better evidence or setup arrives.`;
}

export function buildFundPlan(args: {
  env?: NodeJS.ProcessEnv;
  policy: BillTrackPolicy;
  trackBoard: TrackReadinessSummary[];
  runtimeHealth: { status: "healthy" | "degraded" | "critical" };
  primaryAction?: OpportunityAction | null;
}): FundPlan {
  const env = args.env ?? process.env;
  const reserveTarget = readPct(env, "BILL_CAPITAL_RESERVE_PCT", 55);
  const activeRiskTarget = readPct(env, "BILL_CAPITAL_ACTIVE_RISK_PCT", 25);
  const incubationTarget = readPct(env, "BILL_CAPITAL_INCUBATION_PCT", 10);
  const compounderTarget = readPct(env, "BILL_CAPITAL_COMPOUNDER_PCT", 10);

  const prediction = args.trackBoard.find((track) => track.id === "prediction");
  const futures = args.trackBoard.find((track) => track.id === "futures-core");
  const longOnly = args.trackBoard.find((track) => track.id === "long-only-compounder");
  const adjacent = args.trackBoard.filter((track) => track.id === "options-us" || track.id === "crypto-liquid");

  const coreStable = [prediction, futures]
    .filter((track): track is TrackReadinessSummary => Boolean(track))
    .every((track) => track.mode === "active" && (track.posture === "shadow" || track.posture === "actionable"));
  const adjacentReady = adjacent.some((track) => track.posture === "collecting" || track.posture === "shadow" || track.posture === "actionable");
  const compounderReady = Boolean(
    longOnly
    && longOnly.mode !== "disabled"
    && longOnly.posture !== "setup-debt"
    && longOnly.posture !== "idle"
  );

  const mode: FundPlan["mode"] = args.runtimeHealth.status === "critical" || !coreStable
    ? "stabilize-core"
    : !adjacentReady
      ? "branch-adjacent"
      : !compounderReady
        ? "seed-compounder"
        : "compound";

  const compounderDeployed = compounderReady ? compounderTarget : 0;
  const incubationDeployed = adjacentReady ? incubationTarget : incubationTarget * 0.4;
  const activeRiskDeployed = coreStable || args.policy.executionTracks.length > 0 ? activeRiskTarget : activeRiskTarget * 0.5;
  const reserveDeployed = roundPct(100 - activeRiskDeployed - incubationDeployed - compounderDeployed);

  const tracks: FundTrackDirective[] = args.trackBoard.map((track) => ({
    id: track.id,
    role: roleForTrack(track.id),
    mode: track.mode,
    posture: track.posture,
    suggestedCapitalPct: suggestedCapitalPct(track),
    branchCondition: branchCondition(track),
    summary: trackSummary(track)
  }));

  const nextCapitalMove = mode === "stabilize-core"
    ? `Keep capital concentrated in ${args.policy.executionTracks.join(" + ") || "the active cashflow wedges"} and reserve until the core tracks are stable.`
    : mode === "branch-adjacent"
      ? "Use spare budget to finish adjacent-lane setup so the next wedge can be tested without diluting core execution."
      : mode === "seed-compounder"
        ? "Keep funding the cashflow wedges, then seed the long-only compounder data and ranking stack from realized gains."
        : "Start a small long-only sleeve while preserving the reserve and leaving active risk concentrated in the core cashflow tracks.";

  const growthLadder: FundGrowthStep[] = [
    {
      stage: "stabilize-core",
      title: "Stabilize the cashflow wedges",
      status: mode === "stabilize-core" ? "now" : "later",
      condition: "Prediction and futures must stay fresh, guarded, and economically honest.",
      action: prediction?.nextAction ?? futures?.nextAction ?? "Keep the nearest cashflow wedge honest."
    },
    {
      stage: "branch-adjacent",
      title: "Branch into adjacent trading research",
      status: mode === "branch-adjacent" ? "now" : mode === "stabilize-core" ? "next" : "later",
      condition: "Only branch once the core loops are stable enough that adding a new track will not starve them.",
      action: adjacent[0]?.nextAction ?? "Finish options or crypto setup debt before widening."
    },
    {
      stage: "seed-compounder",
      title: "Seed the long-only compounder",
      status: mode === "seed-compounder" ? "now" : mode === "compound" ? "later" : "next",
      condition: "Use realized cashflow, not optimism, to fund the compounding sleeve.",
      action: longOnly?.nextAction ?? "Wire the long-only data, filings, and ranking surfaces."
    },
    {
      stage: "compound",
      title: "Run the machine as a compounding fund",
      status: mode === "compound" ? "now" : "later",
      condition: "Reserve stays intact, active wedges stay bounded, and the compounder lane scales only after evidence stays durable.",
      action: args.primaryAction?.summary ?? "Let Hermes keep the next move bounded."
    }
  ];

  return {
    mode,
    nextCapitalMove,
    reservePolicy: "Protect reserve first. New sleeves are funded from proven surplus, not from weakening guardrails on the core lanes.",
    buckets: [
      {
        id: "reserve",
        label: "Reserve",
        targetPct: reserveTarget,
        deployedPct: reserveDeployed,
        status: "ready",
        mandate: "Keep dry powder and prevent the machine from cannibalizing itself during buildout."
      },
      {
        id: "active-risk",
        label: "Active Risk",
        targetPct: activeRiskTarget,
        deployedPct: roundPct(activeRiskDeployed),
        status: coreStable ? "ready" : "building",
        mandate: "Concentrate active risk in the current cashflow wedges: prediction and futures."
      },
      {
        id: "incubation",
        label: "Incubation",
        targetPct: incubationTarget,
        deployedPct: roundPct(incubationDeployed),
        status: adjacentReady ? "ready" : "building",
        mandate: "Advance options and crypto as controlled next wedges without starving the core."
      },
      {
        id: "compounder",
        label: "Compounder",
        targetPct: compounderTarget,
        deployedPct: roundPct(compounderDeployed),
        status: compounderReady ? "ready" : "held",
        mandate: "Build a Warren Buffett-style long-only sleeve only after cashflow wedges are stable."
      }
    ],
    tracks,
    growthLadder,
    notes: [
      "Macro/rates remains a context lane, not a stand-alone allocation sleeve.",
      "Long-only should compound capital created elsewhere; it should not become an excuse to blur the active trading loops.",
      "Hermes remains the allocator of attention; this plan only changes the read model, not the underlying control boundary."
    ]
  };
}
