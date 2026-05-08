// payoutLedger.ts — Funded payout-window accounting and eligibility tracker.
//
// Tracks everything needed to pass a payout review:
//   - Payout-window net profit (rolling 5-day window for Topstep standard path)
//   - Largest winning day (must be ≤50% or ≤40% of total depending on tier)
//   - Largest day percentage (consistency check)
//   - $150+ days count (standard path minimum)
//   - 40% constraint (consistency path)
//   - Days since last payout
//   - Whether a new trade would wreck payout consistency
//
// Topstep payout rules (standard path for $50K):
//   - 5 winning days of $150+
//   - Best day ≤ 50% of total profit
//   - No payout in first 5 trading days
//   - Max payout: $5,000 (standard), $2,000 (consistency)
//
// Consistency path:
//   - Best day ≤ 40% of total profit
//   - 10 winning days of $100+
//   - Max payout: $2,000

export type PayoutPath = "standard" | "consistency";

export interface PayoutDayRecord {
  date: string;        // "YYYY-MM-DD"
  netPnL: number;
  trades: number;
  wins: number;
  losses: number;
  isWinningDay: boolean; // ≥$150 for standard, ≥$100 for consistency
}

export interface PayoutLedgerState {
  /** Which payout path we're targeting */
  path: PayoutPath;
  /** Account tier */
  accountTier: 50000 | 100000 | 150000;
  /** Total P&L since last payout */
  windowNetPnL: number;
  /** Largest single-day P&L in window */
  largestWinningDay: number;
  /** Largest day as percentage of total */
  largestDayPct: number;
  /** Number of qualifying winning days ($150+ or $100+) */
  qualifyingDays: number;
  /** Minimum qualifying days required */
  minQualifyingDays: number;
  /** Days since last payout */
  daysSincePayout: number;
  /** Whether eligible for payout right now */
  eligible: boolean;
  /** If not eligible, why */
  ineligibleReason: string | null;
  /** Whether a new trade of given P&L today would break consistency */
  wouldBreakConsistency: boolean;
  /** Maximum additional profit today before consistency breaks */
  maxAdditionalProfitToday: number;
  /** Daily history */
  dailyHistory: PayoutDayRecord[];
  /** Best day ratio threshold (0.50 = 50%) */
  bestDayRatioThreshold: number;
}

export interface PayoutLedgerConfig {
  accountTier: 50000 | 100000 | 150000;
  path: PayoutPath;
}

export const STANDARD_PATH_50K = {
  minQualifyingDays: 5,
  minWinningDayAmount: 150,
  bestDayRatioThreshold: 0.50,
  maxPayout: 5000,
};

export const CONSISTENCY_PATH_50K = {
  minQualifyingDays: 10,
  minWinningDayAmount: 100,
  bestDayRatioThreshold: 0.40,
  maxPayout: 2000,
};

export function getPayoutPathConfig(path: PayoutPath) {
  return path === "standard" ? STANDARD_PATH_50K : CONSISTENCY_PATH_50K;
}

export function createPayoutLedgerState(config: PayoutLedgerConfig): PayoutLedgerState {
  const pathConfig = getPayoutPathConfig(config.path);
  return {
    path: config.path,
    accountTier: config.accountTier,
    windowNetPnL: 0,
    largestWinningDay: 0,
    largestDayPct: 0,
    qualifyingDays: 0,
    minQualifyingDays: pathConfig.minQualifyingDays,
    daysSincePayout: 0,
    eligible: false,
    ineligibleReason: "No trading days yet",
    wouldBreakConsistency: false,
    maxAdditionalProfitToday: Infinity,
    dailyHistory: [],
    bestDayRatioThreshold: pathConfig.bestDayRatioThreshold,
  };
}

export class PayoutLedger {
  private state: PayoutLedgerState;
  private config: PayoutLedgerConfig;

  constructor(config: PayoutLedgerConfig, initialState?: Partial<PayoutLedgerState>) {
    this.config = config;
    this.state = { ...createPayoutLedgerState(config), ...initialState };
  }

  /** Record end-of-day P&L and recalculate payout eligibility */
  recordDay(date: string, pnl: number, trades: number, wins: number, losses: number): void {
    const pathConfig = getPayoutPathConfig(this.config.path);

    // Check if this date already exists (update) or is new
    const existing = this.state.dailyHistory.findIndex(d => d.date === date);
    const record: PayoutDayRecord = {
      date,
      netPnL: pnl,
      trades,
      wins,
      losses,
      isWinningDay: pnl >= pathConfig.minWinningDayAmount,
    };

    if (existing >= 0) {
      this.state.dailyHistory[existing] = record;
    } else {
      this.state.dailyHistory.push(record);
    }

    // Recalculate all derived state
    this.recalculate();
  }

  /** Before trading: check if a hypothetical trade would break consistency */
  wouldBreakConsistency(todayPnL: number, hypotheticalNewPnL: number): boolean {
    const pathConfig = getPayoutPathConfig(this.config.path);
    const projectedTotal = this.state.windowNetPnL + hypotheticalNewPnL;
    const projectedToday = todayPnL + hypotheticalNewPnL;

    if (projectedTotal <= 0) return false;

    // Check if today would become the largest day and violate ratio
    const projectedLargestDay = Math.max(this.state.largestWinningDay, projectedToday);
    const projectedRatio = projectedLargestDay / projectedTotal;

    return projectedRatio > pathConfig.bestDayRatioThreshold;
  }

  /** Maximum additional profit today before consistency breaks */
  calcMaxAdditionalProfit(todayPnL: number): number {
    const pathConfig = getPayoutPathConfig(this.config.path);
    if (this.state.windowNetPnL <= 0 && todayPnL <= 0) return Infinity;

    // Solve: (todayPnL + x) / (totalPnL + x) ≤ threshold
    // → todayPnL + x ≤ threshold × (totalPnL + x)
    // → todayPnL + x ≤ threshold × totalPnL + threshold × x
    // → x - threshold × x ≤ threshold × totalPnL - todayPnL
    // → x × (1 - threshold) ≤ threshold × totalPnL - todayPnL
    // → x ≤ (threshold × totalPnL - todayPnL) / (1 - threshold)

    const threshold = pathConfig.bestDayRatioThreshold;
    const total = this.state.windowNetPnL;
    const numerator = threshold * total - todayPnL;
    const denominator = 1 - threshold;

    if (denominator <= 0) return 0;
    return Math.max(0, numerator / denominator);
  }

  private recalculate(): void {
    const pathConfig = getPayoutPathConfig(this.config.path);

    // Sum daily P&L (last N days in window)
    const sorted = [...this.state.dailyHistory].sort(
      (a, b) => b.date.localeCompare(a.date)
    );

    this.state.windowNetPnL = this.state.dailyHistory.reduce((sum, d) => sum + d.netPnL, 0);
    this.state.largestWinningDay = Math.max(0, ...this.state.dailyHistory.map(d => d.netPnL));
    this.state.largestDayPct = this.state.windowNetPnL > 0
      ? this.state.largestWinningDay / this.state.windowNetPnL
      : 0;
    this.state.qualifyingDays = this.state.dailyHistory.filter(d => d.isWinningDay).length;

    if (sorted.length > 0) {
      const lastDate = new Date(sorted[0].date);
      const now = new Date();
      this.state.daysSincePayout = Math.floor(
        (now.getTime() - lastDate.getTime()) / 86400000
      );
    }

    // Eligibility checks
    const checks: string[] = [];

    if (this.state.windowNetPnL <= 0) {
      checks.push("Net P&L is not positive");
    }
    if (this.state.qualifyingDays < this.state.minQualifyingDays) {
      checks.push(`Need ${this.state.minQualifyingDays - this.state.qualifyingDays} more qualifying days (${this.state.qualifyingDays}/${this.state.minQualifyingDays})`);
    }
    if (this.state.largestDayPct > pathConfig.bestDayRatioThreshold) {
      checks.push(`Best day ${(this.state.largestDayPct * 100).toFixed(0)}% exceeds ${(pathConfig.bestDayRatioThreshold * 100).toFixed(0)}% threshold`);
    }
    if (this.state.daysSincePayout < 5) {
      checks.push("Minimum 5 days since last payout not met");
    }

    this.state.eligible = checks.length === 0;
    this.state.ineligibleReason = checks.length > 0 ? checks.join("; ") : null;
  }

  /** Check before trade: would this trade break consistency? */
  checkPreTrade(todayPnL: number, hypotheticalTradePnL: number): { safe: boolean; reason?: string } {
    if (this.wouldBreakConsistency(todayPnL, hypotheticalTradePnL)) {
      const pathConfig = getPayoutPathConfig(this.config.path);
      const projected = todayPnL + hypotheticalTradePnL;
      const projectedTotal = this.state.windowNetPnL + hypotheticalTradePnL;
      const projectedRatio = ((projected / projectedTotal) * 100);
      return {
        safe: false,
        reason: `Trade would make today ${projectedRatio.toFixed(0)}% of total profit (>${(pathConfig.bestDayRatioThreshold * 100).toFixed(0)}% threshold)`,
      };
    }
    return { safe: true };
  }

  /** Reset window after a payout */
  recordPayout(amount: number): void {
    this.state = createPayoutLedgerState(this.config);
    this.state.daysSincePayout = 0;
  }

  getState(): Readonly<PayoutLedgerState> {
    return { ...this.state, dailyHistory: [...this.state.dailyHistory] };
  }

  /** One-line status for report */
  getStatusLine(): string {
    const pathConfig = getPayoutPathConfig(this.config.path);
    const eligible = this.state.eligible ? "ELIGIBLE" : "NOT-READY";
    const sign = this.state.windowNetPnL >= 0 ? "+" : "";
    return [
      `Payout:${eligible}`,
      `$${sign}${this.state.windowNetPnL.toFixed(0)}`,
      `${this.state.qualifyingDays}/${this.state.minQualifyingDays}d`,
      `best${(this.state.largestDayPct * 100).toFixed(0)}%`,
      `${this.config.path}`,
    ].join(" ");
  }
}
