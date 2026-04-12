import type { Bar, LabConfig } from "../domain.js";
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

  return {
    timestamp: snapshot.timestamp,
    source: {
      system: "rumbling-hedge",
      module: "open-jarvis"
    },
    summary: {
      headline: buildHeadline({
        status: report.status,
        deployableNow: report.deployableNow,
        action: selection.selectedExecutionPlan.action,
        operatingMode: report.agentStatus.operatingMode
      }),
      status: report.status,
      operatingMode: report.agentStatus.operatingMode,
      survivabilityScore: report.survivabilityScore,
      deployableNow: report.deployableNow,
      recommendedAction: selection.selectedExecutionPlan.action,
      recommendedActionReason: selection.selectedExecutionPlan.reason
    },
    operatorNote: args.operatorNote?.trim() ? args.operatorNote.trim() : null,
    kMainHandoff: {
      tellRajiv: unique([
        report.agentStatus.message,
        `Jarvis status is ${report.status} with survivability score ${report.survivabilityScore}.`,
        report.deployableNow
          ? `Selected profile ${selection.selectedProfileId ?? report.deployableProfileId ?? report.winnerProfileId ?? "unknown"} is deployable under current guardrails.`
          : "No profile cleared the promotion gate, so Jarvis remains in research-only mode.",
        selection.selectedExecutionPlan.reason
      ]),
      askRajiv: buildQuestionsForRajiv({
        failedChecks: report.failedChecks,
        deployableNow: report.deployableNow,
        killSwitchActive: snapshot.killSwitch.state.active,
        topCandidateExists: topCandidate !== null
      }),
      nextChecklist: report.nextRunChecklist.slice(0, 4)
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
