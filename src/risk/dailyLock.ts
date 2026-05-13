// dailyLock.ts — Daily trade lock automation for NQ challenge/funded phases.
//
// Enforces hard daily gates that supersede generic guardrails:
//   1. Daily profit lock — stop when daily P&L hits target
//   2. Daily loss lock — stop when daily loss hits threshold
//   3. Max trades/day — hard cap from phase config
//   4. Stop after N consecutive losses
//   5. No trade after profit target reached (challenge pass)
//   6. No trade during high-impact news windows (8:30-8:35, 9:00-9:05, 13:00-13:05 CT)

import type { PhaseRiskProfile, NQChallengePhase } from "./challengePhaseController.js";
import { PHASE_RISK_PROFILES } from "./challengePhaseController.js";

export interface DailyLockState {
  date: string;            // "YYYY-MM-DD" Chicago
  dailyPnL: number;
  tradeCount: number;
  consecutiveLosses: number;
  lastTradeResult: "win" | "loss" | null;
  profitLocked: boolean;   // true = hit daily profit target, stop trading
  lossLocked: boolean;     // true = hit daily loss limit, stop trading
  maxTradesReached: boolean;
  consecutiveLossLock: boolean;
  combinedLocked: boolean; // true = combine passed, stop trading
  lockReason: string | null;
}

export interface DailyTradeRecord {
  timestamp: string;
  pnl: number;
  won: boolean;
  setupLabel?: string;
}

// High-impact news windows in Chicago time (CT)
// These are when major economic data drops that can wreck NQ positions
const NEWS_BLACKOUT_WINDOWS_CT: Array<{ start: string; end: string; label: string }> = [
  { start: "08:30", end: "08:35", label: "Econ data release (8:30 ET)" },
  { start: "09:00", end: "09:05", label: "Market open / ISM" },
  { start: "13:00", end: "13:05", label: "Bond market close / FOMC minutes (1pm ET)" },
];

export function isInNewsBlackout(ctTime: string): { blocked: boolean; label?: string } {
  const timePart = ctTime.slice(0, 5); // "HH:MM"
  for (const window of NEWS_BLACKOUT_WINDOWS_CT) {
    if (timePart >= window.start && timePart <= window.end) {
      return { blocked: true, label: window.label };
    }
  }
  return { blocked: false };
}

export function chicagoToday(): string {
  // Chicago is UTC-6 (CST) or UTC-5 (CDT). Use simple UTC offset approximation.
  // During US daylight time (Mar-Nov): UTC-5. Otherwise: UTC-6.
  const now = new Date();
  const month = now.getUTCMonth(); // 0-indexed
  const isDST = month >= 2 && month <= 10; // rough: Mar-Nov
  const offset = isDST ? 5 : 6;
  const chicago = new Date(now.getTime() - offset * 3600000);
  return chicago.toISOString().slice(0, 10);
}

export function chicagoTime(): string {
  const now = new Date();
  const month = now.getUTCMonth();
  const isDST = month >= 2 && month <= 10;
  const offset = isDST ? 5 : 6;
  const chicago = new Date(now.getTime() - offset * 3600000);
  return chicago.toISOString().slice(11, 19); // "HH:MM:SS"
}

export function createDailyLockState(date?: string): DailyLockState {
  return {
    date: date ?? chicagoToday(),
    dailyPnL: 0,
    tradeCount: 0,
    consecutiveLosses: 0,
    lastTradeResult: null,
    profitLocked: false,
    lossLocked: false,
    maxTradesReached: false,
    consecutiveLossLock: false,
    combinedLocked: false,
    lockReason: null,
  };
}

export interface DailyLockDecision {
  allowed: boolean;
  reason?: string;
  /** If profit-locked, how much profit has been made */
  dailyPnL?: number;
  /** Remaining trades allowed */
  tradesRemaining?: number;
}

export class DailyLock {
  private state: DailyLockState;
  private tradeHistory: DailyTradeRecord[] = [];

  constructor(initialState?: Partial<DailyLockState>) {
    const today = chicagoToday();
    if (initialState && initialState.date !== today) {
      // Stale state from a different day — reset
      this.state = createDailyLockState(today);
    } else {
      this.state = { ...createDailyLockState(today), ...initialState };
    }
  }

  /** Main gate: check if a new trade is allowed given current lock state and phase */
  canTrade(phase: NQChallengePhase): DailyLockDecision {
    const profile = PHASE_RISK_PROFILES[phase];
    const today = chicagoToday();

    // Reset if new day
    if (this.state.date !== today) {
      this.state = createDailyLockState(today);
    }

    // Combined-locked: challenge passed, no more trading
    if (this.state.combinedLocked) {
      return { allowed: false, reason: "Challenge passed — stop trading", dailyPnL: this.state.dailyPnL };
    }

    // Profit lock
    if (this.state.profitLocked) {
      return { allowed: false, reason: `Daily profit lock hit ($${this.state.dailyPnL.toFixed(0)} >= $${profile.dailyProfitLock})`, dailyPnL: this.state.dailyPnL };
    }

    // Loss lock
    if (this.state.lossLocked) {
      return { allowed: false, reason: `Daily loss lock hit (-$${Math.abs(this.state.dailyPnL).toFixed(0)} >= $${profile.dailyLossLock})`, dailyPnL: this.state.dailyPnL };
    }

    // Max trades
    if (this.state.tradeCount >= profile.maxTradesPerDay) {
      return { allowed: false, reason: `Max trades today (${this.state.tradeCount}/${profile.maxTradesPerDay})`, dailyPnL: this.state.dailyPnL, tradesRemaining: 0 };
    }

    // Consecutive loss lock
    if (this.state.consecutiveLosses >= profile.maxConsecutiveLosses) {
      return { allowed: false, reason: `${this.state.consecutiveLosses} consecutive losses — stop for today`, dailyPnL: this.state.dailyPnL };
    }

    // News blackout check
    const ctTime = chicagoTime();
    const blackout = isInNewsBlackout(ctTime);
    if (blackout.blocked) {
      return { allowed: false, reason: `News blackout window: ${blackout.label}`, dailyPnL: this.state.dailyPnL };
    }

    // Combined (all gates clear)
    return {
      allowed: true,
      dailyPnL: this.state.dailyPnL,
      tradesRemaining: profile.maxTradesPerDay - this.state.tradeCount,
    };
  }

  /** Record a completed trade and update lock state */
  recordTrade(pnl: number, won: boolean, setupLabel?: string): void {
    const today = chicagoToday();
    if (this.state.date !== today) {
      this.state = createDailyLockState(today);
      this.tradeHistory = [];
    }

    const profile = PHASE_RISK_PROFILES["challenge-demo"]; // default if phase unknown
    this.state.dailyPnL += pnl;
    this.state.tradeCount += 1;
    this.state.lastTradeResult = won ? "win" : "loss";
    this.state.consecutiveLosses = won ? 0 : this.state.consecutiveLosses + 1;

    // Check profit lock
    if (this.state.dailyPnL >= profile.dailyProfitLock) {
      this.state.profitLocked = true;
      this.state.lockReason = `Daily profit target reached: $${this.state.dailyPnL.toFixed(0)}`;
    }

    // Check loss lock
    if (this.state.dailyPnL <= -profile.dailyLossLock) {
      this.state.lossLocked = true;
      this.state.lockReason = `Daily loss limit hit: -$${Math.abs(this.state.dailyPnL).toFixed(0)}`;
    }

    // Check max trades
    if (this.state.tradeCount >= profile.maxTradesPerDay) {
      this.state.maxTradesReached = true;
      if (!this.state.lockReason) {
        this.state.lockReason = `Max trades reached: ${this.state.tradeCount}`;
      }
    }

    // Check consecutive losses
    if (this.state.consecutiveLosses >= profile.maxConsecutiveLosses) {
      this.state.consecutiveLossLock = true;
      if (!this.state.lockReason) {
        this.state.lockReason = `${this.state.consecutiveLosses} consecutive losses`;
      }
    }

    this.tradeHistory.push({
      timestamp: new Date().toISOString(),
      pnl,
      won,
      setupLabel,
    });
  }

  /** Reserve one submitted/pending trade without pretending it won or lost. */
  reserveSubmittedTrade(setupLabel?: string): void {
    const today = chicagoToday();
    if (this.state.date !== today) {
      this.state = createDailyLockState(today);
      this.tradeHistory = [];
    }

    const profile = PHASE_RISK_PROFILES["challenge-demo"];
    this.state.tradeCount += 1;
    if (this.state.tradeCount >= profile.maxTradesPerDay) {
      this.state.maxTradesReached = true;
      if (!this.state.lockReason) {
        this.state.lockReason = `Max trades reached: ${this.state.tradeCount}`;
      }
    }

    this.tradeHistory.push({
      timestamp: new Date().toISOString(),
      pnl: 0,
      won: false,
      setupLabel: setupLabel ? `${setupLabel}:pending-submit` : "pending-submit",
    });
  }

  /** Lock combined (challenge passed) */
  lockCombined(reason: string): void {
    this.state.combinedLocked = true;
    this.state.lockReason = reason;
  }

  /** Get current state snapshot */
  getState(): Readonly<DailyLockState> {
    return { ...this.state };
  }

  /** Get today's trade history */
  getTradeHistory(): Readonly<DailyTradeRecord[]> {
    return [...this.tradeHistory];
  }

  /** One-line status for EOD/morning report */
  getStatusLine(): string {
    const locks: string[] = [];
    if (this.state.profitLocked) locks.push("PROFIT-LOCK");
    if (this.state.lossLocked) locks.push("LOSS-LOCK");
    if (this.state.maxTradesReached) locks.push("MAX-TRADES");
    if (this.state.consecutiveLossLock) locks.push("CONSEC-LOSS");
    if (this.state.combinedLocked) locks.push("COMBINED-PASSED");

    const lockStatus = locks.length > 0 ? locks.join("+") : "OPEN";
    const sign = this.state.dailyPnL >= 0 ? "+" : "";
    return [
      `PnL:${sign}$${this.state.dailyPnL.toFixed(0)}`,
      `${this.state.tradeCount}t`,
      `${this.state.consecutiveLosses}L`,
      lockStatus,
    ].join(" ");
  }
}
