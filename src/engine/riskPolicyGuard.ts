import { mkdir, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";

export interface RiskPolicyGuardReport {
  command: "risk-policy-guard";
  generatedAt: string;
  status: "pass" | "blocked";
  policyVersion: string;
  approvalId: string | null;
  checks: Array<{
    name: string;
    passed: boolean;
    observed: string | number | boolean;
    threshold: string | number | boolean;
    reason: string;
  }>;
  blockers: string[];
  outputPath?: string;
}

const DEFAULT_OUTPUT_PATH = ".rumbling-hedge/state/risk-policy-guard.latest.json";

function readNumber(env: NodeJS.ProcessEnv, key: string, fallback: number): number {
  const parsed = Number(env[key]);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function check(args: RiskPolicyGuardReport["checks"][number]): RiskPolicyGuardReport["checks"][number] {
  return args;
}

export function evaluateRiskPolicyGuard(args: {
  env?: NodeJS.ProcessEnv;
  now?: () => string;
} = {}): RiskPolicyGuardReport {
  const env = args.env ?? process.env;
  const generatedAt = args.now?.() ?? new Date().toISOString();
  const approvalId = env.BILL_LIVE_APPROVAL_ID?.trim() || null;
  const demoApprovalId = env.BILL_FUTURES_DEMO_APPROVAL_ID?.trim() || null;
  const policyVersion = env.BILL_RISK_POLICY_VERSION?.trim() || "starter-v1";
  const futuresLiveArmed = env.RH_LIVE_EXECUTION_ENABLED === "true";
  const futuresDemoArmed = env.BILL_ENABLE_FUTURES_DEMO_EXECUTION === "true";
  const futuresDemoOnly = env.RH_TOPSTEP_DEMO_ONLY !== "false";
  const futuresDemoApproved = futuresDemoArmed && futuresDemoOnly && Boolean(demoApprovalId);
  const predictionLiveArmed = env.BILL_PREDICTION_EXECUTION_MODE === "live" || env.BILL_PREDICTION_LIVE_EXECUTION_ENABLED === "true";
  const maxContracts = readNumber(env, "RH_MAX_CONTRACTS", 1);
  const maxTrades = readNumber(env, "RH_MAX_TRADES_PER_DAY", 1);
  const maxDailyLossR = readNumber(env, "RH_MAX_DAILY_LOSS_R", 1);
  const maxConsecutiveLosses = readNumber(env, "RH_MAX_CONSECUTIVE_LOSSES", 1);
  const maxTradesThreshold = futuresDemoApproved ? 4 : 1;
  const maxDailyLossThreshold = futuresDemoApproved ? 2 : 1;
  const maxConsecutiveLossThreshold = futuresDemoApproved ? 2 : 1;

  const checks = [
    check({
      name: "futuresLiveApproval",
      passed: !futuresLiveArmed || Boolean(approvalId) || futuresDemoApproved,
      observed: futuresLiveArmed,
      threshold: "live approval required unless approved demo-only routing is armed",
      reason: futuresLiveArmed
        ? futuresDemoApproved
          ? "Futures transport is armed only for approved Topstep demo-only routing."
          : "Futures live execution requires explicit approval id."
        : "Futures live execution is not armed."
    }),
    check({
      name: "futuresDemoReadOnly",
      passed: !futuresDemoArmed || env.RH_TOPSTEP_READ_ONLY === "true" || Boolean(approvalId) || futuresDemoApproved,
      observed: futuresDemoArmed,
      threshold: "read-only, live approval, or demo approval required when demo execution is armed",
      reason: futuresDemoArmed
        ? futuresDemoApproved
          ? "Futures demo execution is explicitly approved and demo-only account locking is required downstream."
          : "Futures demo execution must remain read-only unless explicitly approved."
        : "Futures demo execution is not armed."
    }),
    check({
      name: "predictionLiveApproval",
      passed: !predictionLiveArmed || Boolean(approvalId),
      observed: predictionLiveArmed,
      threshold: "approval required when armed",
      reason: predictionLiveArmed ? "Prediction live execution requires explicit approval id." : "Prediction live execution is not armed."
    }),
    check({
      name: "starterMaxContracts",
      passed: maxContracts <= 1,
      observed: maxContracts,
      threshold: 1,
      reason: "Starter live-readiness envelope allows at most one futures contract."
    }),
    check({
      name: "starterMaxTradesPerDay",
      passed: maxTrades <= maxTradesThreshold,
      observed: maxTrades,
      threshold: maxTradesThreshold,
      reason: futuresDemoApproved
        ? "Approved demo exploration envelope allows up to four demo trades per day."
        : "Starter live-readiness envelope allows at most one trade per day."
    }),
    check({
      name: "starterMaxDailyLossR",
      passed: maxDailyLossR <= maxDailyLossThreshold,
      observed: maxDailyLossR,
      threshold: maxDailyLossThreshold,
      reason: futuresDemoApproved
        ? "Approved demo exploration envelope allows at most 2R daily loss."
        : "Starter live-readiness envelope stops the day at 1R."
    }),
    check({
      name: "starterMaxConsecutiveLosses",
      passed: maxConsecutiveLosses <= maxConsecutiveLossThreshold,
      observed: maxConsecutiveLosses,
      threshold: maxConsecutiveLossThreshold,
      reason: futuresDemoApproved
        ? "Approved demo exploration envelope allows at most two consecutive losses."
        : "Starter live-readiness envelope stops after one loss."
    })
  ];
  const blockers = checks.filter((item) => !item.passed).map((item) => `risk-policy:${item.name}`);

  return {
    command: "risk-policy-guard",
    generatedAt,
    status: blockers.length === 0 ? "pass" : "blocked",
    policyVersion,
    approvalId,
    checks,
    blockers
  };
}

export async function writeRiskPolicyGuard(args: {
  env?: NodeJS.ProcessEnv;
  now?: () => string;
  outputPath?: string;
} = {}): Promise<RiskPolicyGuardReport> {
  const outputPath = resolve(args.outputPath ?? args.env?.BILL_RISK_POLICY_GUARD_PATH ?? DEFAULT_OUTPUT_PATH);
  const report = {
    ...evaluateRiskPolicyGuard(args),
    outputPath
  };
  await mkdir(dirname(outputPath), { recursive: true });
  await writeFile(outputPath, `${JSON.stringify(report, null, 2)}\n`, "utf8");
  return report;
}
