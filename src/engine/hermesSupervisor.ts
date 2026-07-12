import { mkdir, readFile, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import type { OpportunitySnapshot } from "../opportunity/orchestrator.js";
import type { RuntimeManifest, WorkerLaneOwner } from "./runtimeManifest.js";

export type HermesWorkStatus = "active" | "queued" | "backlog" | "paused" | "needs-approval" | "done";
export type HermesWorkSource = "runtime" | "bill" | "agency-os" | "researcher" | "hermes";
export type HermesSupervisorDecisionAction = "approve" | "pause" | "resume" | "complete";

export interface HermesSupervisorTask {
  id: string;
  owner: WorkerLaneOwner | "hermes";
  stage: "execute" | "shadow" | "collect" | "configure" | "research";
  priority: number;
  summary: string;
  reason: string;
  source: HermesWorkSource;
  requiresApproval: boolean;
  lane?: string;
  status: HermesWorkStatus;
}

export interface HermesWorkerHeartbeat {
  owner: HermesSupervisorTask["owner"];
  taskId: string;
  lane?: string;
  summary: string;
  status: "running";
  updatedAt: string;
}

export interface HermesSupervisorDecision {
  action: HermesSupervisorDecisionAction;
  taskId: string;
  at: string;
  actor: "founder" | "hermes";
  note?: string;
}

export interface HermesSupervisorControls {
  pausedTaskIds: string[];
  approvedTaskIds: string[];
  completedTaskIds: string[];
  decisionLog: HermesSupervisorDecision[];
}

export interface HermesSupervisorPlan {
  owner: "hermes";
  mode: "bounded-parallel";
  generatedAt: string;
  statePath?: string;
  activeWork: HermesSupervisorTask[];
  needsApprovalWork: HermesSupervisorTask[];
  pausedWork: HermesSupervisorTask[];
  queuedWork: HermesSupervisorTask[];
  backlog: HermesSupervisorTask[];
  doneWork: HermesSupervisorTask[];
  todoList: HermesSupervisorTask[];
  heartbeats: HermesWorkerHeartbeat[];
  summaryLines: string[];
  controls: HermesSupervisorControls;
}

export interface HermesSupervisorArtifact {
  generatedAt: string;
  statePath: string;
  owner: "hermes";
  mode: "bounded-parallel";
  activeWork: HermesSupervisorTask[];
  needsApprovalWork: HermesSupervisorTask[];
  pausedWork: HermesSupervisorTask[];
  queuedWork: HermesSupervisorTask[];
  backlog: HermesSupervisorTask[];
  doneWork: HermesSupervisorTask[];
  todoList: HermesSupervisorTask[];
  heartbeats: HermesWorkerHeartbeat[];
  summaryLines: string[];
  controls: HermesSupervisorControls;
}

export const DEFAULT_HERMES_SUPERVISOR_STATE_PATH = ".rumbling-hedge/state/hermes-supervisor.json";
const DEFAULT_DECISION_LOG_LIMIT = 100;

interface IncomingAction {
  owner: "bill" | "agency-os" | "researcher" | "hermes" | "openclaw" | "open-jarvis";
  stage: "execute" | "shadow" | "collect" | "configure" | "research";
  priority: number;
  summary: string;
  reason: string;
  source: "bill" | "agency-os" | "hermes";
  lane?: string;
}

interface RuntimeHealthLike {
  status: "healthy" | "degraded" | "critical";
  summaryLines: string[];
  recentFailures: string[];
  staleArtifacts: string[];
}

interface AgencyOsLike {
  summaryLines: string[];
  operatingMode?: string;
}

function slug(value: string): string {
  return value
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 80);
}

function makeTask(input: Omit<HermesSupervisorTask, "id" | "status">): HermesSupervisorTask {
  return {
    ...input,
    id: `${input.owner}:${slug(input.summary)}`,
    status: "queued"
  };
}

function buildPredictionFineTuningTask(snapshot: OpportunitySnapshot): HermesSupervisorTask {
  const blockerSet = new Set(snapshot.prediction.blockers ?? []);
  const topCandidate = snapshot.prediction.topCandidate as { reasons?: string[] } | null;
  const reasons = Array.isArray(topCandidate?.reasons) ? topCandidate.reasons : [];

  if (
    blockerSet.has("top-candidate-zero-stake")
    || blockerSet.has("lead-candidate-not-paper-trade")
    || blockerSet.has("committee-watch")
    || reasons.some((reason) => /negative-net-edge|cost-drag-exceeds-edge|subscale-edge/i.test(reason))
  ) {
    return makeTask({
      owner: "bill",
      stage: "configure",
      priority: 95,
      summary: "Improve prediction economics and paper thresholds without forcing execution",
      reason: snapshot.prediction.recommendation
        ?? "Prediction has a structurally real pair, but economics still fail after costs, so the next task is to improve edge quality rather than relax the committee.",
      source: "hermes",
      requiresApproval: true,
      lane: "prediction"
    });
  }

  if (reasons.some((reason) => /liquidity|size|thin/i.test(reason))) {
    return makeTask({
      owner: "bill",
      stage: "configure",
      priority: 95,
      summary: "Align prediction scan policy and committee liquidity gating for bounded micro-paper reviews",
      reason: "Prediction keeps surfacing a live pair, but liquidity gating is still preventing bounded paper validation.",
      source: "hermes",
      requiresApproval: true,
      lane: "prediction"
    });
  }

  return makeTask({
    owner: "bill",
    stage: "configure",
    priority: 95,
    summary: "Align prediction scan policy and committee gating with the live blocker",
    reason: snapshot.prediction.recommendation
      ?? "Prediction is still fail-closed, so the next task should follow the actual live blocker rather than a stale generic fix.",
    source: "hermes",
    requiresApproval: true,
    lane: "prediction"
  });
}

function buildResearcherFineTuningTask(snapshot: OpportunitySnapshot): HermesSupervisorTask | null {
  const research = snapshot.research;
  const healthyYield = (research.chunksKept ?? 0) > 0 && research.status !== "degraded";
  if (healthyYield) {
    return null;
  }

  const noSuccessfulTargets = (research.targetsSucceeded ?? 0) === 0;
  const noNovelChunks = (research.targetsSucceeded ?? 0) > 0 && (research.chunksCollected ?? 0) === 0;
  const noRetainedChunks = (research.chunksCollected ?? 0) > 0 && (research.chunksKept ?? 0) === 0;
  const summary = research.nextAction?.trim().length
    ? research.nextAction
    : noSuccessfulTargets
      ? "Fix failing researcher targets before widening scope"
      : noNovelChunks
        ? "Refresh the target list; the latest run only hit already-covered material."
        : noRetainedChunks
          ? "Refresh the target list or loosen filtering; the latest run kept no chunks."
          : "Keep ingesting and curate the next highest-priority researcher targets.";
  const reason = noSuccessfulTargets
    ? "Researcher targets are failing outright, so Bill is missing fresh external context until the lane is repaired."
    : noNovelChunks
      ? "Researcher is running but the selected sources are exhausted, so the lane needs fresher targets rather than another dry cycle."
      : noRetainedChunks
        ? "Researcher found novel material but retained no durable chunks, so target relevance and filter fit still need work."
        : "Researcher is healthy enough to keep feeding Bill's active lanes with fresh context.";

  return makeTask({
    owner: "researcher",
    stage: "research",
    priority: 82,
    summary,
    reason,
    source: "hermes",
    requiresApproval: false,
    lane: "researcher"
  });
}

function withStatus(tasks: HermesSupervisorTask[], status: HermesWorkStatus): HermesSupervisorTask[] {
  return tasks.map((task) => ({ ...task, status }));
}

function buildActionTasks(actions: IncomingAction[]): HermesSupervisorTask[] {
  return actions
    .filter((action): action is IncomingAction & { owner: HermesSupervisorTask["owner"] } => action.owner !== "open-jarvis")
    .map((action) => makeTask({
      owner: action.owner,
      stage: action.stage,
      priority: action.priority,
      summary: action.summary,
      reason: action.reason,
      source: action.source,
      requiresApproval: false,
      lane: action.lane
    }));
}

function buildBillFineTuningTasks(snapshot: OpportunitySnapshot): HermesSupervisorTask[] {
  const tasks: HermesSupervisorTask[] = [
    buildPredictionFineTuningTask(snapshot),
    makeTask({
      owner: "bill",
      stage: "configure",
      priority: 92,
      summary: "Harden futures free-data refresh with symbol-specific fallbacks and degraded-symbol routing",
      reason: "Futures demo readiness is still too brittle because single-symbol failures like CL or GC degrade the whole lane.",
      source: "hermes",
      requiresApproval: false,
      lane: "futures-core"
    }),
    makeTask({
      owner: "bill",
      stage: "research",
      priority: 89,
      summary: "Tighten futures evidence thresholds and ranking stability before widening strategy count",
      reason: "Futures remains blocked by thin OOS evidence, severe tail loss, and unstable profile ranking across windows.",
      source: "hermes",
      requiresApproval: true,
      lane: "futures-core"
    }),
    makeTask({
      owner: "openclaw",
      stage: "configure",
      priority: 84,
      summary: "Replace stale cloud-review model ids in Hedge env and helper scripts",
      reason: "The control plane should not keep pointing operators or review jobs at dead provider slugs while the system is still being stabilized.",
      source: "hermes",
      requiresApproval: false
    }),
    makeTask({
      owner: "bill",
      stage: "configure",
      priority: 72,
      summary: "Turn options-us from setup debt into a real research lane with a validated collection path",
      reason: "Options is still mostly setup debt, which means Bill's in-domain board is broader than the actually usable research machinery.",
      source: "hermes",
      requiresApproval: false,
      lane: "options-us"
    })
  ];
  const researcherTask = buildResearcherFineTuningTask(snapshot);
  if (researcherTask) {
    tasks.push(researcherTask);
  }

  if ((snapshot.prediction.counts.paperTrade ?? 0) > 0) {
    return tasks.filter((task) => !task.summary.includes("prediction scan policy"));
  }

  return tasks;
}

function buildHermesControlTasks(args: {
  runtimeHealth: RuntimeHealthLike;
  agencyOs: AgencyOsLike;
}): HermesSupervisorTask[] {
  const tasks: HermesSupervisorTask[] = [];
  if (args.runtimeHealth.status !== "healthy") {
    tasks.push(makeTask({
      owner: "hermes",
      stage: "configure",
      priority: args.runtimeHealth.status === "critical" ? 99 : 90,
      summary: "Stabilize degraded loops before widening autonomy",
      reason: args.runtimeHealth.summaryLines[0] ?? "The runtime still has degraded loops or stale artifacts.",
      source: "runtime",
      requiresApproval: false
    }));
  }

  if (args.agencyOs.summaryLines.length > 0) {
    tasks.push(makeTask({
      owner: "agency-os",
      stage: "execute",
      priority: 87,
      summary: "Force one concrete AgentPay packet or founder-ready artifact through Agency OS this cycle",
      reason: args.agencyOs.operatingMode
        ? `Agency OS is live in ${args.agencyOs.operatingMode}, but it still needs concrete founder-ready output each cycle.`
        : "Agency OS should produce one concrete founder-ready output each cycle instead of drifting in internal coordination.",
      source: "agency-os",
      requiresApproval: false
    }));
  }

  tasks.push(makeTask({
    owner: "hermes",
    stage: "configure",
    priority: 88,
    summary: "Persist Hermes task state and worker heartbeats as structured artifacts instead of markdown-only memory",
    reason: "Hermes should be able to supervise bounded parallel workers from structured state rather than rely on drift-prone prose surfaces.",
    source: "hermes",
    requiresApproval: false
  }));

  tasks.push(makeTask({
    owner: "hermes",
    stage: "configure",
    priority: 86,
    summary: "Add approval and pause-resume controls so Hermes can run safe loops without widening authority",
    reason: "A usable autonomous system needs a clear trust boundary: Hermes may schedule and retry safe work, but approvals must gate execution widening and risky changes.",
    source: "hermes",
    requiresApproval: true
  }));

  return tasks;
}

function dedupe(tasks: HermesSupervisorTask[]): HermesSupervisorTask[] {
  const seen = new Map<string, HermesSupervisorTask>();
  for (const task of tasks) {
    const key = `${task.owner}::${task.summary}`;
    if (!seen.has(key) || (seen.get(key)?.priority ?? 0) < task.priority) {
      seen.set(key, task);
    }
  }
  return [...seen.values()].sort((left, right) => right.priority - left.priority);
}

export function normalizeHermesSupervisorControls(
  controls?: Partial<HermesSupervisorControls> | null
): HermesSupervisorControls {
  return {
    pausedTaskIds: Array.from(new Set((controls?.pausedTaskIds ?? []).filter(Boolean))),
    approvedTaskIds: Array.from(new Set((controls?.approvedTaskIds ?? []).filter(Boolean))),
    completedTaskIds: Array.from(new Set((controls?.completedTaskIds ?? []).filter(Boolean))),
    decisionLog: [...(controls?.decisionLog ?? [])].slice(-DEFAULT_DECISION_LOG_LIMIT)
  };
}

function assignBoundedParallelWork(manifest: RuntimeManifest, tasks: HermesSupervisorTask[]): {
  activeWork: HermesSupervisorTask[];
  remaining: HermesSupervisorTask[];
} {
  const caps = {
    ...manifest.supervisor.maxParallelByOwner,
    hermes: 1
  } as Record<HermesSupervisorTask["owner"], number>;
  const counts = new Map<HermesSupervisorTask["owner"], number>();
  const activeWork: HermesSupervisorTask[] = [];
  const remaining = [...tasks];

  function canAssign(task: HermesSupervisorTask): boolean {
    const current = counts.get(task.owner) ?? 0;
    return current < (caps[task.owner] ?? 0);
  }

  function takeFirst(owner: HermesSupervisorTask["owner"]): void {
    if (activeWork.length >= manifest.supervisor.maxParallelWorkers) return;
    const index = remaining.findIndex((task) => task.owner === owner && canAssign(task));
    if (index === -1) return;
    const [task] = remaining.splice(index, 1);
    counts.set(task.owner, (counts.get(task.owner) ?? 0) + 1);
    activeWork.push({ ...task, status: "active" });
  }

  const urgentHermesTask = remaining.find((task) => task.owner === "hermes" && task.priority >= 95);
  if (urgentHermesTask) {
    takeFirst("hermes");
  }

  takeFirst("bill");
  takeFirst("agency-os");

  if (manifest.supervisor.rotationEnabled) {
    for (const owner of manifest.supervisor.rotationOrder) {
      while (activeWork.length < manifest.supervisor.maxParallelWorkers) {
        const before = activeWork.length;
        takeFirst(owner);
        if (activeWork.length === before) break;
      }
      if (activeWork.length >= manifest.supervisor.maxParallelWorkers) break;
    }
  }

  for (const task of remaining) {
    if (activeWork.length >= manifest.supervisor.maxParallelWorkers) break;
    if (!canAssign(task)) continue;
    counts.set(task.owner, (counts.get(task.owner) ?? 0) + 1);
    activeWork.push({ ...task, status: "active" });
  }

  const activeIds = new Set(activeWork.map((task) => task.id));
  return {
    activeWork,
    remaining: tasks
      .filter((task) => !activeIds.has(task.id))
      .sort((left, right) => right.priority - left.priority)
  };
}

function applyControls(args: {
  manifest: RuntimeManifest;
  now: string;
  tasks: HermesSupervisorTask[];
  controls: HermesSupervisorControls;
}): Pick<HermesSupervisorPlan, "activeWork" | "needsApprovalWork" | "pausedWork" | "queuedWork" | "backlog" | "doneWork" | "todoList" | "heartbeats" | "controls"> {
  const controls = normalizeHermesSupervisorControls(args.controls);
  const completedIds = new Set(controls.completedTaskIds);
  const pausedIds = new Set(controls.pausedTaskIds);
  const approvedIds = new Set(controls.approvedTaskIds);

  const doneWork = withStatus(args.tasks.filter((task) => completedIds.has(task.id)), "done");
  const outstanding = args.tasks.filter((task) => !completedIds.has(task.id));
  const pausedWork = withStatus(outstanding.filter((task) => pausedIds.has(task.id)), "paused");
  const runnableBase = outstanding.filter((task) => !pausedIds.has(task.id));
  const needsApprovalWork = withStatus(
    runnableBase.filter((task) => task.requiresApproval && !approvedIds.has(task.id)),
    "needs-approval"
  );
  const schedulable = runnableBase.filter((task) => !task.requiresApproval || approvedIds.has(task.id));
  const { activeWork, remaining } = assignBoundedParallelWork(args.manifest, schedulable);
  const queuedWork = withStatus(remaining.slice(0, 8), "queued");
  const queuedIds = new Set(queuedWork.map((task) => task.id));
  const backlog = withStatus(remaining.filter((task) => !queuedIds.has(task.id)), "backlog");
  const heartbeats: HermesWorkerHeartbeat[] = activeWork.map((task) => ({
    owner: task.owner,
    taskId: task.id,
    lane: task.lane,
    summary: task.summary,
    status: "running",
    updatedAt: args.now
  }));
  const todoList = [
    ...activeWork,
    ...needsApprovalWork,
    ...pausedWork,
    ...queuedWork,
    ...backlog
  ].sort((left, right) => right.priority - left.priority);

  return {
    activeWork,
    needsApprovalWork,
    pausedWork,
    queuedWork,
    backlog,
    doneWork,
    todoList,
    heartbeats,
    controls
  };
}

export function buildHermesSupervisorPlan(args: {
  manifest: RuntimeManifest;
  actionQueue: IncomingAction[];
  bill: OpportunitySnapshot;
  runtimeHealth: RuntimeHealthLike;
  agencyOs: AgencyOsLike;
  now: string;
  statePath?: string;
  controls?: Partial<HermesSupervisorControls> | null;
}): HermesSupervisorPlan {
  const actionTasks = buildActionTasks(args.actionQueue);
  const fineTuningTasks = buildBillFineTuningTasks(args.bill);
  const controlTasks = buildHermesControlTasks({
    runtimeHealth: args.runtimeHealth,
    agencyOs: args.agencyOs
  });
  const tasks = dedupe([
    ...actionTasks,
    ...fineTuningTasks,
    ...controlTasks
  ]);
  const controlled = applyControls({
    manifest: args.manifest,
    now: args.now,
    tasks,
    controls: normalizeHermesSupervisorControls(args.controls)
  });

  return {
    owner: "hermes",
    mode: args.manifest.supervisor.mode,
    generatedAt: args.now,
    statePath: args.statePath,
    ...controlled,
    summaryLines: [
      `Hermes is supervising ${controlled.activeWork.length}/${args.manifest.supervisor.maxParallelWorkers} active worker slots.`,
      `${controlled.needsApprovalWork.length} task(s) are waiting for founder approval and ${controlled.pausedWork.length} task(s) are paused.`,
      "Bill and Agency OS are pinned into the active rotation before Researcher and OpenClaw consume spare capacity.",
      `Top Bill fine-tuning item: ${fineTuningTasks[0]?.summary ?? "none"}.`
    ]
  };
}

export async function writeHermesSupervisorArtifact(args: {
  plan: HermesSupervisorPlan;
  filePath?: string;
}): Promise<string> {
  const target = resolve(args.filePath ?? args.plan.statePath ?? DEFAULT_HERMES_SUPERVISOR_STATE_PATH);
  await mkdir(dirname(target), { recursive: true });
  const artifact: HermesSupervisorArtifact = {
    generatedAt: args.plan.generatedAt,
    statePath: target,
    owner: args.plan.owner,
    mode: args.plan.mode,
    activeWork: args.plan.activeWork,
    needsApprovalWork: args.plan.needsApprovalWork,
    pausedWork: args.plan.pausedWork,
    queuedWork: args.plan.queuedWork,
    backlog: args.plan.backlog,
    doneWork: args.plan.doneWork,
    todoList: args.plan.todoList,
    heartbeats: args.plan.heartbeats,
    summaryLines: args.plan.summaryLines,
    controls: normalizeHermesSupervisorControls(args.plan.controls)
  };
  await writeFile(target, `${JSON.stringify(artifact, null, 2)}\n`, "utf8");
  return target;
}

export async function readHermesSupervisorArtifact(filePath = DEFAULT_HERMES_SUPERVISOR_STATE_PATH): Promise<HermesSupervisorArtifact | null> {
  try {
    const artifact = JSON.parse(await readFile(resolve(filePath), "utf8")) as HermesSupervisorArtifact;
    return {
      ...artifact,
      activeWork: artifact.activeWork ?? [],
      needsApprovalWork: artifact.needsApprovalWork ?? [],
      pausedWork: artifact.pausedWork ?? [],
      queuedWork: artifact.queuedWork ?? [],
      backlog: artifact.backlog ?? [],
      doneWork: artifact.doneWork ?? [],
      todoList: artifact.todoList ?? [],
      heartbeats: artifact.heartbeats ?? [],
      summaryLines: artifact.summaryLines ?? [],
      controls: normalizeHermesSupervisorControls(artifact.controls)
    };
  } catch {
    return null;
  }
}

export function findHermesSupervisorTask(
  artifact: Pick<HermesSupervisorArtifact, "activeWork" | "needsApprovalWork" | "pausedWork" | "queuedWork" | "backlog" | "doneWork">,
  taskId: string
): HermesSupervisorTask | null {
  return [
    ...artifact.activeWork,
    ...artifact.needsApprovalWork,
    ...artifact.pausedWork,
    ...artifact.queuedWork,
    ...artifact.backlog,
    ...artifact.doneWork
  ].find((task) => task.id === taskId) ?? null;
}

export async function applyHermesSupervisorDecision(args: {
  filePath?: string;
  action: HermesSupervisorDecisionAction;
  taskId: string;
  note?: string;
  at?: string;
  actor?: "founder" | "hermes";
}): Promise<HermesSupervisorArtifact> {
  const target = resolve(args.filePath ?? DEFAULT_HERMES_SUPERVISOR_STATE_PATH);
  const artifact = await readHermesSupervisorArtifact(target);
  if (!artifact) {
    throw new Error(`Hermes supervisor state is missing at ${target}. Run hermes-supervisor-status first.`);
  }

  const existingTask = findHermesSupervisorTask(artifact, args.taskId);
  if (!existingTask) {
    throw new Error(`Task ${args.taskId} is not present in the current Hermes supervisor artifact.`);
  }

  const controls = normalizeHermesSupervisorControls(artifact.controls);
  const paused = new Set(controls.pausedTaskIds);
  const approved = new Set(controls.approvedTaskIds);
  const completed = new Set(controls.completedTaskIds);

  switch (args.action) {
    case "approve":
      approved.add(args.taskId);
      break;
    case "pause":
      paused.add(args.taskId);
      break;
    case "resume":
      paused.delete(args.taskId);
      break;
    case "complete":
      completed.add(args.taskId);
      paused.delete(args.taskId);
      break;
  }

  controls.pausedTaskIds = [...paused];
  controls.approvedTaskIds = [...approved];
  controls.completedTaskIds = [...completed];
  controls.decisionLog = [
    ...controls.decisionLog,
    {
      action: args.action,
      taskId: args.taskId,
      at: args.at ?? new Date().toISOString(),
      actor: args.actor ?? "founder",
      note: args.note
    }
  ].slice(-DEFAULT_DECISION_LOG_LIMIT);

  const updated: HermesSupervisorArtifact = {
    ...artifact,
    controls,
    summaryLines: [
      ...artifact.summaryLines.filter((line) => !line.startsWith("Latest founder decision:")),
      `Latest founder decision: ${args.action} ${args.taskId}.`
    ].slice(-8)
  };
  await writeFile(target, `${JSON.stringify(updated, null, 2)}\n`, "utf8");
  return updated;
}
