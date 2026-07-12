// setupJournal.ts — Mandatory NQ trade setup classifier.
//
// Every trade must be assigned one setup label. If the setup is unclear,
// the trade is blocked. This enforces the selectivity that makes the
// challenge risk model work — one or two A+ trades/day, not three mediocre ones.
//
// Four NQ playbook setups:
//   1. opening-drive-continuation — momentum continuation after first 15-min drive
//   2. liquidity-sweep-reversal   — sweep of session high/low then reversal
//   3. vwap-reclaim-reject        — price reclaims or rejects VWAP with volume
//   4. displacement-pullback      — large displacement bar + pullback to FVG/OB
//   0. unclear                    — no clear setup → NO TRADE

export type SetupLabel =
  | "opening-drive-continuation"
  | "liquidity-sweep-reversal"
  | "vwap-reclaim-reject"
  | "displacement-pullback"
  | "unclear";

export interface SetupAnnotation {
  label: SetupLabel;
  confidence: number;        // 0-1: how clearly this setup matches
  timestamp: string;
  symbol: string;
  entryPrice: number;
  notes: string;             // Brief rationale for the classification
}

export interface SetupJournalEntry {
  id: string;
  date: string;
  timestamp: string;
  setup: SetupAnnotation;
  direction: "long" | "short";
  result?: {
    pnl: number;
    exitReason: string;
    exitTimestamp: string;
  };
  postTradeReview?: string;
}

export interface SetupJournalState {
  entries: SetupJournalEntry[];
  totalTrades: number;
  bySetup: Record<SetupLabel, {
    count: number;
    wins: number;
    losses: number;
    totalPnL: number;
    avgPnL: number;
  }>;
}

export const SETUP_REQUIREMENTS: Record<Exclude<SetupLabel, "unclear">, {
  description: string;
  minConfidence: number;    // minimum confidence to allow trade
  typicalRr: number;        // typical R:R for this setup
  bestSessions: string[];  // best Chicago time sessions
}> = {
  "opening-drive-continuation": {
    description: "First 15-min candle sets direction, continuation after pullback to 5-min OB",
    minConfidence: 0.6,
    typicalRr: 2.5,
    bestSessions: ["08:30-09:30"],
  },
  "liquidity-sweep-reversal": {
    description: "Price sweeps session high/low to grab liquidity, then reverses with momentum",
    minConfidence: 0.65,
    typicalRr: 3.0,
    bestSessions: ["09:30-11:00", "13:00-15:00"],
  },
  "vwap-reclaim-reject": {
    description: "Price rejects VWAP with volume confirmation, or reclaims VWAP after deviation",
    minConfidence: 0.6,
    typicalRr: 2.0,
    bestSessions: ["09:30-11:30", "13:30-15:00"],
  },
  "displacement-pullback": {
    description: "Large displacement candle (2.5x ATR) followed by pullback to FVG/order block",
    minConfidence: 0.7,
    typicalRr: 2.8,
    bestSessions: ["08:30-10:00", "13:00-14:00"],
  },
};

export function createSetupJournalState(): SetupJournalState {
  const bySetup = {} as SetupJournalState["bySetup"];
  const labels: SetupLabel[] = [
    "opening-drive-continuation",
    "liquidity-sweep-reversal",
    "vwap-reclaim-reject",
    "displacement-pullback",
    "unclear",
  ];
  for (const label of labels) {
    bySetup[label] = { count: 0, wins: 0, losses: 0, totalPnL: 0, avgPnL: 0 };
  }
  return { entries: [], totalTrades: 0, bySetup };
}

export class SetupJournal {
  private state: SetupJournalState;
  private nextId = 1;

  constructor(initialState?: Partial<SetupJournalState>) {
    this.state = { ...createSetupJournalState(), ...initialState };
    if (this.state.entries.length > 0) {
      this.nextId = Math.max(...this.state.entries.map(e => parseInt(e.id))) + 1;
    }
  }

  /** Classify a trade setup. Returns null if unclear (block the trade). */
  classifySetup(args: {
    symbol: string;
    direction: "long" | "short";
    entryPrice: number;
    timestamp: string;
    /** Optional context for classification */
    context?: {
      barHigh?: number;
      barLow?: number;
      barOpen?: number;
      barClose?: number;
      barVolume?: number;
      sessionHigh?: number;
      sessionLow?: number;
      vwap?: number;
      atr?: number;
      priorBarRange?: number;
      priorBarDirection?: "up" | "down";
      /** Displacement size relative to ATR (for displacement-pullback) */
      displacementRatio?: number;
      /** Whether price swept session high/low */
      sweptSessionLevel?: "high" | "low" | null;
      /** Distance from VWAP in ATR units */
      vwapDistanceAtr?: number;
      /** Whether this is within first 15 minutes */
      isOpeningDrive?: boolean;
    };
  }): SetupAnnotation | null {
    const { symbol, direction, entryPrice, timestamp, context } = args;
    const ctx = context ?? {};

    // Try each setup in order of specificity
    const candidates: Array<{ label: Exclude<SetupLabel, "unclear">; confidence: number; notes: string }> = [];

    // 1. Opening drive continuation
    if (ctx.isOpeningDrive && ctx.priorBarDirection) {
      const continuation = direction === "long"
        ? ctx.priorBarDirection === "up"
        : ctx.priorBarDirection === "down";
      if (continuation && ctx.priorBarRange && ctx.atr && ctx.atr > 0) {
        const strength = ctx.priorBarRange / ctx.atr;
        const confidence = Math.min(0.95, 0.5 + strength * 0.3);
        if (confidence >= SETUP_REQUIREMENTS["opening-drive-continuation"].minConfidence) {
          candidates.push({
            label: "opening-drive-continuation",
            confidence,
            notes: `Opening drive ${ctx.priorBarDirection} bar, range ${(strength * 100).toFixed(0)}% ATR`,
          });
        }
      }
    }

    // 2. Liquidity sweep reversal
    if (ctx.sweptSessionLevel && ctx.atr && ctx.atr > 0) {
      const sweptAndReversed = (direction === "long" && ctx.sweptSessionLevel === "low")
        || (direction === "short" && ctx.sweptSessionLevel === "high");
      if (sweptAndReversed) {
        const confidence = 0.55 + (ctx.priorBarRange && ctx.atr > 0
          ? Math.min(0.35, ctx.priorBarRange / ctx.atr * 0.2)
          : 0.15);
        if (confidence >= SETUP_REQUIREMENTS["liquidity-sweep-reversal"].minConfidence) {
          candidates.push({
            label: "liquidity-sweep-reversal",
            confidence,
            notes: `Swept session ${ctx.sweptSessionLevel} then reversed ${direction}`,
          });
        }
      }
    }

    // 3. VWAP reclaim/reject
    if (ctx.vwap && ctx.vwapDistanceAtr !== undefined && Math.abs(ctx.vwapDistanceAtr) < 2.0) {
      const reclaiming = direction === "long" && entryPrice > ctx.vwap && ctx.priorBarDirection === "up";
      const rejecting = direction === "short" && entryPrice < ctx.vwap && ctx.priorBarDirection === "down";
      if (reclaiming || rejecting) {
        const dist = Math.abs(ctx.vwapDistanceAtr);
        const confidence = 0.55 + Math.min(0.35, (1 - dist / 2) * 0.35);
        if (confidence >= SETUP_REQUIREMENTS["vwap-reclaim-reject"].minConfidence) {
          candidates.push({
            label: "vwap-reclaim-reject",
            confidence,
            notes: `${reclaiming ? "Reclaimed" : "Rejected"} VWAP at ${dist.toFixed(2)} ATR distance`,
          });
        }
      }
    }

    // 4. Displacement + pullback
    if (ctx.displacementRatio && ctx.displacementRatio >= 2.5) {
      const pullback = direction === "long"
        ? entryPrice < (ctx.barHigh ?? entryPrice)
        : entryPrice > (ctx.barLow ?? entryPrice);
      if (pullback) {
        const confidence = 0.55 + Math.min(0.40, (ctx.displacementRatio - 2.5) * 0.2);
        if (confidence >= SETUP_REQUIREMENTS["displacement-pullback"].minConfidence) {
          candidates.push({
            label: "displacement-pullback",
            confidence,
            notes: `Displacement ${ctx.displacementRatio.toFixed(1)}x ATR, pullback entry`,
          });
        }
      }
    }

    // Pick highest-confidence setup
    if (candidates.length === 0) {
      return null; // Unclear — block the trade
    }

    candidates.sort((a, b) => b.confidence - a.confidence);
    const best = candidates[0];

    return {
      label: best.label,
      confidence: Number(best.confidence.toFixed(3)),
      timestamp,
      symbol,
      entryPrice,
      notes: best.notes,
    };
  }

  /** Record a trade entry with setup label */
  recordEntry(args: {
    date: string;
    timestamp: string;
    setup: SetupAnnotation;
    direction: "long" | "short";
  }): SetupJournalEntry {
    const entry: SetupJournalEntry = {
      id: String(this.nextId++).padStart(4, "0"),
      date: args.date,
      timestamp: args.timestamp,
      setup: args.setup,
      direction: args.direction,
    };

    this.state.entries.push(entry);
    this.state.totalTrades++;
    this.state.bySetup[args.setup.label].count++;

    return entry;
  }

  /** Record trade result for a journal entry */
  recordResult(entryId: string, pnl: number, exitReason: string, exitTimestamp: string): void {
    const entry = this.state.entries.find(e => e.id === entryId);
    if (!entry) return;

    entry.result = { pnl, exitReason, exitTimestamp };
    const won = pnl > 0;
    const stats = this.state.bySetup[entry.setup.label];
    if (won) stats.wins++;
    else stats.losses++;
    stats.totalPnL += pnl;
    stats.avgPnL = stats.totalPnL / Math.max(1, stats.count);
  }

  /** Add post-trade review notes */
  addReview(entryId: string, review: string): void {
    const entry = this.state.entries.find(e => e.id === entryId);
    if (entry) {
      entry.postTradeReview = review;
    }
  }

  /** Get performance summary by setup label */
  getSetupPerformance(): Record<SetupLabel, {
    count: number;
    winRate: number;
    totalPnL: number;
    avgPnL: number;
    isProfitable: boolean;
  }> {
    const result = {} as Record<SetupLabel, any>;
    for (const [label, stats] of Object.entries(this.state.bySetup)) {
      result[label as SetupLabel] = {
        ...stats,
        winRate: stats.count > 0 ? stats.wins / stats.count : 0,
        isProfitable: stats.totalPnL > 0,
      };
    }
    return result;
  }

  getState(): Readonly<SetupJournalState> {
    return {
      entries: [...this.state.entries],
      totalTrades: this.state.totalTrades,
      bySetup: { ...this.state.bySetup },
    };
  }

  /** One-line status for report */
  getStatusLine(): string {
    const perf = this.getSetupPerformance();
    const best = Object.entries(perf)
      .filter(([label]) => label !== "unclear")
      .sort(([, a], [, b]) => b.totalPnL - a.totalPnL)[0];

    return [
      `Journal:${this.state.totalTrades}t`,
      best ? `${best[0]}:$${best[1].totalPnL.toFixed(0)}` : "no-data",
    ].join(" ");
  }
}
