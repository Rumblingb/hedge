import type { LiveGateReason } from "./types.js";

/**
 * Conservative gate that decides whether live (real-money) prediction-market
 * execution is permitted. All checks must pass. Default posture is refuse.
 *
 * The gate reads env flags only — it never reaches out to external services.
 * This keeps the decision auditable and deterministic.
 */
export function evaluateLiveGate(env: NodeJS.ProcessEnv = process.env): LiveGateReason {
  const failures: string[] = [];

  if (env.BILL_PREDICTION_LIVE_EXECUTION_ENABLED !== "true") {
    failures.push("BILL_PREDICTION_LIVE_EXECUTION_ENABLED must be exactly 'true'.");
  }
  if (env.BILL_PREDICTION_LIVE_ACKNOWLEDGED !== "true") {
    failures.push("BILL_PREDICTION_LIVE_ACKNOWLEDGED must be exactly 'true' (founder dual-acknowledgement).");
  }
  const ceiling = Number.parseFloat(env.BILL_PREDICTION_LIVE_MAX_STAKE ?? "NaN");
  if (!Number.isFinite(ceiling) || ceiling <= 0) {
    failures.push("BILL_PREDICTION_LIVE_MAX_STAKE must be a positive number.");
  }
  const currency = env.BILL_PREDICTION_BANKROLL_CURRENCY;
  if (!currency || currency.length < 3) {
    failures.push("BILL_PREDICTION_BANKROLL_CURRENCY must be set (ISO 4217).");
  }
  if (env.RH_MODE === "paper" && env.BILL_PREDICTION_LIVE_EXECUTION_ENABLED === "true") {
    failures.push("RH_MODE=paper is incompatible with live prediction execution — set RH_MODE=live explicitly.");
  }

  return { ok: failures.length === 0, failures };
}
