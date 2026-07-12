/**
 * Structural Flows Calendar Strategy
 *
 * Trades institutional structural flows — the predictable, mandatory large flows
 * that institutions MUST execute regardless of market conditions.
 *
 * Four sub-signals:
 * 1. Quarter-End Rebalancing — pension funds rebalancing equities vs bonds
 * 2. Futures Roll Window — slight selling pressure during contract roll
 * 3. OPEX Friday Gamma Pin — price drifts toward max-pain strike
 * 4. Post-FOMC Fade — fade the initial spike after FOMC announcement
 *
 * Sources: Claude strategic analysis + FOMC fade research + quarterly rebalancing research
 */
import { DateTime } from "luxon";
import type { Bar, Strategy, StrategyContext, StrategySignal, TradeSide } from "../domain.js";
import { calculateRr } from "../risk/guardrails.js";
import { averageTrueRange } from "../utils/indicators.js";
import { chicagoTime, minutesSinceMidnightCt } from "../utils/time.js";

// ── Constants ─────────────────────────────────────────────────────────────────

const TARGET_SYMBOLS = ["ES", "NQ", "ZN"];
const STRATEGY_ID = "structural-flows";

/** FOMC 2026 announcement dates (Wednesdays; announcement at 14:00 ET / 13:00 CT) */
const FOMC_2026_DATES = new Set([
  "2026-01-28",
  "2026-03-18",
  "2026-05-06",
  "2026-06-17",
  "2026-07-29",
  "2026-09-16",
  "2026-11-04",
  "2026-12-16",
]);

/** Months that end a calendar quarter */
const QUARTER_MONTHS = new Set([3, 6, 9, 12]);

/** Quarter-end rebalancing: look at last N calendar days of quarter month */
const QUARTER_END_WINDOW_DAYS = 5;

/** Minimum quarterly return magnitude (5%) to trigger rebalancing signal */
const QUARTERLY_RETURN_THRESHOLD = 0.05;

/** Roll window: N calendar days before quarterly expiry (3rd Friday) */
const ROLL_WINDOW_DAYS = 10;

/** OPEX gamma pin window in minutes since midnight CT: 10:00–13:00 CT (11 AM–2 PM ET) */
const OPEX_PIN_START_CT_MINUTES = 10 * 60; // 10:00 CT
const OPEX_PIN_END_CT_MINUTES = 13 * 60; // 13:00 CT

/** FOMC announcement time in minutes since midnight CT: 13:00 CT (14:00 ET) */
const FOMC_ANNOUNCEMENT_CT_MINUTES = 13 * 60;

/** FOMC fade window: 15–35 min after announcement (13:15–13:35 CT) */
const FOMC_FADE_START_CT_MINUTES = FOMC_ANNOUNCEMENT_CT_MINUTES + 15;
const FOMC_FADE_END_CT_MINUTES = FOMC_ANNOUNCEMENT_CT_MINUTES + 35;

/** FOMC spike threshold: fade if 5-min move exceeds 1.5 × ATR */
const FOMC_SPIKE_ATR_MULTIPLE = 1.5;

// ── Date helpers ──────────────────────────────────────────────────────────────

/** Extract Chicago date key ("YYYY-MM-DD") from a bar's ISO timestamp */
function barDateKey(barTs: string): string {
  return chicagoTime(barTs).toFormat("yyyy-LL-dd");
}

/** Get the year and month from a Chicago date key */
function parseDateKey(dateKey: string): { year: number; month: number; day: number } {
  const parts = dateKey.split("-").map(Number);
  return { year: parts[0]!, month: parts[1]!, day: parts[2]! };
}

/**
 * Compute the 3rd Friday of a given year/month.
 * Luxon's weekday: 1=Mon … 5=Fri.
 */
function thirdFridayOf(year: number, month: number): string {
  let day = 1;
  const first = DateTime.fromObject({ year, month, day }, { zone: "America/Chicago" });
  const weekday = first.weekday; // 1=Mon … 5=Fri … 7=Sun
  const offset = (5 - weekday + 7) % 7;
  const thirdFriday = first.plus({ days: offset + 14 });
  return thirdFriday.toFormat("yyyy-LL-dd");
}

/** True if bar date falls in the last N calendar days of a quarter-end month */
function isQuarterEnd(dateKey: string): boolean {
  const { year, month, day } = parseDateKey(dateKey);
  if (!QUARTER_MONTHS.has(month)) return false;
  // Get last day of month (JS Date month is 0-indexed, day 0 = last day of previous month)
  const lastDay = new Date(year, month, 0).getDate();
  // For quarter end, use last QUARTER_END_WINDOW_DAYS
  const threshold = Math.max(1, lastDay - QUARTER_END_WINDOW_DAYS + 1);
  return day >= threshold;
}

/**
 * True if bar date is within ROLL_WINDOW_DAYS calendar days before a quarterly
 * expiry (3rd Friday of Mar/Jun/Sep/Dec).
 */
function isRollWindow(dateKey: string): boolean {
  const { year, month, day } = parseDateKey(dateKey);
  const barDate = DateTime.fromISO(dateKey, { zone: "America/Chicago" });

  // Check current month and next month for quarterly expiry
  for (let offset = 0; offset <= 1; offset++) {
    const checkMonth = month + offset;
    const adjYear = checkMonth > 12 ? year + 1 : year;
    const adjMonth = checkMonth > 12 ? checkMonth - 12 : checkMonth;

    if (!QUARTER_MONTHS.has(adjMonth)) continue;

    const expiryStr = thirdFridayOf(adjYear, adjMonth);
    const expiryDate = DateTime.fromISO(expiryStr, { zone: "America/Chicago" });
    const daysUntil = expiryDate.diff(barDate, "days").days;

    if (daysUntil >= 0 && daysUntil <= ROLL_WINDOW_DAYS) return true;
  }

  return false;
}

/** True if bar date is the 3rd Friday of any month (OPEX Friday) */
function isOpexFriday(dateKey: string): boolean {
  const { year, month } = parseDateKey(dateKey);
  return dateKey === thirdFridayOf(year, month);
}

/** True if bar date is a scheduled 2026 FOMC announcement day */
function isFomcDay(dateKey: string): boolean {
  return FOMC_2026_DATES.has(dateKey);
}

// ── Data helpers ──────────────────────────────────────────────────────────────

/** Extract daily closes from history bars (one close per calendar date) */
function extractDailyCloses(history: Bar[]): Array<{ date: string; close: number }> {
  const daily: Array<{ date: string; close: number }> = [];
  let lastDate = "";
  for (const bar of history) {
    const date = barDateKey(bar.ts);
    if (date !== lastDate) {
      if (lastDate !== "") daily.push({ date: lastDate, close: bar.close });
      lastDate = date;
    }
  }
  // Push current (partial) day
  if (history.length > 0) {
    const tail = history[history.length - 1]!;
    daily.push({ date: barDateKey(tail.ts), close: tail.close });
  }
  return daily;
}

/**
 * Compute approximate quarterly return using daily closes.
 * Looks for a reference close roughly 60–70 trading days back.
 */
function computeQuarterlyReturn(dailyCloses: Array<{ date: string; close: number }>): number | null {
  if (dailyCloses.length < 50) return null;
  const latest = dailyCloses[dailyCloses.length - 1]!;
  // Walk back ~60 entries to approximate start of quarter
  const refIdx = Math.max(0, dailyCloses.length - 60);
  const ref = dailyCloses[refIdx]!;
  if (ref.close <= 0) return null;
  return (latest.close - ref.close) / ref.close;
}

/** Get the prior trading day's close from history (day before current bar date) */
function getPriorDayClose(history: Bar[], currentDateKey: string): number | null {
  for (let i = history.length - 1; i >= 0; i--) {
    const bar = history[i]!;
    if (barDateKey(bar.ts) < currentDateKey) {
      return bar.close;
    }
  }
  return null;
}

// ── Signal builder ────────────────────────────────────────────────────────────

function buildSignal(args: {
  context: StrategyContext;
  side: TradeSide;
  stop: number;
  target: number;
  confidence: number;
  subSignal: string;
  metaExtras?: Record<string, string | number | boolean>;
}): StrategySignal | null {
  const { context, side, stop, target, confidence, subSignal, metaExtras } = args;
  const entry = context.bar.close;
  const rr = calculateRr(entry, stop, target, side);
  if (rr <= 0) return null;

  return {
    symbol: context.symbol,
    strategyId: STRATEGY_ID,
    side,
    entry,
    stop,
    target,
    rr,
    confidence,
    contracts: 1,
    maxHoldMinutes: 25,
    meta: {
      subSignal,
      ...metaExtras,
    },
  };
}

// ── Strategy class ────────────────────────────────────────────────────────────

export class StructuralFlowsStrategy implements Strategy {
  public readonly id = STRATEGY_ID;
  public readonly description =
    "Institutional structural flows: quarter-end rebalancing, futures roll, " +
    "OPEX gamma pin, post-FOMC fade. Four mandatory-flow signals in one strategy.";

  private readonly symbolHistory: Map<string, Bar[]> = new Map();

  public generateSignal(context: StrategyContext): StrategySignal | null {
    if (!TARGET_SYMBOLS.includes(context.symbol)) return null;

    const barDate = barDateKey(context.bar.ts);
    const ctMinutes = minutesSinceMidnightCt(context.bar.ts);

    // Update internal symbol history
    let internalHistory = this.symbolHistory.get(context.symbol) ?? [];
    internalHistory = [...internalHistory, context.bar];
    if (internalHistory.length > 500) internalHistory = internalHistory.slice(-500);
    this.symbolHistory.set(context.symbol, internalHistory);

    const atr = averageTrueRange(context.sessionHistory, 14);
    if (atr <= 0) return null;

    const targetRr = Math.max(context.config.guardrails.minRr, 2.0);

    // ── Sub-signal 1: Quarter-End Rebalancing ─────────────────────────────────
    if (isQuarterEnd(barDate)) {
      // Use full context.history for quarterly return (needs ~60 days of data)
      const dailyCloses = extractDailyCloses(context.history);
      const qReturn = computeQuarterlyReturn(dailyCloses);

      if (qReturn !== null && Math.abs(qReturn) > QUARTERLY_RETURN_THRESHOLD) {
        const isEquity = context.symbol === "ES" || context.symbol === "NQ";
        const isBond = context.symbol === "ZN";

        if (isEquity) {
          // Equities up >5% → short (pension funds selling to rebalance)
          // Equities down >5% → long (pension funds buying)
          const side: TradeSide = qReturn > QUARTERLY_RETURN_THRESHOLD ? "short" : "long";
          const risk = atr * 0.8;
          const stop = side === "long"
            ? context.bar.close - risk
            : context.bar.close + risk;
          const target = side === "long"
            ? context.bar.close + risk * targetRr
            : context.bar.close - risk * targetRr;

          return buildSignal({
            context,
            side,
            stop,
            target,
            confidence: 0.62,
            subSignal: "quarter-end-rebalance",
            metaExtras: {
              quarterlyReturn: Math.round(qReturn * 1000) / 10,
              direction: qReturn > QUARTERLY_RETURN_THRESHOLD ? "equity-up-sell" : "equity-down-buy",
            },
          });
        }

        if (isBond) {
          // ZN: opposite direction — bond buying when equities up, bond selling when equities down
          const side: TradeSide = qReturn > QUARTERLY_RETURN_THRESHOLD ? "long" : "short";
          const risk = atr * 0.8;
          const stop = side === "long"
            ? context.bar.close - risk
            : context.bar.close + risk;
          const target = side === "long"
            ? context.bar.close + risk * targetRr
            : context.bar.close - risk * targetRr;

          return buildSignal({
            context,
            side,
            stop,
            target,
            confidence: 0.58,
            subSignal: "quarter-end-rebalance-zn",
            metaExtras: {
              quarterlyReturn: Math.round(qReturn * 1000) / 10,
              direction: qReturn > QUARTERLY_RETURN_THRESHOLD ? "equity-up-buy-bonds" : "equity-down-sell-bonds",
            },
          });
        }
      }
    }

    // ── Sub-signal 2: Futures Roll Window ─────────────────────────────────────
    if (isRollWindow(barDate)) {
      // Slight selling pressure on front month during roll
      const risk = atr * 0.7;
      const stop = context.bar.close + risk;
      const target = context.bar.close - risk * targetRr;

      return buildSignal({
        context,
        side: "short",
        stop,
        target,
        confidence: 0.55,
        subSignal: "roll-window",
        metaExtras: {
          rollWindowDays: ROLL_WINDOW_DAYS,
        },
      });
    }

    // ── Sub-signal 3: OPEX Friday Gamma Pin ──────────────────────────────────
    if (
      isOpexFriday(barDate) &&
      ctMinutes >= OPEX_PIN_START_CT_MINUTES &&
      ctMinutes <= OPEX_PIN_END_CT_MINUTES
    ) {
      const priorClose = getPriorDayClose(context.history, barDate);
      if (priorClose !== null && priorClose > 0) {
        const currentClose = context.bar.close;
        const side: TradeSide = currentClose > priorClose ? "short" : "long";
        const risk = atr * 0.6;
        const stop = side === "long"
          ? context.bar.close - risk
          : context.bar.close + risk;
        const target = side === "long"
          ? context.bar.close + risk * targetRr
          : context.bar.close - risk * targetRr;

        return buildSignal({
          context,
          side,
          stop,
          target,
          confidence: 0.60,
          subSignal: "opex-gamma-pin",
          metaExtras: {
            priorClose,
            maxPainProxy: priorClose,
          },
        });
      }
    }

    // ── Sub-signal 4: Post-FOMC Fade ─────────────────────────────────────────
    if (
      isFomcDay(barDate) &&
      ctMinutes >= FOMC_FADE_START_CT_MINUTES &&
      ctMinutes <= FOMC_FADE_END_CT_MINUTES
    ) {
      // Find bars since announcement (13:00 CT) to compute spike
      const announcementBars = context.sessionHistory.filter((bar) => {
        const m = minutesSinceMidnightCt(bar.ts);
        return m >= FOMC_ANNOUNCEMENT_CT_MINUTES && m <= ctMinutes;
      });

      if (announcementBars.length >= 2) {
        const firstClose = announcementBars[0]!.close;
        const lastClose = announcementBars[announcementBars.length - 1]!.close;
        const spike = lastClose - firstClose;
        const spikeThreshold = atr * FOMC_SPIKE_ATR_MULTIPLE;

        if (Math.abs(spike) > spikeThreshold) {
          // Fade the spike
          const side: TradeSide = spike > 0 ? "short" : "long";
          const risk = atr * 0.7;
          const stop = side === "long"
            ? context.bar.close - risk
            : context.bar.close + risk;
          const target = side === "long"
            ? context.bar.close + risk * targetRr
            : context.bar.close - risk * targetRr;

          return buildSignal({
            context,
            side,
            stop,
            target,
            confidence: 0.65,
            subSignal: "post-fomc-fade",
            metaExtras: {
              spikeRounded: Math.round(spike * 100) / 100,
              spikeThresholdRounded: Math.round(spikeThreshold * 100) / 100,
            },
          });
        }
      }
    }

    return null;
  }
}
