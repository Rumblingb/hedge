import { mkdtemp, mkdir, readFile, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { afterEach, describe, expect, it } from "vitest";
import { applyHermesSupervisorDecision } from "../src/engine/hermesSupervisor.js";
import { buildOpenJarvisStatus } from "../src/engine/openJarvis.js";

const cleanupPaths: string[] = [];

async function makeTempWorkspace(): Promise<string> {
  const dir = await mkdtemp(join(tmpdir(), "openjarvis-"));
  cleanupPaths.push(dir);
  return dir;
}

afterEach(async () => {
  await Promise.all(cleanupPaths.splice(0).map(async (path) => {
    const { rm } = await import("node:fs/promises");
    await rm(path, { recursive: true, force: true });
  }));
});

describe("buildOpenJarvisStatus", () => {
  it("merges Bill opportunity state with Agency OS founder surfaces", async () => {
    const workspace = await makeTempWorkspace();
    const agencyDir = resolve(workspace, ".openclaw/workspace-agency-os");
    const agencyBoardsDir = resolve(agencyDir, "boards");
    const openJarvisDir = resolve(workspace, ".openclaw/workspace-open-jarvis");
    const stateDir = resolve(workspace, ".rumbling-hedge/state");
    const researcherDir = resolve(workspace, ".rumbling-hedge/research/researcher");
    const researchRoot = resolve(workspace, ".rumbling-hedge/research");
    const researchDataDir = resolve(workspace, "data/research/crypto-bars");

    await Promise.all([
      mkdir(agencyDir, { recursive: true }),
      mkdir(agencyBoardsDir, { recursive: true }),
      mkdir(openJarvisDir, { recursive: true }),
      mkdir(stateDir, { recursive: true }),
      mkdir(researcherDir, { recursive: true }),
      mkdir(researchRoot, { recursive: true }),
      mkdir(researchDataDir, { recursive: true })
    ]);

    await Promise.all([
      writeFile(resolve(agencyDir, "STATUS.md"), [
        "# Agency OS Status",
        "- last sync: 2026-04-15T10:00:00Z",
        "- active company lanes: 4/4",
        "- merged mission: ship + sell",
        ""
      ].join("\n")),
      writeFile(resolve(agencyDir, "OUTBOX.md"), [
        "# Agency OS Outbox",
        "- founder inbox tail: one founder channel only",
        "- operating mode: four-lane merged office",
        ""
      ].join("\n")),
      writeFile(resolve(agencyBoardsDir, "approvals.json"), JSON.stringify({
        requests: [
          {
            id: "APPROVAL-001",
            type: "external-send",
            owner: "outbound-ops",
            status: "pending-founder-review",
            requested_action: "approve the first outbound send packet"
          }
        ]
      })),
      writeFile(resolve(openJarvisDir, "FOUNDER_ALERTS.md"), [
        "# Founder Alerts",
        "- active alerts: 1",
        "- delivery mode: open-jarvis inbox fallback",
        ""
      ].join("\n")),
      writeFile(resolve(openJarvisDir, "BRAIN.md"), [
        "# OpenJarvis Brain",
        "- founder ingress: open-jarvis",
        "- tracked lanes: 9",
        ""
      ].join("\n")),
      writeFile(resolve(stateDir, "prediction-review.latest.json"), JSON.stringify({
        review: {
          counts: { reject: 0, watch: 1, "paper-trade": 0 },
          topCandidate: { candidateId: "pm__mf", verdict: "watch", netEdgePct: 1.5 },
          readyForPaper: false,
          blockers: ["economics"],
          recommendation: "keep collecting"
        }
      })),
      writeFile(resolve(stateDir, "prediction-learning.latest.json"), JSON.stringify({
        recentCycleSummary: {
          totalCycles: 10,
          structuralWatchCycles: 3,
          economicBlockCycles: 2
        }
      })),
      writeFile(resolve(stateDir, "prediction-copy-demo.latest.json"), JSON.stringify({
        ts: "2026-04-15T10:00:00Z",
        ideas: [],
        blockers: ["domain-filter"],
        summary: "No approved copy-demo ideas."
      })),
      writeFile(resolve(stateDir, "futures-demo.latest.json"), JSON.stringify({
        deployable: false,
        sampleSequence: 12,
        lanes: [
          { accountId: "a1", label: "lane-1", primaryStrategy: "ict-displacement", focusSymbol: "NQ", action: "shadow" }
        ]
      })),
      writeFile(resolve(researcherDir, "latest-run.json"), JSON.stringify({
        runId: "r1",
        startedAt: "2026-04-15T09:00:00Z",
        finishedAt: "2026-04-15T09:05:00Z",
        targetsAttempted: 1,
        targetsSucceeded: 1,
        chunksCollected: 5,
        chunksKept: 4,
        firecrawlUsed: false,
        dedupRate: 0.2,
        kept: [{ title: "Firecrawl intro" }],
        status: "healthy",
        nextAction: "Keep ingesting and curate the next highest-priority researcher targets.",
        blockers: []
      })),
      writeFile(resolve(researchRoot, "source-catalog.json"), JSON.stringify([]))
    ]);

    const result = await buildOpenJarvisStatus({
      agencyStatusPath: resolve(agencyDir, "STATUS.md"),
      agencyOutboxPath: resolve(agencyDir, "OUTBOX.md"),
      approvalsPath: resolve(agencyDir, "boards/approvals.json"),
      founderAlertsPath: resolve(openJarvisDir, "FOUNDER_ALERTS.md"),
      brainPath: resolve(openJarvisDir, "BRAIN.md"),
      env: {
        BILL_CLOUD_PROVIDER: "nvidia-nim",
        BILL_CLOUD_BASE_URL: "https://integrate.api.nvidia.com/v1",
        BILL_CLOUD_REVIEW_MODEL: "moonshotai/kimi-k2.5",
        BILL_CLOUD_DEEP_REVIEW_MODEL: "moonshotai/kimi-k2.5"
      },
      bill: {
        baseDir: workspace,
        stateDir,
        researchDir: researcherDir,
        researchDataDir: resolve(workspace, "data/research"),
        sourceCatalogPath: resolve(researchRoot, "source-catalog.json")
      },
      persistHermesSupervisor: true,
      now: () => "2026-04-15T10:10:00Z"
    });

    expect(result.source.module).toBe("open-jarvis");
    expect(result.architecture.founderIngress).toBe("open-jarvis");
    expect(result.statePaths.hermesSupervisor).toBe(resolve(workspace, ".rumbling-hedge/state/hermes-supervisor.json"));
    expect(result.statePaths.openJarvisStatus).toBe(resolve(workspace, ".rumbling-hedge/state/openjarvis-status.json"));
    expect(result.statePaths.runtimeManifest).toBe(resolve(workspace, ".rumbling-hedge/state/runtime-manifest.json"));
    expect(result.brain.posture).toBe("hosted-budget-first");
    expect(result.architecture.controlPlane).toBe("hermes");
    expect(result.architecture.fixerRuntime).toBe("openclaw");
    expect(result.supervisor.owner).toBe("hermes");
    expect(result.supervisor.mode).toBe("bounded-parallel");
    expect(result.supervisor.maxParallelWorkers).toBe(3);
    expect(result.teamTopology.map((team) => team.owner)).toEqual(["bill", "agency-os", "researcher", "openclaw"]);
    expect(result.teamTopology.find((team) => team.owner === "bill")?.workers.some((worker) => worker.id === "strategy-lab")).toBe(true);
    expect(result.costPolicy.founderIngress).toBe("hosted-budget-first");
    expect(result.orchestration.owner).toBe("hermes");
    expect(result.orchestration.activeWork.length).toBeLessThanOrEqual(3);
    expect(result.orchestration.activeWork.some((task) => task.owner === "bill")).toBe(true);
    expect(result.orchestration.activeWork.some((task) => task.owner === "agency-os")).toBe(true);
    expect(result.orchestration.needsApprovalWork.length).toBeGreaterThan(0);
    expect(result.orchestration.todoList.some((task) => task.summary.includes("prediction scan policy"))).toBe(true);
    expect(result.actionQueue.some((action) => action.owner === "bill" && action.lane === "prediction")).toBe(true);
    expect(result.orchestration.todoList.some((task) => task.owner === "bill" && task.lane === "prediction")).toBe(true);
    expect(result.orchestration.todoList.some((task) => task.summary.includes("Loosen researcher filters"))).toBe(false);
    expect(result.orchestration.statePath).toBe(resolve(workspace, ".rumbling-hedge/state/hermes-supervisor.json"));
    expect(result.orchestration.heartbeats.length).toBe(result.orchestration.activeWork.length);
    expect(result.orchestration.controls.approvedTaskIds).toEqual([]);
    expect(result.orchestration.controls.pausedTaskIds).toEqual([]);
    expect(result.brain.activeModel).toBe("moonshotai/kimi-k2.5");
    expect(result.brain.embedModel).toBe("nomic-embed-text:latest");
    expect(result.brain.cloudProvider).toBe("nvidia-nim");
    expect(result.brain.cloudBaseUrl).toBe("https://integrate.api.nvidia.com/v1");
    expect(result.brain.cloudReviewModel).toBe("moonshotai/kimi-k2.5");
    expect(result.founderAttention.activeAlerts).toBe("1");
    expect(result.brainMemory.founderIngress).toBe("open-jarvis");
    expect(result.agencyOs.mergedMission).toBe("ship + sell");
    expect(result.agencyOs.operatingMode).toBe("four-lane merged office");
    expect(result.approvalQueue.count).toBe(1);
    expect(result.approvalQueue.requests[0]?.requestedAction).toBe("approve the first outbound send packet");
    expect(result.actionQueue.some((action) => action.owner === "agency-os")).toBe(true);
    expect(result.founder.routingOwner).toBe("bill");
    expect(result.founder.posture).toBe("configure");
    expect(result.founder.operatorReply.owner).toBe("bill");
    expect(result.founder.operatorReply.approvalsNeeded).toContain("approve the first outbound send packet");
    expect(result.founder.operatorReply.eta).toBe("blocked pending explicit approval");
    expect(result.bill.prediction.counts.watch).toBe(1);
    expect(result.bill.fundPlan.mode).toBe("stabilize-core");
    expect(result.bill.fundPlan.tracks.some((track) => track.id === "long-only-compounder")).toBe(true);
    const persisted = JSON.parse(await readFile(resolve(workspace, ".rumbling-hedge/state/hermes-supervisor.json"), "utf8")) as {
      owner: string;
      activeWork: Array<{ owner: string }>;
      needsApprovalWork: Array<{ owner: string }>;
      heartbeats: Array<{ owner: string; updatedAt: string }>;
      controls: { pausedTaskIds: string[]; approvedTaskIds: string[] };
    };
    const persistedStatus = JSON.parse(await readFile(resolve(workspace, ".rumbling-hedge/state/openjarvis-status.json"), "utf8")) as {
      statePaths: { runtimeManifest?: string };
      teamTopology: Array<{ owner: string }>;
    };
    const persistedManifest = JSON.parse(await readFile(resolve(workspace, ".rumbling-hedge/state/runtime-manifest.json"), "utf8")) as {
      workerTopology: Array<{ owner: string }>;
    };
    expect(persisted.owner).toBe("hermes");
    expect(persisted.activeWork.length).toBe(result.orchestration.activeWork.length);
    expect(persisted.needsApprovalWork.length).toBe(result.orchestration.needsApprovalWork.length);
    expect(persisted.heartbeats.length).toBe(result.orchestration.activeWork.length);
    expect(persisted.heartbeats.every((heartbeat) => typeof heartbeat.updatedAt === "string" && heartbeat.updatedAt.length > 0)).toBe(true);
    expect(persisted.controls.pausedTaskIds).toEqual([]);
    expect(persisted.controls.approvedTaskIds).toEqual([]);
    expect(persistedStatus.teamTopology.map((team) => team.owner)).toEqual(["bill", "agency-os", "researcher", "openclaw"]);
    expect(persistedStatus.statePaths.runtimeManifest).toBe(resolve(workspace, ".rumbling-hedge/state/runtime-manifest.json"));
    expect(persistedManifest.workerTopology.map((team) => team.owner)).toEqual(["bill", "agency-os", "researcher", "openclaw"]);
  });

  it("persists founder approvals and pauses across supervisor rebuilds", async () => {
    const workspace = await makeTempWorkspace();
    const agencyDir = resolve(workspace, ".openclaw/workspace-agency-os");
    const openJarvisDir = resolve(workspace, ".openclaw/workspace-open-jarvis");
    const stateDir = resolve(workspace, ".rumbling-hedge/state");
    const researcherDir = resolve(workspace, ".rumbling-hedge/research/researcher");
    const researchRoot = resolve(workspace, ".rumbling-hedge/research");
    const researchDataDir = resolve(workspace, "data/research");

    await Promise.all([
      mkdir(agencyDir, { recursive: true }),
      mkdir(openJarvisDir, { recursive: true }),
      mkdir(stateDir, { recursive: true }),
      mkdir(researcherDir, { recursive: true }),
      mkdir(researchRoot, { recursive: true }),
      mkdir(researchDataDir, { recursive: true })
    ]);

    await Promise.all([
      writeFile(resolve(agencyDir, "STATUS.md"), "# Agency OS Status\n- merged mission: ship + sell\n"),
      writeFile(resolve(agencyDir, "OUTBOX.md"), "# Agency OS Outbox\n- founder inbox tail: one founder channel only\n"),
      writeFile(resolve(openJarvisDir, "FOUNDER_ALERTS.md"), "# Founder Alerts\n"),
      writeFile(resolve(openJarvisDir, "BRAIN.md"), "# OpenJarvis Brain\n- founder ingress: open-jarvis\n"),
      writeFile(resolve(stateDir, "prediction-review.latest.json"), JSON.stringify({
        review: {
          counts: { reject: 0, watch: 1, "paper-trade": 0 },
          topCandidate: { candidateId: "pm__mf", verdict: "watch", netEdgePct: 1.5 },
          readyForPaper: false,
          blockers: ["economics"],
          recommendation: "keep collecting"
        }
      })),
      writeFile(resolve(stateDir, "prediction-learning.latest.json"), JSON.stringify({
        recentCycleSummary: {
          totalCycles: 10,
          structuralWatchCycles: 3,
          economicBlockCycles: 2
        }
      })),
      writeFile(resolve(stateDir, "prediction-copy-demo.latest.json"), JSON.stringify({
        ts: "2026-04-15T10:00:00Z",
        ideas: [],
        blockers: ["domain-filter"],
        summary: "No approved copy-demo ideas."
      })),
      writeFile(resolve(stateDir, "futures-demo.latest.json"), JSON.stringify({
        deployable: false,
        sampleSequence: 12,
        lanes: [
          { accountId: "a1", label: "lane-1", primaryStrategy: "ict-displacement", focusSymbol: "NQ", action: "shadow" }
        ]
      })),
      writeFile(resolve(researcherDir, "latest-run.json"), JSON.stringify({
        runId: "r1",
        startedAt: "2026-04-15T09:00:00Z",
        finishedAt: "2026-04-15T09:05:00Z",
        targetsAttempted: 1,
        targetsSucceeded: 1,
        chunksCollected: 5,
        chunksKept: 4,
        firecrawlUsed: false,
        dedupRate: 0.2,
        kept: [{ title: "Firecrawl intro" }]
      })),
      writeFile(resolve(researchRoot, "source-catalog.json"), JSON.stringify([]))
    ]);

    const first = await buildOpenJarvisStatus({
      agencyStatusPath: resolve(agencyDir, "STATUS.md"),
      agencyOutboxPath: resolve(agencyDir, "OUTBOX.md"),
      approvalsPath: resolve(agencyDir, "boards/approvals.json"),
      founderAlertsPath: resolve(openJarvisDir, "FOUNDER_ALERTS.md"),
      brainPath: resolve(openJarvisDir, "BRAIN.md"),
      bill: {
        baseDir: workspace,
        stateDir,
        researchDir: researcherDir,
        researchDataDir,
        sourceCatalogPath: resolve(researchRoot, "source-catalog.json")
      },
      persistHermesSupervisor: true,
      now: () => "2026-04-15T10:10:00Z"
    });

    const approvalTask = first.orchestration.needsApprovalWork.find((task) => task.owner === "bill");
    const activeTask = first.orchestration.activeWork.find((task) => task.owner === "bill");
    expect(approvalTask).toBeTruthy();
    expect(activeTask).toBeTruthy();

    await applyHermesSupervisorDecision({
      filePath: first.orchestration.statePath,
      action: "approve",
      taskId: approvalTask!.id,
      at: "2026-04-15T10:11:00Z"
    });
    await applyHermesSupervisorDecision({
      filePath: first.orchestration.statePath,
      action: "pause",
      taskId: activeTask!.id,
      at: "2026-04-15T10:12:00Z"
    });

    const second = await buildOpenJarvisStatus({
      agencyStatusPath: resolve(agencyDir, "STATUS.md"),
      agencyOutboxPath: resolve(agencyDir, "OUTBOX.md"),
      approvalsPath: resolve(agencyDir, "boards/approvals.json"),
      founderAlertsPath: resolve(openJarvisDir, "FOUNDER_ALERTS.md"),
      brainPath: resolve(openJarvisDir, "BRAIN.md"),
      bill: {
        baseDir: workspace,
        stateDir,
        researchDir: researcherDir,
        researchDataDir,
        sourceCatalogPath: resolve(researchRoot, "source-catalog.json")
      },
      persistHermesSupervisor: true,
      now: () => "2026-04-15T10:13:00Z"
    });

    expect(second.orchestration.controls.approvedTaskIds).toContain(approvalTask!.id);
    expect(second.orchestration.controls.pausedTaskIds).toContain(activeTask!.id);
    expect(second.orchestration.pausedWork.some((task) => task.id === activeTask!.id)).toBe(true);
    expect(second.orchestration.activeWork.some((task) => task.id === activeTask!.id)).toBe(false);
    expect(second.orchestration.needsApprovalWork.some((task) => task.id === approvalTask!.id)).toBe(false);
    expect(second.orchestration.todoList.some((task) => task.id === approvalTask!.id)).toBe(true);
    expect(second.founder.approvalNeeded).toBe(true);
  });

  it("routes urgent systems issues to Hermes when founder alerts flag runtime drift", async () => {
    const workspace = await makeTempWorkspace();
    const agencyDir = resolve(workspace, ".openclaw/workspace-agency-os");
    const openJarvisDir = resolve(workspace, ".openclaw/workspace-open-jarvis");

    await Promise.all([
      mkdir(agencyDir, { recursive: true }),
      mkdir(openJarvisDir, { recursive: true })
    ]);

    await Promise.all([
      writeFile(resolve(agencyDir, "STATUS.md"), "# Agency OS Status\n"),
      writeFile(resolve(agencyDir, "OUTBOX.md"), "# Agency OS Outbox\n"),
      writeFile(resolve(openJarvisDir, "FOUNDER_ALERTS.md"), [
        "# Founder Alerts",
        "- active alerts: 1",
        "- alert: runtime drift detected in launchd health checks",
        ""
      ].join("\n")),
      writeFile(resolve(openJarvisDir, "BRAIN.md"), "# OpenJarvis Brain\n")
    ]);

    const result = await buildOpenJarvisStatus({
      agencyStatusPath: resolve(agencyDir, "STATUS.md"),
      agencyOutboxPath: resolve(agencyDir, "OUTBOX.md"),
      approvalsPath: resolve(agencyDir, "boards/approvals.json"),
      founderAlertsPath: resolve(openJarvisDir, "FOUNDER_ALERTS.md"),
      brainPath: resolve(openJarvisDir, "BRAIN.md"),
      bill: {
        baseDir: workspace
      },
      now: () => "2026-04-15T10:10:00Z"
    });

    expect(result.actionQueue[0]?.owner).toBe("hermes");
    expect(result.founder.routingOwner).toBe("hermes");
    expect(result.founder.posture).toBe("configure");
  });

  it("ignores resolved historical prediction-cycle failures once newer healthy cycles exist", async () => {
    const workspace = await makeTempWorkspace();
    const agencyDir = resolve(workspace, ".openclaw/workspace-agency-os");
    const openJarvisDir = resolve(workspace, ".openclaw/workspace-open-jarvis");
    const stateDir = resolve(workspace, ".rumbling-hedge/state");
    const researcherDir = resolve(workspace, ".rumbling-hedge/research/researcher");
    const researchRoot = resolve(workspace, ".rumbling-hedge/research");
    const logsDir = resolve(workspace, ".rumbling-hedge/logs");

    await Promise.all([
      mkdir(agencyDir, { recursive: true }),
      mkdir(openJarvisDir, { recursive: true }),
      mkdir(stateDir, { recursive: true }),
      mkdir(researcherDir, { recursive: true }),
      mkdir(researchRoot, { recursive: true }),
      mkdir(logsDir, { recursive: true })
    ]);

    await Promise.all([
      writeFile(resolve(agencyDir, "STATUS.md"), "# Agency OS Status\n"),
      writeFile(resolve(agencyDir, "OUTBOX.md"), "# Agency OS Outbox\n"),
      writeFile(resolve(openJarvisDir, "FOUNDER_ALERTS.md"), "# Founder Alerts\n"),
      writeFile(resolve(openJarvisDir, "BRAIN.md"), "# OpenJarvis Brain\n"),
      writeFile(resolve(stateDir, "prediction-review.latest.json"), JSON.stringify({
        review: {
          ts: "2026-04-18T00:30:00Z",
          counts: { reject: 0, watch: 1, "paper-trade": 0 },
          readyForPaper: false,
          recommendation: "keep collecting"
        }
      })),
      writeFile(resolve(stateDir, "prediction-learning.latest.json"), JSON.stringify({ ts: "2026-04-18T00:30:00Z" })),
      writeFile(resolve(stateDir, "prediction-copy-demo.latest.json"), JSON.stringify({ ts: "2026-04-18T00:30:00Z", ideas: [] })),
      writeFile(resolve(stateDir, "futures-demo.latest.json"), JSON.stringify({
        ts: "2026-04-18T00:30:00Z",
        posture: { deployableNow: false },
        sampling: { ts: "2026-04-18T00:30:00Z", laneCount: 0, lanes: [] }
      })),
      writeFile(resolve(researcherDir, "latest-run.json"), JSON.stringify({
        runId: "r1",
        finishedAt: "2026-04-18T00:20:00Z",
        targetsAttempted: 1,
        targetsSucceeded: 1,
        chunksCollected: 1,
        chunksKept: 1,
        firecrawlUsed: true,
        topKeptTitles: ["one"],
        status: "healthy"
      })),
      writeFile(resolve(researchRoot, "source-catalog.json"), JSON.stringify([])),
      writeFile(resolve(logsDir, "prediction-cycle-history.jsonl"), [
        JSON.stringify({ ts: "2026-04-17T10:00:00Z", posture: "failed", error: "old failure" }),
        JSON.stringify({ ts: "2026-04-18T00:25:00Z", posture: "watch-only" })
      ].join("\n"))
    ]);

    const result = await buildOpenJarvisStatus({
      agencyStatusPath: resolve(agencyDir, "STATUS.md"),
      agencyOutboxPath: resolve(agencyDir, "OUTBOX.md"),
      approvalsPath: resolve(agencyDir, "boards/approvals.json"),
      founderAlertsPath: resolve(openJarvisDir, "FOUNDER_ALERTS.md"),
      brainPath: resolve(openJarvisDir, "BRAIN.md"),
      bill: {
        baseDir: workspace,
        stateDir,
        researchDir: researcherDir,
        sourceCatalogPath: resolve(researchRoot, "source-catalog.json")
      },
      now: () => "2026-04-18T00:35:00Z"
    });

    expect(result.runtimeHealth.recentFailures).toEqual([]);
    expect(result.founder.routingOwner).toBe("bill");
  });

  it("does not route to Hermes just because brain prose mentions Hermes", async () => {
    const workspace = await makeTempWorkspace();
    const agencyDir = resolve(workspace, ".openclaw/workspace-agency-os");
    const openJarvisDir = resolve(workspace, ".openclaw/workspace-open-jarvis");
    const stateDir = resolve(workspace, ".rumbling-hedge/state");
    const researcherDir = resolve(workspace, ".rumbling-hedge/research/researcher");
    const researchRoot = resolve(workspace, ".rumbling-hedge/research");

    await Promise.all([
      mkdir(agencyDir, { recursive: true }),
      mkdir(openJarvisDir, { recursive: true }),
      mkdir(stateDir, { recursive: true }),
      mkdir(researcherDir, { recursive: true }),
      mkdir(researchRoot, { recursive: true })
    ]);

    await Promise.all([
      writeFile(resolve(agencyDir, "STATUS.md"), "# Agency OS Status\n"),
      writeFile(resolve(agencyDir, "OUTBOX.md"), "# Agency OS Outbox\n"),
      writeFile(resolve(openJarvisDir, "FOUNDER_ALERTS.md"), [
        "# Founder Alerts",
        "- active alerts: 0",
        ""
      ].join("\n")),
      writeFile(resolve(openJarvisDir, "BRAIN.md"), [
        "# OpenJarvis Brain",
        "- posture: Hermes is the adaptive audit and playbook-learning lane, not the founder cortex.",
        "- founder ingress: open-jarvis",
        ""
      ].join("\n")),
      writeFile(resolve(stateDir, "prediction-review.latest.json"), JSON.stringify({
        review: {
          ts: "2026-04-18T00:30:00Z",
          counts: { reject: 0, watch: 1, "paper-trade": 0 },
          readyForPaper: false,
          recommendation: "keep collecting"
        }
      })),
      writeFile(resolve(stateDir, "prediction-learning.latest.json"), JSON.stringify({ ts: "2026-04-18T00:30:00Z" })),
      writeFile(resolve(stateDir, "prediction-copy-demo.latest.json"), JSON.stringify({
        ts: "2026-04-18T00:30:00Z",
        ideas: [],
        blockers: []
      })),
      writeFile(resolve(stateDir, "futures-demo.latest.json"), JSON.stringify({
        ts: "2026-04-18T00:30:00Z",
        posture: { deployableNow: false },
        sampling: { ts: "2026-04-18T00:30:00Z", laneCount: 1, lanes: [] }
      })),
      writeFile(resolve(researcherDir, "latest-run.json"), JSON.stringify({
        runId: "r2",
        finishedAt: "2026-04-18T00:20:00Z",
        targetsAttempted: 1,
        targetsSucceeded: 1,
        chunksCollected: 1,
        chunksKept: 1,
        firecrawlUsed: true,
        topKeptTitles: ["one"],
        status: "healthy"
      })),
      writeFile(resolve(researchRoot, "source-catalog.json"), JSON.stringify([]))
    ]);

    const result = await buildOpenJarvisStatus({
      agencyStatusPath: resolve(agencyDir, "STATUS.md"),
      agencyOutboxPath: resolve(agencyDir, "OUTBOX.md"),
      approvalsPath: resolve(agencyDir, "boards/approvals.json"),
      founderAlertsPath: resolve(openJarvisDir, "FOUNDER_ALERTS.md"),
      brainPath: resolve(openJarvisDir, "BRAIN.md"),
      bill: {
        baseDir: workspace,
        stateDir,
        researchDir: researcherDir,
        sourceCatalogPath: resolve(researchRoot, "source-catalog.json")
      },
      now: () => "2026-04-18T00:35:00Z"
    });

    expect(result.actionQueue[0]?.owner).not.toBe("hermes");
    expect(result.founder.routingOwner).toBe("bill");
  });
});
