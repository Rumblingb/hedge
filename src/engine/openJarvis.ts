import os from "node:os";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { dirname, join, resolve } from "node:path";
import { buildOpportunitySnapshot, type OpportunitySnapshot, type OpportunitySnapshotOptions } from "../opportunity/orchestrator.js";
import { resolveRuntimeRepoRoot } from "../utils/runtimePaths.js";
import {
  readHermesSupervisorArtifact,
  buildHermesSupervisorPlan,
  DEFAULT_HERMES_SUPERVISOR_STATE_PATH,
  type HermesSupervisorPlan,
  writeHermesSupervisorArtifact
} from "./hermesSupervisor.js";
import {
  buildRuntimeManifest,
  DEFAULT_RUNTIME_MANIFEST_STATE_PATH,
  type RuntimeWorkerTeam,
  writeRuntimeManifestArtifact
} from "./runtimeManifest.js";
import type { AutonomyStatus } from "./autonomyStatus.js";

export interface OpenJarvisStatusOptions {
  agencyStatusPath?: string;
  agencyOutboxPath?: string;
  approvalsPath?: string;
  founderAlertsPath?: string;
  brainPath?: string;
  billHealthPath?: string;
  autonomyStatusPath?: string;
  predictionCycleHistoryPath?: string;
  hermesSupervisorStatePath?: string;
  openJarvisStatusStatePath?: string;
  runtimeManifestStatePath?: string;
  persistHermesSupervisor?: boolean;
  bill?: OpportunitySnapshotOptions;
  env?: NodeJS.ProcessEnv;
  now?: () => string;
}

export type OpenJarvisOwner = "bill" | "agency-os" | "hermes" | "researcher" | "openclaw" | "open-jarvis";

export interface OpenJarvisAction {
  owner: OpenJarvisOwner;
  stage: "execute" | "shadow" | "collect" | "configure" | "research";
  priority: number;
  summary: string;
  reason: string;
  source: "bill" | "agency-os" | "hermes";
  lane?: string;
}

export interface OpenJarvisStatus {
  timestamp: string;
  source: {
    system: "rumbling-hedge";
    module: "open-jarvis";
    surface: "founder-control-plane";
  };
  statePaths: {
    hermesSupervisor: string;
    openJarvisStatus?: string;
    runtimeManifest?: string;
  };
  architecture: {
    founderIngress: "open-jarvis";
    controlPlane: "hermes";
    marketRuntime: "bill";
    companyRuntime: "agency-os";
    researchRuntime: "researcher";
    fixerRuntime: "openclaw";
    auditRuntime: "hermes";
    supervisorMode: "bounded-parallel";
    founderCostMode: "hosted-budget-first";
    webAccess: "browser-tools-hosted";
    changeControl: "founder-approval-required";
  };
  supervisor: {
    owner: "hermes";
    mode: "bounded-parallel";
    rotationEnabled: boolean;
    maxParallelWorkers: number;
    maxParallelByOwner: Record<"bill" | "agency-os" | "researcher" | "openclaw", number>;
    rotationOrder: Array<"bill" | "agency-os" | "researcher" | "openclaw">;
    notes: string[];
  };
  teamTopology: RuntimeWorkerTeam[];
  costPolicy: {
    founderIngress: "hosted-budget-first";
    workerPreflight: "free-until-ready";
    workerPaidTier: "budget-tier";
    preferredBudgetFamilies: string[];
    summaryLines: string[];
  };
  brain: {
    posture: "hosted-budget-first";
    localBaseUrl: string;
    activeModel: string;
    embedModel: string;
    lightModel?: string;
    heavyModel?: string;
    cloudProvider?: string;
    cloudBaseUrl?: string;
    cloudReviewModel?: string;
    cloudDeepReviewModel?: string;
    notes: string[];
  };
  founderAttention: {
    path: string;
    activeAlerts?: string;
    deliveryMode?: string;
    summaryLines: string[];
  };
  brainMemory: {
    path: string;
    trackedLanes?: string;
    founderIngress?: string;
    summaryLines: string[];
  };
  runtimeHealth: {
    status: "healthy" | "degraded" | "critical";
    observedAt?: string;
    healthPath: string;
    cycleHistoryPath: string;
    warnings: string[];
    recentFailures: string[];
    staleArtifacts: string[];
    summaryLines: string[];
  };
  autonomy?: AutonomyStatus;
  bill: OpportunitySnapshot;
  agencyOs: {
    lastSync?: string;
    activeCompanyLanes?: string;
    activeLaneUpdates?: string;
    mergedMission?: string;
    founderInboxTail?: string;
    operatingMode?: string;
    summaryLines: string[];
  };
  approvalQueue: {
    path: string;
    count: number;
    urgentCount: number;
    summaryLines: string[];
    requests: Array<{
      id: string;
      type: string;
      owner: string;
      status: string;
      requestedAction: string;
    }>;
  };
  orchestration: HermesSupervisorPlan;
  actionQueue: OpenJarvisAction[];
  founder: {
    posture: "execute" | "shadow" | "collect" | "configure" | "research";
    nextAction: string;
    routingOwner: OpenJarvisOwner;
    approvalNeeded: boolean;
    approvalReason?: string;
    operatorReply: {
      intent: string;
      owner: OpenJarvisOwner;
      nextAction: string;
      blockers: string[];
      approvalsNeeded: string[];
      eta: string;
    };
  };
}

export const DEFAULT_OPENJARVIS_STATUS_STATE_PATH = ".rumbling-hedge/state/openjarvis-status.json";

function normalizeOllamaModel(value: string | undefined): string | undefined {
  if (!value) return undefined;
  return value.startsWith("ollama/") ? value.slice("ollama/".length) : value;
}

function buildBrainStatus(env: NodeJS.ProcessEnv): OpenJarvisStatus["brain"] {
  const manifest = buildRuntimeManifest(env);
  const activeModel = env.BILL_CLOUD_REVIEW_MODEL
    ?? manifest.ingress.routingModel
    ?? normalizeOllamaModel(env.BILL_LOCAL_HEAVY_MODEL)
    ?? manifest.ingress.fallbackModel;
  const lightModel = normalizeOllamaModel(env.BILL_LOCAL_LIGHT_MODEL) ?? manifest.ingress.routingModel;
  const heavyModel = normalizeOllamaModel(env.BILL_LOCAL_HEAVY_MODEL) ?? manifest.ingress.fallbackModel ?? activeModel;
  const cloudProvider = env.BILL_CLOUD_PROVIDER;
  const cloudBaseUrl = env.BILL_CLOUD_BASE_URL;
  const cloudReviewModel = env.BILL_CLOUD_REVIEW_MODEL;
  const cloudDeepReviewModel = env.BILL_CLOUD_DEEP_REVIEW_MODEL;
  const notes = [
    "Keep OpenJarvis as the single founder-facing ingress and let specialists stay behind it.",
    "Use hosted free or budget-tier models on the founder-facing ingress so the orchestration layer sees the same model families as the worker lanes.",
    "Keep the lighter and heavier local Ollama models as background fallback for degraded mode, repair jobs, and low-priority batch work."
  ];

  if (!lightModel || lightModel === activeModel) {
    notes.push("Keep a smaller local fallback installed if you want degraded-mode routing when hosted providers are unavailable.");
  }
  if (cloudProvider && cloudReviewModel) {
    notes.push(`Hermes cloud review lane is pinned to ${cloudProvider}:${cloudReviewModel}.`);
  }

  return {
    posture: "hosted-budget-first",
    localBaseUrl: manifest.ingress.localBaseUrl,
    activeModel,
    embedModel: env.BILL_OLLAMA_EMBED_MODEL ?? "nomic-embed-text:latest",
    lightModel,
    heavyModel,
    cloudProvider,
    cloudBaseUrl,
    cloudReviewModel,
    cloudDeepReviewModel,
    notes
  };
}

function resolveOpenClawHome(env: NodeJS.ProcessEnv = process.env): string {
  return resolve(env.OPENCLAW_HOME ?? join(os.homedir(), ".openclaw"));
}

function resolveAgencyWorkspaceRoot(env: NodeJS.ProcessEnv = process.env): string {
  return resolve(env.OPENJARVIS_AGENCY_WORKSPACE_ROOT ?? join(resolveOpenClawHome(env), "workspace-agency-os"));
}

function resolveOpenJarvisWorkspaceRoot(env: NodeJS.ProcessEnv = process.env): string {
  return resolve(env.OPENJARVIS_WORKSPACE_ROOT ?? join(resolveOpenClawHome(env), "workspace-open-jarvis"));
}

function defaultAgencyStatusPath(env: NodeJS.ProcessEnv = process.env): string {
  return resolve(env.OPENJARVIS_AGENCY_STATUS_PATH ?? join(resolveAgencyWorkspaceRoot(env), "STATUS.md"));
}

function defaultAgencyOutboxPath(env: NodeJS.ProcessEnv = process.env): string {
  return resolve(env.OPENJARVIS_AGENCY_OUTBOX_PATH ?? join(resolveAgencyWorkspaceRoot(env), "OUTBOX.md"));
}

function defaultApprovalsPath(env: NodeJS.ProcessEnv = process.env): string {
  return resolve(env.OPENJARVIS_AGENCY_APPROVALS_PATH ?? join(resolveAgencyWorkspaceRoot(env), "boards/approvals.json"));
}

function defaultFounderAlertsPath(env: NodeJS.ProcessEnv = process.env): string {
  return resolve(env.OPENJARVIS_FOUNDER_ALERTS_PATH ?? join(resolveOpenJarvisWorkspaceRoot(env), "FOUNDER_ALERTS.md"));
}

function defaultBrainPath(env: NodeJS.ProcessEnv = process.env): string {
  return resolve(env.OPENJARVIS_BRAIN_PATH ?? join(resolveOpenJarvisWorkspaceRoot(env), "BRAIN.md"));
}

function resolveBillBaseDir(options: OpenJarvisStatusOptions): string {
  return resolveRuntimeRepoRoot({
    importMetaUrl: import.meta.url,
    cwd: process.cwd(),
    explicitBaseDir: options.bill?.baseDir,
    env: process.env
  });
}

function defaultBillHealthPath(options: OpenJarvisStatusOptions): string {
  return resolve(options.billHealthPath ?? join(resolveBillBaseDir(options), ".rumbling-hedge/logs/bill-health.latest.json"));
}

function defaultAutonomyStatusPath(options: OpenJarvisStatusOptions): string {
  return resolve(options.autonomyStatusPath ?? join(resolveBillBaseDir(options), ".rumbling-hedge/state/autonomy-status.latest.json"));
}

function defaultPredictionCycleHistoryPath(options: OpenJarvisStatusOptions): string {
  return resolve(options.predictionCycleHistoryPath ?? join(resolveBillBaseDir(options), ".rumbling-hedge/logs/prediction-cycle-history.jsonl"));
}

async function readLines(path: string): Promise<string[]> {
  try {
    const raw = await readFile(path, "utf8");
    return raw
      .split(/\r?\n/)
      .map((line) => line.trim())
      .filter(Boolean);
  } catch {
    return [];
  }
}

async function readJsonSafe<T>(path: string): Promise<T | null> {
  try {
    return JSON.parse(await readFile(path, "utf8")) as T;
  } catch {
    return null;
  }
}

async function readJsonLines(path: string): Promise<any[]> {
  try {
    return (await readFile(path, "utf8"))
      .split(/\r?\n/)
      .map((line) => line.trim())
      .filter(Boolean)
      .map((line) => JSON.parse(line));
  } catch {
    return [];
  }
}

interface AgencyApprovalQueueDoc {
  requests?: Array<{
    id?: unknown;
    type?: unknown;
    owner?: unknown;
    status?: unknown;
    requested_action?: unknown;
  }>;
}

function extractBulletValue(lines: string[], prefix: string): string | undefined {
  const needle = `- ${prefix}: `;
  const line = lines.find((value) => value.startsWith(needle));
  return line ? line.slice(needle.length).trim() : undefined;
}

function summarizeAgencyOs(lines: string[]): OpenJarvisStatus["agencyOs"] {
  const summaryLines = lines.filter((line) => line.startsWith("- ")).slice(0, 8);
  return {
    lastSync: extractBulletValue(lines, "last sync"),
    activeCompanyLanes: extractBulletValue(lines, "active company lanes"),
    activeLaneUpdates: extractBulletValue(lines, "active lane updates"),
    mergedMission: extractBulletValue(lines, "merged mission"),
    founderInboxTail: extractBulletValue(lines, "founder inbox tail"),
    operatingMode: extractBulletValue(lines, "operating mode"),
    summaryLines
  };
}

function summarizeFounderAttention(path: string, lines: string[]): OpenJarvisStatus["founderAttention"] {
  return {
    path,
    activeAlerts: extractBulletValue(lines, "active alerts"),
    deliveryMode: extractBulletValue(lines, "delivery mode"),
    summaryLines: lines.filter((line) => line.startsWith("- ")).slice(0, 8)
  };
}

function summarizeBrainMemory(path: string, lines: string[]): OpenJarvisStatus["brainMemory"] {
  return {
    path,
    trackedLanes: extractBulletValue(lines, "tracked lanes"),
    founderIngress: extractBulletValue(lines, "founder ingress"),
    summaryLines: lines.filter((line) => line.startsWith("- ")).slice(0, 10)
  };
}

function summarizeApprovalQueue(path: string, doc: AgencyApprovalQueueDoc | null): OpenJarvisStatus["approvalQueue"] {
  const requests = Array.isArray(doc?.requests)
    ? doc.requests.map((request) => ({
        id: typeof request?.id === "string" ? request.id : "unknown",
        type: typeof request?.type === "string" ? request.type : "unknown",
        owner: typeof request?.owner === "string" ? request.owner : "unknown",
        status: typeof request?.status === "string" ? request.status : "unknown",
        requestedAction: typeof request?.requested_action === "string" ? request.requested_action : "No requested action recorded."
      }))
    : [];
  const urgentCount = requests.filter((request) => /pending|needs|blocked|review/i.test(request.status)).length;
  return {
    path,
    count: requests.length,
    urgentCount,
    summaryLines: requests.slice(0, 4).map((request) => `${request.id} ${request.owner} ${request.status}: ${request.requestedAction}`),
    requests
  };
}

function mapStageToFounderPosture(stage: OpportunitySnapshot["primaryAction"]["stage"]): OpenJarvisStatus["founder"]["posture"] {
  switch (stage) {
    case "execute":
      return "execute";
    case "shadow":
      return "shadow";
    case "collect":
      return "collect";
    case "configure":
      return "configure";
    case "research":
    default:
      return "research";
  }
}

function mapLaneToRoutingOwner(lane: OpportunitySnapshot["primaryAction"]["lane"]): OpenJarvisOwner {
  switch (lane) {
    case "prediction":
    case "futures-core":
    case "options-us":
    case "crypto-liquid":
    case "macro-rates":
      return "bill";
    case "researcher":
      return "researcher";
    default:
      return "open-jarvis";
  }
}

function parsePriorityValue(value: string | undefined): number | null {
  if (!value) return null;
  const parsed = Number.parseInt(value, 10);
  return Number.isFinite(parsed) ? parsed : null;
}

function cleanupDirective(value: string): string {
  return value.replace(/^- /, "").trim();
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

function buildBillActions(snapshot: OpportunitySnapshot): OpenJarvisAction[] {
  return snapshot.actionQueue.map((action) => ({
    owner: mapLaneToRoutingOwner(action.lane),
    stage: mapStageToFounderPosture(action.stage),
    priority: action.priority,
    summary: action.summary,
    reason: action.reason,
    source: "bill",
    lane: action.lane
  }));
}

function buildAgencyAction(args: {
  statusLines: string[];
  outboxLines: string[];
}): OpenJarvisAction | null {
  const combined = Array.from(new Set([...args.statusLines, ...args.outboxLines]));
  const explicitSummary = extractBulletValue(combined, "founder next action") ?? extractBulletValue(combined, "next action");
  const explicitOwner = extractBulletValue(combined, "routing owner");
  if (explicitOwner && explicitOwner !== "agency-os") {
    return null;
  }

  const reasonParts = [
    extractBulletValue(combined, "active lane updates"),
    extractBulletValue(combined, "founder inbox tail"),
    extractBulletValue(combined, "merged mission"),
    extractBulletValue(combined, "operating mode")
  ].filter((value): value is string => Boolean(value));
  if (!explicitSummary && reasonParts.length === 0) {
    return null;
  }

  return {
    owner: "agency-os",
    stage: explicitSummary ? "execute" : "collect",
    priority: parsePriorityValue(extractBulletValue(combined, "priority")) ?? (explicitSummary ? 82 : 58),
    summary: explicitSummary ?? "Review Agency OS company lanes and founder-facing work.",
    reason: reasonParts.join(" ") || "Agency OS has active company runtime state that should stay visible to OpenJarvis.",
    source: "agency-os"
  };
}

function buildHermesAction(args: {
  founderAlertLines: string[];
  brainLines: string[];
}): OpenJarvisAction | null {
  const combined = Array.from(new Set([...args.founderAlertLines, ...args.brainLines]));
  const explicitOwner = extractBulletValue(combined, "routing owner");
  const explicitSummary = extractBulletValue(combined, "founder next action") ?? extractBulletValue(combined, "next action");
  const hermesPattern = /\b(architecture drift|runtime drift|trust boundary|ops fix|incident|audit|security|launchd|broken|failure|correction)\b/i;
  const candidateLines = args.founderAlertLines
    .filter((line) => line.startsWith("- "))
    .filter((line) => /^(?:- )(alert|incident|blocker|action|next action|founder next action|summary):/i.test(line));
  const matchedLine = candidateLines.find((line) => hermesPattern.test(line));
  if (explicitOwner !== "hermes" && !matchedLine) {
    return null;
  }

  return {
    owner: "hermes",
    stage: "configure",
    priority: parsePriorityValue(extractBulletValue(combined, "priority")) ?? (matchedLine ? 96 : 88),
    summary: explicitSummary ?? (matchedLine ? `Investigate ${cleanupDirective(matchedLine)}` : "Investigate runtime drift in the control plane."),
    reason: matchedLine
      ? `Founder-facing control-plane notes flagged a systems issue: ${cleanupDirective(matchedLine)}`
      : "Founder-facing control-plane notes explicitly routed a systems-correction item to Hermes.",
    source: "hermes"
  };
}

function buildRuntimeHealthStatus(args: {
  bill: OpportunitySnapshot;
  billHealthPath: string;
  predictionCycleHistoryPath: string;
  billHealthDoc: any;
  cycleHistory: any[];
  now: string;
}): OpenJarvisStatus["runtimeHealth"] {
  const warnings = Array.isArray(args.bill.runtimeHealth?.warnings)
    ? [...args.bill.runtimeHealth.warnings]
    : [];
  const staleArtifacts = [
    args.bill.prediction.freshness,
    args.bill.copyDemo.freshness,
    args.bill.futures.freshness,
    args.bill.futures.datasetFreshness,
    args.bill.research.freshness
  ]
    .filter((value): value is NonNullable<typeof args.bill.prediction.freshness> => Boolean(value))
    .filter((value) => value.status !== "fresh")
    .map((value) => value.summary);
  const latestHealthyCycleMs = [...args.cycleHistory]
    .map((row) => (row?.posture !== "failed" && typeof row?.ts === "string") ? parseTimestamp(row.ts) : null)
    .filter((value): value is number => value !== null)
    .sort((left, right) => right - left)[0] ?? null;
  const recentFailures = [...args.cycleHistory]
    .filter((row) => {
      if (row?.posture !== "failed" || typeof row?.ts !== "string") {
        return false;
      }
      const rowMs = parseTimestamp(row.ts);
      if (rowMs === null) {
        return false;
      }
      return latestHealthyCycleMs === null || rowMs > latestHealthyCycleMs;
    })
    .reverse()
    .slice(0, 3)
    .map((row) => {
      const ts = typeof row?.ts === "string" ? row.ts : "unknown-ts";
      const error = typeof row?.error === "string" ? row.error.split(/\r?\n/)[0] : "unknown failure";
      return `${ts}: ${error}`;
    });
  const observedAt = typeof args.billHealthDoc?.timestamp === "string"
    ? args.billHealthDoc.timestamp
    : args.bill.runtimeHealth?.observedAt;
  const observedMs = parseTimestamp(observedAt);
  const nowMs = parseTimestamp(args.now) ?? Date.now();
  const healthStale = observedMs !== null && (nowMs - observedMs) / 60_000 > 180;
  if (healthStale && observedAt) {
    staleArtifacts.unshift(`Bill health snapshot is stale at ${formatAgeMinutes((nowMs - observedMs) / 60_000)} old.`);
  }
  const summaryLines = Array.from(new Set([
    ...recentFailures,
    ...warnings.slice(0, 4),
    ...staleArtifacts.slice(0, 4)
  ])).slice(0, 8);
  const status = recentFailures.length > 0 || staleArtifacts.some((line) => line.includes("missing"))
    ? "critical"
    : summaryLines.length > 0
      ? "degraded"
      : "healthy";

  return {
    status,
    observedAt,
    healthPath: args.billHealthPath,
    cycleHistoryPath: args.predictionCycleHistoryPath,
    warnings,
    recentFailures,
    staleArtifacts,
    summaryLines
  };
}

function buildRuntimeHealthAction(runtimeHealth: OpenJarvisStatus["runtimeHealth"]): OpenJarvisAction | null {
  if (runtimeHealth.status === "healthy") {
    return null;
  }

  // Route Hermes for unresolved control-plane/runtime incidents, not for ordinary lane degradation.
  if (runtimeHealth.recentFailures.length === 0 && runtimeHealth.status !== "critical") {
    return null;
  }

  const summary = runtimeHealth.recentFailures[0]
    ? `Stabilize degraded Bill loops: ${runtimeHealth.recentFailures[0]}`
    : runtimeHealth.staleArtifacts[0]
      ? `Restore control-plane freshness: ${runtimeHealth.staleArtifacts[0]}`
      : runtimeHealth.summaryLines[0]
        ? `Investigate runtime drift: ${runtimeHealth.summaryLines[0]}`
        : "Investigate runtime drift in the control plane.";

  const reason = runtimeHealth.summaryLines.join(" ") || "The control plane detected degraded or stale runtime state.";
  return {
    owner: "hermes",
    stage: "configure",
    priority: runtimeHealth.status === "critical" ? 99 : 91,
    summary,
    reason,
    source: "hermes"
  };
}

function mergeActionQueue(actions: OpenJarvisAction[]): OpenJarvisAction[] {
  const deduped = new Map<string, OpenJarvisAction>();
  for (const action of actions) {
    const key = `${action.owner}::${action.stage}::${action.summary}`;
    if (!deduped.has(key)) {
      deduped.set(key, action);
    }
  }
  return [...deduped.values()].sort((left, right) => right.priority - left.priority);
}

function estimateFounderEta(args: {
  owner: OpenJarvisOwner;
  posture: OpenJarvisStatus["founder"]["posture"];
  approvalNeeded: boolean;
}): string {
  if (args.approvalNeeded) {
    return "blocked pending explicit approval";
  }
  if (args.owner === "hermes") {
    return args.posture === "configure" ? "within the hour" : "today";
  }
  if (args.owner === "bill") {
    return args.posture === "research" ? "same day research pass" : "next bounded cycle";
  }
  if (args.owner === "agency-os") {
    return args.posture === "execute" ? "same day packet movement" : "today";
  }
  if (args.owner === "researcher") {
    return "next scheduled ingest cycle";
  }
  return "today";
}

function buildFounderSummary(args: {
  orchestration: HermesSupervisorPlan;
  actionQueue: OpenJarvisAction[];
  attention: string[];
  runtimeHealth: OpenJarvisStatus["runtimeHealth"];
  approvalQueue: OpenJarvisStatus["approvalQueue"];
}): OpenJarvisStatus["founder"] {
  const urgentHermesAction = args.runtimeHealth.status !== "healthy"
    ? args.actionQueue.find((action) => action.owner === "hermes")
    : undefined;
  const selected = urgentHermesAction ?? args.orchestration.needsApprovalWork[0] ?? args.orchestration.activeWork[0] ?? args.actionQueue[0] ?? {
    owner: "open-jarvis",
    stage: "collect",
    priority: 0,
    summary: "No action available",
    reason: "No track produced a current action.",
    source: "bill"
  };
  const posture = selected.stage;
  const approvalNeeded = ("status" in selected && selected.status === "needs-approval")
    || ("requiresApproval" in selected && Boolean(selected.requiresApproval))
    || args.attention.some((item) => item.includes("setup"))
    || args.approvalQueue.count > 0;
  const intent = selected.owner === "agency-os"
    ? "company execution"
    : selected.owner === "bill"
      ? "trading execution"
      : selected.owner === "hermes"
        ? "runtime repair"
        : selected.owner === "researcher"
          ? "research ingest"
          : "founder routing";
  const blockers = Array.from(new Set([
    ...args.runtimeHealth.summaryLines.slice(0, 2),
    ...(approvalNeeded && selected.reason ? [selected.reason] : [])
  ])).filter(Boolean);
  const approvalsNeeded = approvalNeeded
    ? args.approvalQueue.requests.slice(0, 3).map((request) => request.requestedAction)
    : [];
  return {
    posture,
    nextAction: selected.summary,
    routingOwner: selected.owner,
    approvalNeeded,
    approvalReason: approvalNeeded ? selected.reason : undefined,
    operatorReply: {
      intent,
      owner: selected.owner,
      nextAction: selected.summary,
      blockers,
      approvalsNeeded,
      eta: estimateFounderEta({
        owner: selected.owner,
        posture,
        approvalNeeded
      })
    }
  };
}

export async function buildOpenJarvisStatus(options: OpenJarvisStatusOptions = {}): Promise<OpenJarvisStatus> {
  const env = options.env ?? process.env;
  const manifest = buildRuntimeManifest(env);
  const approvalsPath = options.approvalsPath ?? defaultApprovalsPath(env);
  const founderAlertsPath = options.founderAlertsPath ?? defaultFounderAlertsPath(env);
  const brainPath = options.brainPath ?? defaultBrainPath(env);
  const billHealthPath = defaultBillHealthPath(options);
  const autonomyStatusPath = defaultAutonomyStatusPath(options);
  const predictionCycleHistoryPath = defaultPredictionCycleHistoryPath(options);
  const hermesSupervisorStatePath = resolve(options.hermesSupervisorStatePath ?? join(resolveBillBaseDir(options), DEFAULT_HERMES_SUPERVISOR_STATE_PATH));
  const openJarvisStatusStatePath = resolve(options.openJarvisStatusStatePath ?? join(resolveBillBaseDir(options), DEFAULT_OPENJARVIS_STATUS_STATE_PATH));
  const runtimeManifestStatePath = resolve(options.runtimeManifestStatePath ?? join(resolveBillBaseDir(options), DEFAULT_RUNTIME_MANIFEST_STATE_PATH));
  const now = options.now?.() ?? new Date().toISOString();
  const [bill, agencyStatusLines, agencyOutboxLines, founderAlertLines, brainLines, approvalsDoc, billHealthDoc, autonomyStatusDoc, cycleHistory, existingHermesArtifact] = await Promise.all([
    buildOpportunitySnapshot({
      ...options.bill,
      env: options.bill?.env ?? env,
      now: options.bill?.now ?? (() => now)
    }),
    readLines(options.agencyStatusPath ?? defaultAgencyStatusPath(env)),
    readLines(options.agencyOutboxPath ?? defaultAgencyOutboxPath(env)),
    readLines(founderAlertsPath),
    readLines(brainPath),
    readJsonSafe<AgencyApprovalQueueDoc>(approvalsPath),
    readJsonSafe<any>(billHealthPath),
    readJsonSafe<AutonomyStatus>(autonomyStatusPath),
    readJsonLines(predictionCycleHistoryPath),
    readHermesSupervisorArtifact(hermesSupervisorStatePath)
  ]);

  const agencyStatus = summarizeAgencyOs(agencyStatusLines);
  const agencyOutbox = summarizeAgencyOs(agencyOutboxLines);
  const founderAttention = summarizeFounderAttention(founderAlertsPath, founderAlertLines);
  const brainMemory = summarizeBrainMemory(brainPath, brainLines);
  const approvalQueue = summarizeApprovalQueue(approvalsPath, approvalsDoc);
  const runtimeHealth = buildRuntimeHealthStatus({
    bill,
    billHealthPath,
    predictionCycleHistoryPath,
    billHealthDoc,
    cycleHistory,
    now
  });
  const actionQueue = mergeActionQueue([
    ...[buildRuntimeHealthAction(runtimeHealth)].filter((value): value is OpenJarvisAction => Boolean(value)),
    ...buildBillActions(bill),
    ...[buildAgencyAction({ statusLines: agencyStatusLines, outboxLines: agencyOutboxLines })].filter((value): value is OpenJarvisAction => Boolean(value)),
    ...[buildHermesAction({ founderAlertLines, brainLines })].filter((value): value is OpenJarvisAction => Boolean(value))
  ]);
  const orchestration = buildHermesSupervisorPlan({
    manifest,
    actionQueue,
    bill,
    runtimeHealth,
    agencyOs: {
      summaryLines: Array.from(new Set([...agencyStatus.summaryLines, ...agencyOutbox.summaryLines])).slice(0, 10),
      operatingMode: agencyOutbox.operatingMode
    },
    now,
    statePath: hermesSupervisorStatePath,
    controls: existingHermesArtifact?.controls
  });
  if (options.persistHermesSupervisor) {
    await writeHermesSupervisorArtifact({
      plan: orchestration,
      filePath: hermesSupervisorStatePath
    });
    await writeRuntimeManifestArtifact({
      manifest,
      filePath: runtimeManifestStatePath
    });
  }

  const status: OpenJarvisStatus = {
    timestamp: now,
    source: {
      system: "rumbling-hedge",
      module: "open-jarvis",
      surface: "founder-control-plane"
    },
    statePaths: {
      hermesSupervisor: hermesSupervisorStatePath,
      openJarvisStatus: options.persistHermesSupervisor ? openJarvisStatusStatePath : undefined,
      runtimeManifest: options.persistHermesSupervisor ? runtimeManifestStatePath : undefined
    },
    architecture: {
      founderIngress: manifest.architecture.founderIngress,
      controlPlane: manifest.architecture.orchestrator,
      marketRuntime: manifest.architecture.marketRuntime,
      companyRuntime: manifest.architecture.companyRuntime,
      researchRuntime: manifest.architecture.researchRuntime,
      fixerRuntime: manifest.architecture.fixerRuntime,
      auditRuntime: manifest.architecture.orchestrator,
      supervisorMode: manifest.supervisor.mode,
      founderCostMode: manifest.ingress.costMode,
      webAccess: manifest.ingress.webAccess,
      changeControl: manifest.architecture.changeControl
    },
    supervisor: {
      owner: manifest.supervisor.owner,
      mode: manifest.supervisor.mode,
      rotationEnabled: manifest.supervisor.rotationEnabled,
      maxParallelWorkers: manifest.supervisor.maxParallelWorkers,
      maxParallelByOwner: manifest.supervisor.maxParallelByOwner,
      rotationOrder: manifest.supervisor.rotationOrder,
      notes: manifest.supervisor.notes
    },
    teamTopology: manifest.workerTopology,
    costPolicy: {
      founderIngress: manifest.ingress.costMode,
      workerPreflight: manifest.workerCompute.preflightBudgetMode,
      workerPaidTier: manifest.workerCompute.paidBudgetMode,
      preferredBudgetFamilies: manifest.workerCompute.preferredBudgetFamilies,
      summaryLines: [
        `OpenJarvis stays ${manifest.ingress.costMode}.`,
        `Worker agents stay ${manifest.workerCompute.preflightBudgetMode} until the machine is trusted.`,
        `Paid worker upgrades should stay in the ${manifest.workerCompute.preferredBudgetFamilies.join(" / ")} price band by default.`
      ]
    },
    brain: buildBrainStatus(env),
    founderAttention,
    brainMemory,
    runtimeHealth,
    autonomy: autonomyStatusDoc ?? undefined,
    bill,
    agencyOs: {
      lastSync: agencyStatus.lastSync ?? agencyOutbox.lastSync,
      activeCompanyLanes: agencyStatus.activeCompanyLanes,
      activeLaneUpdates: agencyStatus.activeLaneUpdates ?? agencyOutbox.activeLaneUpdates,
      mergedMission: agencyStatus.mergedMission ?? agencyOutbox.mergedMission,
      founderInboxTail: agencyOutbox.founderInboxTail,
      operatingMode: agencyOutbox.operatingMode,
      summaryLines: Array.from(new Set([...agencyStatus.summaryLines, ...agencyOutbox.summaryLines])).slice(0, 10)
    },
    approvalQueue,
    orchestration,
    actionQueue,
    founder: buildFounderSummary({
      orchestration,
      actionQueue,
      attention: bill.attention,
      runtimeHealth,
      approvalQueue
    })
  };

  if (options.persistHermesSupervisor) {
    await mkdir(dirname(openJarvisStatusStatePath), { recursive: true });
    await writeFile(openJarvisStatusStatePath, `${JSON.stringify(status, null, 2)}\n`, "utf8");
  }

  return status;
}
