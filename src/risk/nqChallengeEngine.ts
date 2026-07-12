// nqChallengeEngine.ts — NQ Challenge Execution Engine
//
// Wires together the four core modules into a single execution interface:
//   - NQChallengePhaseController (state machine)
//   - DailyLock (daily trade gates)
//   - PayoutLedger (funded payout tracking)
//   - SetupJournal (mandatory trade classification)
//
// This is the single entry point for the NQ prop-firm challenge track.
// Everything else (research, Polymarket) runs independently.

import type { GuardrailConfig, StrategySignal } from "../domain.js";
import {
  NQChallengePhaseController,
  type NQChallengePhase,
  type PhaseRiskProfile,
} from "./challengePhaseController.js";
import {
  DailyLock,
  chicagoToday,
  type DailyLockDecision,
  type DailyLockState,
} from "./dailyLock.js";
import {
  PayoutLedger,
  type PayoutLedgerState,
  type PayoutLedgerConfig,
  type PayoutPath,
} from "./payoutLedger.js";
import {
  SetupJournal,
  type SetupLabel,
  type SetupAnnotation,
  type SetupJournalEntry,
  type SetupJournalState,
} from "./setupJournal.js";

export interface NQChallengeState {
  phase: NQChallengePhase;
  phaseSince: string;
  riskProfile: PhaseRiskProfile;
  dailyLock: DailyLockState;
  payoutLedger: PayoutLedgerState | null; // null in non-funded phases
  setupJournal: SetupJournalState;
}

export interface PreTradeCheck {
  allowed: boolean;
  reasons: string[];
  /** Setup classification if allowed */
  setup?: SetupAnnotation;
  /** Daily lock decision */
  lockDecision?: DailyLockDecision;
  /** Payout consistency check (funded only) */
  payoutCheck?: { safe: boolean; reason?: string };
}

export interface PostTradeRecord {
  entryId: string;
  setupLabel: SetupLabel;
  dailyState: DailyLockState;
  journalEntry: SetupJournalEntry;
}

export interface EODReport {
  date: string;
  phase: NQChallengePhase;
  statusLine: string;
  dailyLock: DailyLockState;
  payoutLedger: PayoutLedgerState | null;
  bestSetup: string;
  worstSetup: string;
  tradesToday: number;
  pnlToday: number;
}

export class NQChallengeEngine {
  public readonly phaseController: NQChallengePhaseController;
  public readonly dailyLock: DailyLock;
  public readonly payoutLedger: PayoutLedger | null;
  public readonly setupJournal: SetupJournal;

  constructor(args: {
    initialPhase?: NQChallengePhase;
    payoutConfig?: PayoutLedgerConfig;
  }) {
    const phase = args.initialPhase ?? "challenge-demo";
    this.phaseController = new NQChallengePhaseController(phase);
    this.dailyLock = new DailyLock();
    this.setupJournal = new SetupJournal();

    if (args.payoutConfig) {
      this.payoutLedger = new PayoutLedger(args.payoutConfig);
    } else {
      this.payoutLedger = new PayoutLedger({
        accountTier: 50000,
        path: "standard",
      });
    }
  }

  /** Full pre-trade check: setup classification + daily lock + phase gates + payout consistency */
  preTradeCheck(args: {
    symbol: string;
    direction: "long" | "short";
    entryPrice: number;
    timestamp: string;
    /** Context for setup classification */
    setupContext?: Parameters<SetupJournal["classifySetup"]>[0]["context"];
    /** Today's P&L so far (for payout check) */
    todayPnL?: number;
  }): PreTradeCheck {
    const reasons: string[] = [];

    // 1. Phase gate — paused means no trading
    const phase = this.phaseController.getPhase();
    if (phase === "paused") {
      return { allowed: false, reasons: ["Phase is PAUSED — no trading allowed"] };
    }
    if (phase === "research") {
      return { allowed: false, reasons: ["Phase is RESEARCH — no live/demo trading"] };
    }

    // 2. Setup classification — mandatory for challenge/funded phases
    const riskProfile = this.phaseController.getRiskProfile();
    let setup: SetupAnnotation | null = null;

    if (riskProfile.requireSetupLabel) {
      setup = this.setupJournal.classifySetup({
        symbol: args.symbol,
        direction: args.direction,
        entryPrice: args.entryPrice,
        timestamp: args.timestamp,
        context: args.setupContext,
      });

      if (!setup) {
        return { allowed: false, reasons: ["No clear setup — trade blocked by setup classifier"] };
      }
    }

    // 3. Daily lock check
    const lockDecision = this.dailyLock.canTrade(phase);
    if (!lockDecision.allowed) {
      reasons.push(`Daily lock: ${lockDecision.reason}`);
    }

    // 4. Payout consistency check (funded phase only)
    let payoutCheck: PreTradeCheck["payoutCheck"] = undefined;
    if (phase === "funded-payout-defense" && this.payoutLedger) {
      const todayPnL = args.todayPnL ?? this.dailyLock.getState().dailyPnL;
      // Estimate trade P&L based on risk profile
      const estTradePnl = 200; // rough estimate for MNQ
      payoutCheck = this.payoutLedger.checkPreTrade(todayPnL, estTradePnl);
      if (!payoutCheck.safe) {
        reasons.push(`Payout consistency: ${payoutCheck.reason}`);
      }
    }

    return {
      allowed: reasons.length === 0,
      reasons,
      setup: setup ?? undefined,
      lockDecision,
      payoutCheck,
    };
  }

  /** Record a completed trade through all modules */
  postTradeRecord(args: {
    date: string;
    timestamp: string;
    setup: SetupAnnotation;
    direction: "long" | "short";
    pnl: number;
    exitReason: string;
    exitTimestamp: string;
  }): PostTradeRecord {
    const won = args.pnl > 0;

    // 1. Journal entry
    const journalEntry = this.setupJournal.recordEntry({
      date: args.date,
      timestamp: args.timestamp,
      setup: args.setup,
      direction: args.direction,
    });

    // 2. Record result in journal
    this.setupJournal.recordResult(journalEntry.id, args.pnl, args.exitReason, args.exitTimestamp);

    // 3. Update daily lock
    this.dailyLock.recordTrade(args.pnl, won, args.setup.label, this.phaseController.getPhase());

    // 4. Update payout ledger (end of day only, but track daily P&L)
    // Payout ledger is updated separately at EOD

    return {
      entryId: journalEntry.id,
      setupLabel: args.setup.label,
      dailyState: this.dailyLock.getState(),
      journalEntry,
    };
  }

  /** End-of-day processing */
  endOfDay(): EODReport {
    const date = chicagoToday();
    const phase = this.phaseController.getPhase();
    const dailyState = this.dailyLock.getState();
    const perf = this.setupJournal.getSetupPerformance();

    // Update payout ledger with today's results
    if (this.payoutLedger && dailyState.tradeCount > 0) {
      const wonToday = dailyState.lastTradeResult === "win" ? 1 : 0;
      const lostToday = dailyState.tradeCount - wonToday;
      this.payoutLedger.recordDay(
        date,
        dailyState.dailyPnL,
        dailyState.tradeCount,
        Math.max(0, wonToday),
        Math.max(0, lostToday),
      );
    }

    // Auto-transition: challenge-demo → challenge-live when conditions met
    // This is manual for now — founder approves transition

    // Find best and worst setup
    let bestSetup = "none";
    let worstSetup = "none";
    let bestPnL = -Infinity;
    let worstPnL = Infinity;

    for (const [label, stats] of Object.entries(perf)) {
      if (label === "unclear") continue;
      if (stats.totalPnL > bestPnL) { bestPnL = stats.totalPnL; bestSetup = label; }
      if (stats.totalPnL < worstPnL) { worstPnL = stats.totalPnL; worstSetup = label; }
    }

    return {
      date,
      phase,
      statusLine: this.getStatusLine(),
      dailyLock: dailyState,
      payoutLedger: this.payoutLedger?.getState() ?? null,
      bestSetup,
      worstSetup,
      tradesToday: dailyState.tradeCount,
      pnlToday: dailyState.dailyPnL,
    };
  }

  /** One-line status for EOD/morning report */
  getStatusLine(): string {
    const phase = this.phaseController.getStatusLine();
    const daily = this.dailyLock.getStatusLine();
    const payout = this.payoutLedger?.getStatusLine() ?? "Payout:N/A";
    const journal = this.setupJournal.getStatusLine();
    return `${phase} | ${daily} | ${journal} | ${payout}`;
  }

  /** Full state snapshot for persistence */
  getState(): NQChallengeState {
    return {
      phase: this.phaseController.getPhase(),
      phaseSince: this.phaseController.getState().phaseSince,
      riskProfile: this.phaseController.getRiskProfile(),
      dailyLock: this.dailyLock.getState(),
      payoutLedger: this.payoutLedger?.getState() ?? null,
      setupJournal: this.setupJournal.getState(),
    };
  }

  /** Build guardrail overrides from current phase */
  buildGuardrailOverrides(): Partial<GuardrailConfig> {
    return this.phaseController.buildGuardrailOverrides();
  }

  /** Attempt phase transition */
  transitionPhase(to: NQChallengePhase, reason: string): boolean {
    return this.phaseController.transition(to, reason);
  }
}
