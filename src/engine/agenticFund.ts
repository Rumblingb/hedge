import type {
  AgenticFundReport,
  AgenticIssue,
  AgenticLearningAction,
  FamilyBudgetEntry,
  LabConfig
} from "../domain.js";
import type { PromotionGateCheck } from "./promotionGate.js";
import type { WalkforwardResearchResult } from "./walkforward.js";

const CHECK_TO_ISSUE: Record<string, { component: AgenticIssue["component"]; severity: AgenticIssue["severity"]; summary: string; fixes: string[] }> = {
  testTradeCount: {
    component: "data",
    severity: "high",
    summary: "Out-of-sample evidence is too thin to trust profile quality.",
    fixes: [
      "Increase sample window until test trades exceed threshold.",
      "Add more sessions and regime variety before promotion.",
      "Prefer profiles with stable activity over sparse signal sets."
    ]
  },
  testNetR: {
    component: "research",
    severity: "high",
    summary: "Net out-of-sample performance is not positive.",
    fixes: [
      "Demote current winner and keep research mode only.",
      "Prune weakest strategy leg from active ensemble.",
      "Re-run with stricter risk and friction assumptions."
    ]
  },
  testExpectancyR: {
    component: "research",
    severity: "high",
    summary: "Per-trade expectancy is negative.",
    fixes: [
      "Raise minimum RR and reject low-quality setups.",
      "Reduce daily trade count to focus on highest-confidence entries.",
      "Review signal thresholds and execution timing."
    ]
  },
  maxDrawdownR: {
    component: "risk",
    severity: "high",
    summary: "Drawdown exceeds policy limits.",
    fixes: [
      "Reduce max contracts and max trades per day.",
      "Lower max daily loss cap until drawdown normalizes.",
      "Pause promotion and force de-risked paper pass."
    ]
  },
  cvar95TradeR: {
    component: "risk",
    severity: "medium",
    summary: "Tail loss profile is too severe.",
    fixes: [
      "Tighten stop structure for high-volatility windows.",
      "Avoid thin-liquidity intervals in session filters.",
      "Stress-test with higher slippage and fee assumptions."
    ]
  },
  riskOfRuinProb: {
    component: "risk",
    severity: "high",
    summary: "Estimated risk of ruin is unacceptably high.",
    fixes: [
      "Cut leverage and reduce sequence exposure.",
      "Reduce daily loss and consecutive-loss tolerances.",
      "Require multi-window stability before capital increase."
    ]
  },
  scoreStability: {
    component: "research",
    severity: "medium",
    summary: "Profile ranking is unstable across windows.",
    fixes: [
      "Run additional walk-forward windows and compare persistence.",
      "Keep only profiles that remain top-tier across regimes.",
      "Delay promotion until stability recovers."
    ]
  },
  activeFamilies: {
    component: "portfolio",
    severity: "medium",
    summary: "No active family diversification remains after budgeting.",
    fixes: [
      "Broaden candidate universe with liquid families.",
      "Require at least one active family with positive test contribution.",
      "Keep capital sidelined when all families are degraded."
    ]
  }
};

function unique<T>(values: T[]): T[] {
  return [...new Set(values)];
}

function scorePenaltyByCheck(name: string): number {
  switch (name) {
    case "testTradeCount":
      return 16;
    case "testNetR":
      return 22;
    case "testExpectancyR":
      return 16;
    case "maxDrawdownR":
      return 18;
    case "riskOfRuinProb":
      return 18;
    case "cvar95TradeR":
      return 10;
    case "scoreStability":
      return 10;
    case "activeFamilies":
      return 8;
    default:
      return 6;
  }
}

function buildIssues(failedChecks: PromotionGateCheck[]): AgenticIssue[] {
  return failedChecks.map((check, index) => {
    const template = CHECK_TO_ISSUE[check.name] ?? {
      component: "research" as const,
      severity: "medium" as const,
      summary: `Promotion check ${check.name} failed.`,
      fixes: ["Review failed check and tighten validation thresholds."]
    };

    return {
      id: `issue-${index + 1}`,
      severity: template.severity,
      component: template.component,
      summary: template.summary,
      fixActions: template.fixes
    };
  });
}

function buildLearningActions(args: {
  failedChecks: PromotionGateCheck[];
  config: LabConfig;
}): AgenticLearningAction[] {
  const { failedChecks, config } = args;
  const failed = new Set(failedChecks.map((check) => check.name));
  const actions: AgenticLearningAction[] = [];

  if (failed.has("maxDrawdownR") || failed.has("riskOfRuinProb")) {
    actions.push({
      id: "risk-tighten-core",
      priority: "now",
      title: "Auto-tighten core risk limits",
      rationale: "Drawdown/ruin checks failed; immediate de-risking is required.",
      envPatch: {
        RH_MAX_CONTRACTS: Math.max(1, config.guardrails.maxContracts - 1),
        RH_MAX_TRADES_PER_DAY: Math.max(1, config.guardrails.maxTradesPerDay - 1),
        RH_MAX_DAILY_LOSS_R: Number(Math.max(0.75, config.guardrails.maxDailyLossR - 0.5).toFixed(2))
      }
    });
  }

  if (failed.has("testExpectancyR")) {
    actions.push({
      id: "expectancy-raise-rr",
      priority: "now",
      title: "Increase minimum RR filter",
      rationale: "Negative expectancy requires stricter setup selection.",
      envPatch: {
        RH_MIN_RR: Number((config.guardrails.minRr + 0.2).toFixed(2))
      }
    });
  }

  if (failed.has("testTradeCount") || failed.has("scoreStability")) {
    actions.push({
      id: "evidence-upgrade",
      priority: "next",
      title: "Increase evidence depth",
      rationale: "Current sample/stability is insufficient for promotion confidence.",
      envPatch: {}
    });
  }

  if (failed.has("testTradeCount") && !failed.has("riskOfRuinProb") && !failed.has("maxDrawdownR")) {
    actions.push({
      id: "sample-density",
      priority: "next",
      title: "Increase signal density safely",
      rationale: "Trade count is thin while hard risk checks are not failing.",
      envPatch: {
        RH_MAX_TRADES_PER_DAY: Math.min(6, config.guardrails.maxTradesPerDay + 1),
        RH_MIN_RR: Number(Math.max(2, config.guardrails.minRr - 0.2).toFixed(2))
      }
    });
  }

  if (failed.has("activeFamilies")) {
    actions.push({
      id: "portfolio-breadth",
      priority: "next",
      title: "Restore active family breadth",
      rationale: "Portfolio concentration became non-viable after family scoring.",
      envPatch: {}
    });
  }

  if (actions.length === 0) {
    actions.push({
      id: "promotion-shadow",
      priority: "later",
      title: "Run controlled shadow deployment",
      rationale: "All promotion checks passed; proceed with conservative shadow execution.",
      envPatch: {}
    });
  }

  return actions;
}

function deriveCandidateFamilies(ranked: FamilyBudgetEntry[] | undefined): AgenticFundReport["evolutionPlan"]["candidateMarkets"] {
  if (!ranked || ranked.length === 0) {
    return [];
  }

  return ranked
    .filter((entry) => entry.combinedNetR > 0)
    .slice(0, 3)
    .map((entry) => ({
      marketFamily: entry.marketFamily,
      confidence: Number(entry.confidence.toFixed(4)),
      note: entry.note
    }));
}

function buildAgentStatus(args: {
  profitableNow: boolean;
  deployableNow: boolean;
  failedChecks: PromotionGateCheck[];
}): AgenticFundReport["agentStatus"] {
  const { profitableNow, deployableNow, failedChecks } = args;
  if (profitableNow && deployableNow && failedChecks.length === 0) {
    return {
      operatingMode: "guarded-expansion",
      message: "System is profitable and deployable; evaluating next best markets under existing guardrails."
    };
  }

  return {
    operatingMode: "stabilize",
    message: "System remains in narrow stabilization mode; tightening and validating before any expansion."
  };
}

function buildEvolutionPlan(args: {
  reportStatus: AgenticFundReport["agentStatus"];
  candidateFamilies: AgenticFundReport["evolutionPlan"]["candidateMarkets"];
}): AgenticFundReport["evolutionPlan"] {
  const { reportStatus, candidateFamilies } = args;

  if (reportStatus.operatingMode === "guarded-expansion") {
    return {
      objective: "Scale selectively from a profitable core without violating risk guardrails.",
      currentStep: "Evaluate top candidate families in shadow mode with current funded/challenge limits.",
      nextSteps: [
        "Run rolling OOS for each candidate family with unchanged risk guardrails.",
        "Promote only candidates with positive expectancy, stable score, and acceptable tail risk.",
        "Increase breadth one family at a time and re-run live-readiness after each promotion."
      ],
      guardrailsLocked: [
        "Trailing max drawdown lock",
        "Daily loss lock",
        "Consecutive loss lock",
        "Red-folder event blackout"
      ],
      candidateMarkets: candidateFamilies,
      institutionalPrinciples: [
        "Risk first, alpha second.",
        "Concentrate in liquid instruments and measurable edge.",
        "Expand only after repeated out-of-sample confirmation."
      ]
    };
  }

  return {
    objective: "Restore and prove profitability in a narrow, controlled scope.",
    currentStep: "Keep current universe constrained and resolve failed checks before expansion.",
    nextSteps: [
      "Apply highest-priority learning actions and rerun walkforward.",
      "Track rejection reasons and tail-risk checks until stable green reports appear.",
      "Enable guarded expansion only after profitability and deployability are both true."
    ],
    guardrailsLocked: [
      "Trailing max drawdown lock",
      "Daily loss lock",
      "Consecutive loss lock",
      "Red-folder event blackout"
    ],
    candidateMarkets: candidateFamilies,
    institutionalPrinciples: [
      "Survive first, then scale.",
      "Do not add complexity before edge quality is repeatable.",
      "Use evidence-driven promotion gates, not discretionary overrides."
    ]
  };
}

export function buildAgenticFundReport(args: {
  research: WalkforwardResearchResult;
  config: LabConfig;
}): AgenticFundReport {
  const { research, config } = args;
  const winner = research.winner;
  const promotionGate = research.promotionGate;
  const failedChecks = promotionGate?.checks.filter((check) => !check.passed) ?? [];

  const penalty = failedChecks.reduce((sum, check) => sum + scorePenaltyByCheck(check.name), 0);
  const survivabilityScore = Math.max(0, 100 - penalty);
  const status: AgenticFundReport["status"] = survivabilityScore >= 75 && (promotionGate?.ready ?? false)
    ? "green"
    : survivabilityScore >= 55
      ? "yellow"
      : "red";

  const issues = buildIssues(failedChecks);
  const learningActions = buildLearningActions({ failedChecks, config });
  const profitableNow = (winner?.testSummary.netTotalR ?? 0) > 0;
  const deployableNow = research.deployableWinner !== null;
  const candidateFamilies = deriveCandidateFamilies(research.recommendedFamilyBudget?.rankedFamilies);
  const agentStatus = buildAgentStatus({ profitableNow, deployableNow, failedChecks });
  const evolutionPlan = buildEvolutionPlan({ reportStatus: agentStatus, candidateFamilies });
  const checklist = unique([
    "Run inspect-csv before each research pass.",
    "Require promotionGate.ready before any live escalation.",
    failedChecks.length > 0 ? "Apply suggested envPatch values in paper mode and re-run research." : "Keep current config and execute shadow run diagnostics.",
    config.accountPhase === "funded" ? "Stay on funded strict limits until two consecutive green reports." : "Promote to funded profile only after consecutive green challenge reports."
  ]);

  return {
    timestamp: new Date().toISOString(),
    phase: config.accountPhase,
    mode: config.mode,
    status,
    survivabilityScore,
    profitableNow,
    deployableNow,
    winnerProfileId: winner?.profileId ?? null,
    deployableProfileId: research.deployableWinner?.profileId ?? null,
    diagnostics: {
      testNetR: Number((winner?.testSummary.netTotalR ?? 0).toFixed(4)),
      testTrades: winner?.testSummary.totalTrades ?? 0,
      maxDrawdownR: Number((winner?.testSummary.maxDrawdownR ?? 0).toFixed(4)),
      riskOfRuinProb: Number((winner?.testSummary.tradeQuality.riskOfRuinProb ?? 0).toFixed(4)),
      scoreStability: Number((winner?.scoreStability ?? 0).toFixed(4)),
      activeFamilies: research.recommendedFamilyBudget?.activeFamilies.length ?? 0
    },
    failedChecks: failedChecks.map((check) => check.name),
    issues,
    learningActions,
    nextRunChecklist: checklist,
    agentStatus,
    evolutionPlan
  };
}
