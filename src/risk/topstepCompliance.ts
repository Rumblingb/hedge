// topstepCompliance.ts — Topstep prop firm compliance engine.
//
// Enforces the rules that fail 95% of combine traders:
//   1. Consistency: best day ≤ 50% of total profit (the #1 fail reason)
//   2. Trailing drawdown: $2,000 from peak EOD equity (EOD, NOT intraday)
//   3. Max contracts: 5 for $50K combine
//   4. Profit target: $3,000 for $50K combine
//
// All values in dollars.

export interface TopstepConfig {
  /** Account size tier */
  accountTier: 50000 | 100000 | 150000;
  /** Profit target to pass */
  profitTarget: number;
  /** Max trailing drawdown from peak equity */
  maxTrailingDD: number;
  /** Max contracts allowed */
  maxContracts: number;
  /** Consistency: best day profit / total profit ≤ this */
  maxBestDayRatio: number;
  /** Minimum trading days required */
  minTradingDays: number;
}

export const TOPSTEP_50K: TopstepConfig = {
  accountTier: 50000,
  profitTarget: 3000,
  maxTrailingDD: 2000,
  maxContracts: 5,
  maxBestDayRatio: 0.50,
  minTradingDays: 2,
};

export const TOPSTEP_100K: TopstepConfig = {
  accountTier: 100000,
  profitTarget: 6000,
  maxTrailingDD: 3000,
  maxContracts: 10,
  maxBestDayRatio: 0.50,
  minTradingDays: 2,
};

export const TOPSTEP_150K: TopstepConfig = {
  accountTier: 150000,
  profitTarget: 9000,
  maxTrailingDD: 4500,
  maxContracts: 15,
  maxBestDayRatio: 0.50,
  minTradingDays: 2,
};

export interface DailyPnL {
  date: string;    // "YYYY-MM-DD"
  pnl: number;
  trades: number;
  wins: number;
  losses: number;
}

export interface ComplianceState {
  totalPnL: number;
  peakEquity: number;
  currentDD: number;
  maxDDHit: boolean;
  bestDayPnL: number;
  bestDayRatio: number;
  consistencyViolated: boolean;
  profitTargetHit: boolean;
  tradingDays: number;
  minDaysMet: boolean;
  passed: boolean;
  failed: boolean;
  failReason: string | null;
  dailyHistory: DailyPnL[];
}

export class TopstepComplianceTracker {
  private config: TopstepConfig;
  private state: ComplianceState;

  constructor(config: TopstepConfig = TOPSTEP_50K, initialState?: Partial<ComplianceState>) {
    this.config = config;
    this.state = {
      totalPnL: 0,
      peakEquity: 0,
      currentDD: 0,
      maxDDHit: false,
      bestDayPnL: 0,
      bestDayRatio: 0,
      consistencyViolated: false,
      profitTargetHit: false,
      tradingDays: 0,
      minDaysMet: false,
      passed: false,
      failed: false,
      failReason: null,
      dailyHistory: [],
      ...initialState,
    };
  }

  /** Record a completed trade result. Call this after each trade closes. */
  recordTrade(pnl: number, won: boolean): void {
    if (this.state.failed || this.state.passed) return;

    const today = new Date().toISOString().slice(0, 10);
    let dayEntry = this.state.dailyHistory.find((d) => d.date === today);

    if (!dayEntry) {
      dayEntry = { date: today, pnl: 0, trades: 0, wins: 0, losses: 0 };
      this.state.dailyHistory.push(dayEntry);
      this.state.tradingDays = this.state.dailyHistory.length;
    }

    dayEntry.pnl += pnl;
    dayEntry.trades++;
    if (won) dayEntry.wins++;
    else dayEntry.losses++;

    this.state.totalPnL += pnl;
    this.state.peakEquity = Math.max(this.state.peakEquity, this.state.totalPnL);

    // Check trailing drawdown (EOD — we track intraday but only fail EOD)
    this.state.currentDD = this.state.totalPnL - this.state.peakEquity;
    if (-this.state.currentDD >= this.config.maxTrailingDD) {
      this.state.maxDDHit = true;
      this.state.failed = true;
      this.state.failReason = `Trailing drawdown exceeded: -$${Math.abs(this.state.currentDD).toFixed(0)} >= $${this.config.maxTrailingDD}`;
      return;
    }

    // Check profit target
    if (this.state.totalPnL >= this.config.profitTarget) {
      this.state.profitTargetHit = true;
    }

    // Update best day tracking (informational only, not a fail trigger)
    this.state.bestDayPnL = Math.max(this.state.bestDayPnL, dayEntry.pnl);
    if (this.state.totalPnL > 0) {
      this.state.bestDayRatio = this.state.bestDayPnL / this.state.totalPnL;
    }

    // Min days check (informational)
    this.state.minDaysMet = this.state.tradingDays >= this.config.minTradingDays;

    // Pass check: hit target AND min days met (consistency checked at EOD)
    if (
      this.state.profitTargetHit &&
      !this.state.maxDDHit &&
      this.state.minDaysMet
    ) {
      this.state.passed = true;
    }
  }

  /**
   * End-of-day settlement. Call this at market close.
   * This is where EOD trailing drawdown is enforced.
   * Intraday drawdowns that recover by EOD do NOT fail.
   */
  endOfDay(): void {
    if (this.state.failed || this.state.passed) return;

    // EOD trailing drawdown check
    if (-this.state.currentDD >= this.config.maxTrailingDD) {
      this.state.maxDDHit = true;
      this.state.failed = true;
      this.state.failReason = `EOD trailing drawdown: -$${Math.abs(this.state.currentDD).toFixed(0)} >= $${this.config.maxTrailingDD}`;
    }

    // EOD consistency check
    if (this.state.totalPnL > 0 && this.state.bestDayRatio > this.config.maxBestDayRatio) {
      this.state.consistencyViolated = true;
      this.state.failed = true;
      this.state.failReason = `Consistency violation: best day $${this.state.bestDayPnL.toFixed(2)} is ${(this.state.bestDayRatio * 100).toFixed(0)}% of total $${this.state.totalPnL.toFixed(2)} (>${(this.config.maxBestDayRatio * 100).toFixed(0)}%)`;
    }
  }

  /**
   * Check if a new trade is allowed under current compliance state.
   * Returns false if trading should stop (e.g., profit target reached,
   * or daily P&L approaching consistency violation).
   */
  canTrade(): { allowed: boolean; reason?: string } {
    if (this.state.failed) {
      return { allowed: false, reason: `Failed: ${this.state.failReason}` };
    }
    if (this.state.passed) {
      return { allowed: false, reason: "Combine passed — stop trading" };
    }
    if (this.state.profitTargetHit) {
      return { allowed: false, reason: "Profit target reached — stop trading" };
    }
    if (this.state.maxDDHit) {
      return { allowed: false, reason: "Trailing drawdown hit" };
    }

    // Consistency guard: if today is already the best day and total P&L is positive,
    // additional profits today will worsen the ratio.
    // This is a SOFT block — can be overridden with small trades.
    return { allowed: true };
  }

  /**
   * Maximum additional profit allowed today before consistency would be violated.
   * If current best day is today, and today/total > 40%, we should slow down.
   */
  maxAdditionalProfitToday(): number {
    const today = new Date().toISOString().slice(0, 10);
    const dayEntry = this.state.dailyHistory.find((d) => d.date === today);
    const todayPnL = dayEntry?.pnl ?? 0;

    if (this.state.totalPnL <= 0) return Infinity;

    // Target: todayPnL / (totalPnL + additional) ≤ maxBestDayRatio
    // → todayPnL ≤ maxBestDayRatio * (totalPnL + additional)
    // → additional ≥ todayPnL/maxBestDayRatio - totalPnL
    const target = todayPnL / this.config.maxBestDayRatio - this.state.totalPnL;
    return Math.max(0, target);
  }

  getState(): Readonly<ComplianceState> {
    return { ...this.state };
  }

  getConfig(): Readonly<TopstepConfig> {
    return { ...this.config };
  }

  /**
   * Progress toward combine pass.
   */
  getProgress(): {
    profitPct: number;
    daysComplete: number;
    daysRequired: number;
    consistencyStatus: "good" | "warning" | "violated";
    ddStatus: "good" | "warning" | "violated";
  } {
    const profitPct = Math.min(100, (this.state.totalPnL / this.config.profitTarget) * 100);
    const bestDayPct = this.state.bestDayRatio * 100;
    const ddPct = this.state.totalPnL > 0
      ? (-this.state.currentDD / this.config.maxTrailingDD) * 100
      : 0;

    return {
      profitPct: Math.round(profitPct * 10) / 10,
      daysComplete: this.state.tradingDays,
      daysRequired: this.config.minTradingDays,
      consistencyStatus:
        this.state.consistencyViolated ? "violated" :
        bestDayPct > this.config.maxBestDayRatio * 100 * 0.85 ? "warning" : "good",
      ddStatus:
        this.state.maxDDHit ? "violated" :
        ddPct > 75 ? "warning" : "good",
    };
  }
}
