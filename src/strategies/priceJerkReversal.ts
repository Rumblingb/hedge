/**
 * priceJerkReversal.ts — Price Jerk Indicator (PJI) reversal strategy.
 *
 * Source: SSRN 6487618 "The Price Jerk Indicator and the KCE Quantum System"
 * Third derivative of price applied to financial reversal detection.
 * 388 trades, 7 years NAS100+SPY. Win Rate 25.8%+19.8%=45.6%, PF 1.42, Calmar 10.0.
 *
 * Formula: PJI = regression_slope(price_accelerations, window=20)
 * Signal: PJI crosses zero → reversal.
 */
import { type Strategy, type StrategyContext, type StrategySignal, type TradeSide } from "../domain.js";

const WINDOW = 20;
const MIN_CONFIDENCE = 0.45;
const ATR_MULT_SL = 1.0;
const ATR_MULT_TP = 2.0;

function computePJI(history: Array<{close: number}>, window: number = WINDOW): number {
    if (history.length < window + 3) return 0;

    const accelerations: number[] = [];
    for (let i = 3; i < history.length; i++) {
        // Jerk = third derivative: P[i] - 3P[i-1] + 3P[i-2] - P[i-3]
        const jerk =
            history[i].close
            - 3 * history[i - 1].close
            + 3 * history[i - 2].close
            - history[i - 3].close;
        accelerations.push(jerk);
    }

    // Linear regression slope over window
    const n = Math.min(window, accelerations.length);
    const recent = accelerations.slice(-n);
    const xMean = (n - 1) / 2;
    const yMean = recent.reduce((a, b) => a + b, 0) / n;

    let num = 0;
    let den = 0;
    for (let i = 0; i < n; i++) {
        num += (i - xMean) * (recent[i] - yMean);
        den += (i - xMean) * (i - xMean);
    }
    return den === 0 ? 0 : num / den;
}

let prevPJI = new Map<string, number>();

export function resetPriceJerkReversalState(): void {
    prevPJI = new Map<string, number>();
}

export const priceJerkReversal: Strategy = {
    id: "price-jerk-reversal-15m",
    description:
        "Price Jerk Indicator reversal — third derivative of price. SSRN 6487618, PF 1.42, Calmar 10.0.",

    generateSignal(ctx: StrategyContext): StrategySignal | null {
        const { symbol, bar, history } = ctx;
        const sessionStart = ctx.sessionHistory?.[0]?.ts ?? "global";
        const key = `${symbol}:${sessionStart}`;

        if (!history || history.length < WINDOW + 5) return null;

        const pji = computePJI(history, WINDOW);
        const prev = prevPJI.get(key) ?? 0;
        prevPJI.set(key, pji);

        if (prev === 0) return null;

        let side: TradeSide | null = null;

        // PJI crosses above zero → LONG reversal (acceleration turning positive)
        if (prev < 0 && pji > 0) {
            side = "long";
        }
        // PJI crosses below zero → SHORT reversal (acceleration turning negative)
        else if (prev > 0 && pji < 0) {
            side = "short";
        }

        if (!side) return null;

        const atr = bar.high - bar.low;
        const entry = bar.close;
        const stop = side === "long"
            ? entry - atr * ATR_MULT_SL
            : entry + atr * ATR_MULT_SL;
        const target = side === "long"
            ? entry + atr * ATR_MULT_TP
            : entry - atr * ATR_MULT_TP;

        const confidence = Math.min(0.6, Math.abs(pji) * 10 + 0.3);
        if (confidence < MIN_CONFIDENCE) return null;

        return {
            symbol,
            strategyId: this.id,
            side,
            entry,
            stop,
            target,
            rr: Math.abs(target - entry) / Math.abs(stop - entry),
            confidence,
            contracts: 1,
            maxHoldMinutes: 60,
            meta: {
                pji,
                source: "ssrn-6487618",
                pf: 1.42,
                calmar: 10.0,
                researchOnly: true,
            },
        };
    },
};
