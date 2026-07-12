import type { AgenticLearningAction, Bar, LabConfig } from "../domain.js";
import type { NewsGate } from "../news/base.js";
import { buildDashboardSnapshot } from "./dashboardSnapshot.js";

function unique(values: string[]): string[] {
  return [...new Set(values.filter(Boolean))];
}

function buildHeadline(args: {
  status: "green" | "yellow" | "red";
  deployableNow: boolean;
  action: "paper-trade" | "stand-down";
  operatingMode: "stabilize" | "guarded-expansion";
}): string {
  const { status, deployableNow, action, operatingMode } = args;

  if (action === "paper-trade" && deployableNow) {
    return operatingMode === "guarded-expansion"
      ? "Jarvis sees a deployable core and favors a guarded paper-trade expansion."
      : "Jarvis sees a deployable setup and allows paper trading under current guardrails.";
  }

  if (status === "red") {
    return "Jarvis is in stand-down mode because risk or evidence checks are failing materially.";
  }

  if (status === "yellow") {
    return "Jarvis is research-only for now and wants tighter evidence before paper deployment.";
  }

  return "Jarvis is stable, but the current session still does not justify a paper-trade action.";
}

function buildQuestionsForRajiv(args: {
  failedChecks: string[];
  deployableNow: boolean;
  killSwitchActive: boolean;
  topCandidateExists: boolean;
}): string[] {
  const prompts: string[] = [];

  if (args.killSwitchActive) {
    prompts.push("Should the manual kill switch remain active, or can K treat the freeze as cleared after review?");
  }

  if (args.failedChecks.includes("testTradeCount") || args.failedChecks.includes("scoreStability")) {
    prompts.push("Do we have a newer or wider normalized data window so Jarvis can rerun with more evidence?");
  }

  if (args.failedChecks.includes("maxDrawdownR") || args.failedChecks.includes("riskOfRuinProb")) {
    prompts.push("Has Rajiv changed the tolerated demo risk budget, or should K keep the current hard risk limits locked?");
  }

  if (args.failedChecks.includes("activeFamilies")) {
    prompts.push("Should the allowed market universe change, or should Jarvis keep the universe narrow until one family proves itself?");
  }

  if (!args.deployableNow) {
    prompts.push("Have any founder inputs changed, specifically account path, allowed market universe, demo risk budget, or hard no-go windows?");
  }

  if (args.deployableNow && !args.topCandidateExists) {
    prompts.push("Do you want K to keep the system in shadow mode until a cleaner session candidate appears?");
  }

  return unique(prompts);
}

function cleanEnvPatch(envPatch: AgenticLearningAction["envPatch"]): Record<string, number> | null {
  const entries = Object.entries(envPatch).filter(([, value]) => typeof value === "number");
  if (entries.length === 0) {
    return null;
  }

  return Object.fromEntries(entries) as Record<string, number>;
}

function buildKAction(args: {
  action: AgenticLearningAction;
  deployableNow: boolean;
}): string {
  const { action, deployableNow } = args;
  const envPatch = cleanEnvPatch(action.envPatch);

  if (action.id === "risk-tighten-core") {
    return "Keep Jarvis in paper-only mode, apply the tighter risk patch on the next bounded pass, and rerun before changing scope.";
  }

  if (action.id === "expectancy-raise-rr") {
    return "Raise the setup bar first, then compare the next Jarvis pass instead of widening trade freedom.";
  }

  if (action.id === "evidence-upgrade") {
    return "Do not change risk rails yet. Bring a larger normalized dataset into the next run and check whether stability improves.";
  }

  if (action.id === "sample-density") {
    return "Only test the higher-density patch in demo mode, and only after hard risk checks are already clean.";
  }

  if (action.id === "portfolio-breadth") {
    return "Expand research breadth carefully, not execution breadth. Keep live scope unchanged until one added family proves itself.";
  }

  if (deployableNow && action.id === "promotion-shadow") {
    return "Stay demo-only and use shadow or paper observation before any promotion request reaches Rajiv.";
  }

  if (envPatch) {
    return "Apply this patch in demo mode only, then compare the next Jarvis result against the current baseline.";
  }

  return "Treat this as a bounded follow-up item, not a license to loosen guardrails.";
}

function buildActionQueue(args: {
  learningActions: AgenticLearningAction[];
  deployableNow: boolean;
}): Array<{
  priority: "now" | "next" | "later";
  title: string;
  rationale: string;
  envPatch: Record<string, number> | null;
  kAction: string;
}> {
  return args.learningActions.map((action) => ({
    priority: action.priority,
    title: action.title,
    rationale: action.rationale,
    envPatch: cleanEnvPatch(action.envPatch),
    kAction: buildKAction({
      action,
      deployableNow: args.deployableNow
    })
  }));
}

function buildEscalationTriggers(args: {
  failedChecks: string[];
  deployableNow: boolean;
  killSwitchActive: boolean;
  liveExecutionEnabled: boolean;
}): string[] {
  const triggers: string[] = [];

  if (args.killSwitchActive) {
    triggers.push("Escalate immediately if anyone asks for execution while the manual kill switch is active.");
  }

  if (!args.deployableNow) {
    triggers.push("Escalate before any request to enable live execution or remove demo/read-only safeguards.");
  }

  if (args.failedChecks.includes("maxDrawdownR") || args.failedChecks.includes("riskOfRuinProb")) {
    triggers.push("Escalate if drawdown or risk-of-ruin still fails after the next bounded improvement pass.");
  }

  if (args.failedChecks.includes("testTradeCount") || args.failedChecks.includes("scoreStability")) {
    triggers.push("Escalate if a fresh normalized data pass still leaves Jarvis short on evidence or unstable across windows.");
  }

  if (args.liveExecutionEnabled) {
    triggers.push("Escalate if live execution is toggled on without an explicitly deployable report and unchanged account locks.");
  }

  return unique(triggers);
}

function buildRajivDraft(args: {
  headline: string;
  status: "green" | "yellow" | "red";
  survivabilityScore: number;
  deployableNow: boolean;
  recommendedActionReason: string;
  tellRajiv: string[];
  askRajiv: string[];
}): string {
  const opener = `Jarvis update: ${args.headline}`;
  const statusLine = `Current status is ${args.status} with survivability score ${args.survivabilityScore}, and deployable-now is ${args.deployableNow ? "true" : "false"}.`;
  const actionLine = `Recommended posture: ${args.recommendedActionReason}`;
  const askLine = args.askRajiv[0] ? `Main question for you: ${args.askRajiv[0]}` : null;

  return [opener, statusLine, actionLine, askLine ?? args.tellRajiv[0] ?? null]
    .filter((value): value is string => Boolean(value))
    .join(" ");
}

export async function buildJarvisBrief(args: {
  bars: Bar[];
  baseConfig: LabConfig;
  newsGate: NewsGate;
  operatorNote?: string;
}): Promise<{
  timestamp: string;
  source: {
    system: "rumbling-hedge";
    module: "open-jarvis";
  };
  summary: {
    headline: string;
    status: "green" | "yellow" | "red";
    operatingMode: "stabilize" | "guarded-expansion";
    survivabilityScore: number;
    deployableNow: boolean;
    recommendedAction: "paper-trade" | "stand-down";
    recommendedActionReason: string;
  };
  operatorNote: string | null;
  kMainHandoff: {
    tellRajiv: string[];
    askRajiv: string[];
    nextChecklist: string[];
    actionQueue: Array<{
      priority: "now" | "next" | "later";
      title: string;
      rationale: string;
      envPatch: Record<string, number> | null;
      kAction: string;
    }>;
    escalationTriggers: string[];
    rajivDraft: string;
  };
  machineContext: {
    selectedProfileId: string | null;
    deployableProfileId: string | null;
    winnerProfileId: string | null;
    preferredSymbols: string[];
    activeFamilies: string[];
    failedChecks: string[];
    topCandidate: null | {
      symbol: string;
      strategyId: string;
      regime: string;
      directionalBias: string;
      expectedValueScore: number;
      regimeConfidence: number;
    };
    killSwitchActive: boolean;
    liveExecutionEnabled: boolean;
    demoOnly: boolean;
    readOnly: boolean;
  };
}> {
  const snapshot = await buildDashboardSnapshot(args);
  const report = snapshot.dayPlan.report;
  const selection = snapshot.dayPlan.selection;
  const topCandidate = selection.rankedCandidates[0] ?? null;
  const headline = buildHeadline({
    status: report.status,
    deployableNow: report.deployableNow,
    action: selection.selectedExecutionPlan.action,
    operatingMode: report.agentStatus.operatingMode
  });
  const tellRajiv = unique([
    report.agentStatus.message,
    `Jarvis status is ${report.status} with survivability score ${report.survivabilityScore}.`,
    report.deployableNow
      ? `Selected profile ${selection.selectedProfileId ?? report.deployableProfileId ?? report.winnerProfileId ?? "unknown"} is deployable under current guardrails.`
      : "No profile cleared the promotion gate, so Jarvis remains in research-only mode.",
    selection.selectedExecutionPlan.reason
  ]);
  const askRajiv = buildQuestionsForRajiv({
    failedChecks: report.failedChecks,
    deployableNow: report.deployableNow,
    killSwitchActive: snapshot.killSwitch.state.active,
    topCandidateExists: topCandidate !== null
  });

  return {
    timestamp: snapshot.timestamp,
    source: {
      system: "rumbling-hedge",
      module: "open-jarvis"
    },
    summary: {
      headline,
      status: report.status,
      operatingMode: report.agentStatus.operatingMode,
      survivabilityScore: report.survivabilityScore,
      deployableNow: report.deployableNow,
      recommendedAction: selection.selectedExecutionPlan.action,
      recommendedActionReason: selection.selectedExecutionPlan.reason
    },
    operatorNote: args.operatorNote?.trim() ? args.operatorNote.trim() : null,
    kMainHandoff: {
      tellRajiv,
      askRajiv,
      nextChecklist: report.nextRunChecklist.slice(0, 4),
      actionQueue: buildActionQueue({
        learningActions: report.learningActions,
        deployableNow: report.deployableNow
      }),
      escalationTriggers: buildEscalationTriggers({
        failedChecks: report.failedChecks,
        deployableNow: report.deployableNow,
        killSwitchActive: snapshot.killSwitch.state.active,
        liveExecutionEnabled: snapshot.operator.liveExecutionEnabled
      }),
      rajivDraft: buildRajivDraft({
        headline,
        status: report.status,
        survivabilityScore: report.survivabilityScore,
        deployableNow: report.deployableNow,
        recommendedActionReason: selection.selectedExecutionPlan.reason,
        tellRajiv,
        askRajiv
      })
    },
    machineContext: {
      selectedProfileId: selection.selectedProfileId,
      deployableProfileId: report.deployableProfileId,
      winnerProfileId: report.winnerProfileId,
      preferredSymbols: selection.preferredSymbols,
      activeFamilies: selection.activeFamilies,
      failedChecks: report.failedChecks,
      topCandidate: topCandidate
        ? {
            symbol: topCandidate.symbol,
            strategyId: topCandidate.strategyId,
            regime: topCandidate.regime,
            directionalBias: topCandidate.directionalBias,
            expectedValueScore: topCandidate.expectedValueScore,
            regimeConfidence: topCandidate.regimeConfidence
          }
        : null,
      killSwitchActive: snapshot.killSwitch.state.active,
      liveExecutionEnabled: snapshot.operator.liveExecutionEnabled,
      demoOnly: snapshot.operator.demoOnly,
      readOnly: snapshot.operator.readOnly
    }
  };
}
