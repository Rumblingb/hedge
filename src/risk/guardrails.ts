import type { GuardrailConfig, NewsScore, RiskState, StrategySignal } from "../domain.js";
import { getMarketSessionWindow } from "../utils/sessions.js";
import { isAfterCtTime, isWithinCtWindow, minutesFromCtTime } from "../utils/time.js";

export const HARD_GUARDRAIL_BOUNDS = Object.freeze({
  minRr: 2.5,
  maxContracts: 2,
  maxTradesPerDay: 3,
  maxHoldMinutes: 30,
  maxDailyLossR: 2,
  maxConsecutiveLosses: 2
});

export interface GuardrailDecision {
  allowed: boolean;
  reasons: string[];
}

export function calculateRr(entry: number, stop: number, target: number, side: "long" | "short"): number {
  const risk = side === "long" ? entry - stop : stop - entry;
  const reward = side === "long" ? target - entry : entry - target;
  if (risk <= 0 || reward <= 0) {
    return 0;
  }
  return reward / risk;
}

export function createInitialRiskState(): RiskState {
  return {
    tradeCount: 0,
    realizedR: 0,
    consecutiveLosses: 0
  };
}

export function applyTradeToRiskState(state: RiskState, rMultiple: number): RiskState {
  return {
    tradeCount: state.tradeCount + 1,
    realizedR: state.realizedR + rMultiple,
    consecutiveLosses: rMultiple < 0 ? state.consecutiveLosses + 1 : 0
  };
}

export function evaluateSignalGuardrails(args: {
  signal: StrategySignal;
  timestamp: string;
  guardrails: GuardrailConfig;
  riskState: RiskState;
  news?: NewsScore;
}): GuardrailDecision {
  const { signal, timestamp, guardrails, riskState, news } = args;
  const reasons: string[] = [];
  const marketSession = getMarketSessionWindow(signal.symbol, guardrails.sessionStartCt);
  const effectiveLastEntry = marketSession.endCt && marketSession.endCt < guardrails.lastEntryCt
    ? marketSession.endCt
    : guardrails.lastEntryCt;
  const blockedWindow = marketSession.blockedWindows.find((window) =>
    isWithinCtWindow(timestamp, window.startCt, window.endCt)
  );
  const blockedWindowCrossing = marketSession.blockedWindows.find((window) => {
    const minutesUntilBlocked = minutesFromCtTime(timestamp, window.startCt);
    return minutesUntilBlocked < 0 && (minutesUntilBlocked + signal.maxHoldMinutes) > 0;
  });

  if (!guardrails.allowedSymbols.includes(signal.symbol)) {
    reasons.push(`symbol ${signal.symbol} is not allowed`);
  }

  if (signal.contracts > Math.min(guardrails.maxContracts, HARD_GUARDRAIL_BOUNDS.maxContracts)) {
    reasons.push("contracts exceed hard limit");
  }

  if (!isWithinCtWindow(timestamp, marketSession.startCt, effectiveLastEntry)) {
    reasons.push("entry outside allowed CT session window");
  }

  if (blockedWindow) {
    reasons.push(`entry inside blocked window (${blockedWindow.reason})`);
  }

  if (isAfterCtTime(timestamp, guardrails.flatByCt)) {
    reasons.push("entry arrives after flat cutoff");
  }

  if ((minutesFromCtTime(timestamp, guardrails.flatByCt) + signal.maxHoldMinutes) > 0) {
    reasons.push("max hold crosses flat cutoff");
  }

  if (blockedWindowCrossing) {
    reasons.push(`max hold crosses blocked window (${blockedWindowCrossing.reason})`);
  }

  if (signal.rr < Math.max(guardrails.minRr, HARD_GUARDRAIL_BOUNDS.minRr)) {
    reasons.push("rr below minimum");
  }

  if (signal.maxHoldMinutes > Math.min(guardrails.maxHoldMinutes, HARD_GUARDRAIL_BOUNDS.maxHoldMinutes)) {
    reasons.push("hold time exceeds limit");
  }

  if (riskState.tradeCount >= Math.min(guardrails.maxTradesPerDay, HARD_GUARDRAIL_BOUNDS.maxTradesPerDay)) {
    reasons.push("daily trade count exhausted");
  }

  if (riskState.realizedR <= -Math.min(guardrails.maxDailyLossR, HARD_GUARDRAIL_BOUNDS.maxDailyLossR)) {
    reasons.push("daily loss lock active");
  }

  if (riskState.consecutiveLosses >= Math.min(guardrails.maxConsecutiveLosses, HARD_GUARDRAIL_BOUNDS.maxConsecutiveLosses)) {
    reasons.push("consecutive loss lock active");
  }

  if (news && news.impact === "high") {
    if (news.direction !== "flat" && news.direction !== signal.side) {
      reasons.push("high-impact news disagrees with trade direction");
    }

    if (news.probability < guardrails.newsProbabilityThreshold) {
      reasons.push("high-impact news confidence below threshold");
    }
  }

  return {
    allowed: reasons.length === 0,
    reasons
  };
}
