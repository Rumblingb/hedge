// challengePhaseController.ts — NQ prop-firm challenge state machine.
//
// Five phases with automatic risk-mode switching:
//   research        → no real money, strategy development
//   challenge-demo  → demo account, higher risk allowed (1 NQ, 3 trades/day, $1,200 lock)
//   challenge-live  → real 50K combine, MNQ-first risk
//   funded-payout-defense → funded account, payout-protection mode (MNQ, conservative)
//   paused          → emergency stop, no trading
//
// Each phase changes: sizing, max loss, trade count, profit lock automatically.

import type { GuardrailConfig } from "../domain.js";

export type NQChallengePhase =
  | "research"
  | "challenge-demo"
  | "challenge-live"
  | "funded-payout-defense"
  | "paused";

export interface PhaseRiskProfile {
  /** Max NQ contracts (1 for challenge, 0 = MNQ only) */
  maxNqContracts: number;
  /** Max MNQ contracts (for funded mode) */
  maxMnqContracts: number;
  /** Max trades allowed per day */
  maxTradesPerDay: number;
  /** Daily profit lock — stop trading when daily P&L reaches this */
  dailyProfitLock: number;
  /** Daily loss lock — stop trading when daily loss reaches this */
  dailyLossLock: number;
  /** Max consecutive losses before lockout */
  maxConsecutiveLosses: number;
  /** Minimum R:R required */
  minRr: number;
  /** Max hold time in minutes */
  maxHoldMinutes: number;
  /** Stop management: breakeven trigger in R */
  breakEvenTriggerR: number;
  /** Stop management: runner trigger in R */
  runnerTriggerR: number;
  /** Whether demo fallback signals are allowed */
  allowDemoFallback: boolean;
  /** Whether to enforce setup journal */
  requireSetupLabel: boolean;
}

export const PHASE_RISK_PROFILES: Record<NQChallengePhase, PhaseRiskProfile> = {
  research: {
    maxNqContracts: 0,
    maxMnqContracts: 1,
    maxTradesPerDay: 10,
    dailyProfitLock: Infinity,
    dailyLossLock: 100,
    maxConsecutiveLosses: 5,
    minRr: 1.5,
    maxHoldMinutes: 120,
    breakEvenTriggerR: 1.0,
    runnerTriggerR: 1.8,
    allowDemoFallback: true,
    requireSetupLabel: false,
  },

  "challenge-demo": {
    // Higher risk allowed — this is the aggression phase
    maxNqContracts: 1,
    maxMnqContracts: 0,
    maxTradesPerDay: 3,
    dailyProfitLock: 1200,     // ~3 good NQ trades
    dailyLossLock: 450,        // ~6-7 NQ points = $120-$140 risk × 3
    maxConsecutiveLosses: 2,
    minRr: 2.0,                // 2R minimum for challenge
    maxHoldMinutes: 30,
    breakEvenTriggerR: 1.0,
    runnerTriggerR: 1.8,
    allowDemoFallback: false,
    requireSetupLabel: true,
  },

  "challenge-live": {
    // 50K live is MNQ-first; one NQ is escalation-only after separate proof.
    maxNqContracts: 0,
    maxMnqContracts: 8,
    maxTradesPerDay: 3,
    dailyProfitLock: 900,
    dailyLossLock: 350,
    maxConsecutiveLosses: 2,
    minRr: 2.0,
    maxHoldMinutes: 30,
    breakEvenTriggerR: 1.0,
    runnerTriggerR: 1.8,
    allowDemoFallback: false,
    requireSetupLabel: true,
  },

  "funded-payout-defense": {
    // Conservative — payout protection mode
    maxNqContracts: 0,
    maxMnqContracts: 5,        // MNQ only, sized to clear $150+ days after costs
    maxTradesPerDay: 3,
    dailyProfitLock: 300,
    dailyLossLock: 180,
    maxConsecutiveLosses: 2,
    minRr: 1.8,                // Lower RR but more consistent
    maxHoldMinutes: 60,
    breakEvenTriggerR: 0.8,
    runnerTriggerR: 1.5,
    allowDemoFallback: false,
    requireSetupLabel: true,
  },

  paused: {
    maxNqContracts: 0,
    maxMnqContracts: 0,
    maxTradesPerDay: 0,
    dailyProfitLock: 0,
    dailyLossLock: 0,
    maxConsecutiveLosses: 0,
    minRr: 99,
    maxHoldMinutes: 0,
    breakEvenTriggerR: 99,
    runnerTriggerR: 99,
    allowDemoFallback: false,
    requireSetupLabel: false,
  },
};

export const VALID_PHASE_TRANSITIONS: Record<NQChallengePhase, NQChallengePhase[]> = {
  research: ["challenge-demo", "paused"],
  "challenge-demo": ["challenge-live", "research", "paused"],
  "challenge-live": ["funded-payout-defense", "challenge-demo", "paused"],
  "funded-payout-defense": ["paused"], // funded stays funded; pause only
  paused: ["research", "challenge-demo", "challenge-live", "funded-payout-defense"],
};

export interface PhaseTransition {
  from: NQChallengePhase;
  to: NQChallengePhase;
  reason: string;
  timestamp: string;
  /** Optional condition that must be met for auto-transition */
  autoCondition?: () => boolean;
}

export interface PhaseControllerState {
  currentPhase: NQChallengePhase;
  phaseSince: string;
  transitionHistory: PhaseTransition[];
}

export class NQChallengePhaseController {
  private state: PhaseControllerState;

  constructor(initialPhase: NQChallengePhase = "research") {
    const now = new Date().toISOString();
    this.state = {
      currentPhase: initialPhase,
      phaseSince: now,
      transitionHistory: [{
        from: initialPhase,
        to: initialPhase,
        reason: "Initial phase set",
        timestamp: now,
      }],
    };
  }

  /** Get the risk profile for the current phase */
  getRiskProfile(): PhaseRiskProfile {
    return PHASE_RISK_PROFILES[this.state.currentPhase];
  }

  /** Get current phase */
  getPhase(): NQChallengePhase {
    return this.state.currentPhase;
  }

  /** Check if a phase transition is valid */
  canTransition(to: NQChallengePhase): boolean {
    return VALID_PHASE_TRANSITIONS[this.state.currentPhase].includes(to);
  }

  /** Attempt a phase transition. Returns false if invalid. */
  transition(to: NQChallengePhase, reason: string): boolean {
    if (!this.canTransition(to)) {
      return false;
    }

    const transition: PhaseTransition = {
      from: this.state.currentPhase,
      to,
      reason,
      timestamp: new Date().toISOString(),
    };

    this.state.currentPhase = to;
    this.state.phaseSince = transition.timestamp;
    this.state.transitionHistory.push(transition);

    return true;
  }

  /** Auto-transition if condition is met. Used for challenge-demo → challenge-live. */
  maybeAutoTransition(
    to: NQChallengePhase,
    reason: string,
    condition: () => boolean,
  ): boolean {
    if (!condition()) return false;
    return this.transition(to, reason);
  }

  /** Build guardrail config from the current phase's risk profile */
  buildGuardrailOverrides(): Partial<GuardrailConfig> {
    const profile = this.getRiskProfile();
    return {
      maxContracts: profile.maxNqContracts + profile.maxMnqContracts,
      maxTradesPerDay: profile.maxTradesPerDay,
      maxDailyLossR: profile.dailyLossLock / 400, // approximate R conversion for NQ
      maxConsecutiveLosses: profile.maxConsecutiveLosses,
      minRr: profile.minRr,
      maxHoldMinutes: profile.maxHoldMinutes,
    };
  }

  /** One-line status for EOD/morning report */
  getStatusLine(): string {
    const p = this.getRiskProfile();
    const days = Math.floor(
      (Date.now() - new Date(this.state.phaseSince).getTime()) / 86400000
    );
    return [
      `NQ:${this.state.currentPhase}`,
      `d${days}`,
      `max${p.maxTradesPerDay}t/d`,
      `lock+$${p.dailyProfitLock}`,
      `loss-$${p.dailyLossLock}`,
      `nq${p.maxNqContracts}`,
      `mnq${p.maxMnqContracts}`,
    ].join(" ");
  }

  getState(): Readonly<PhaseControllerState> {
    return { ...this.state, transitionHistory: [...this.state.transitionHistory] };
  }
}
