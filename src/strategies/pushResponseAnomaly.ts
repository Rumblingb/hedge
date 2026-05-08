/**
 * #68 Push-Response Anomalies — Asymmetric Liquidity Replenishment
 * Source: Vlasiuk, D. & Smirnov, M. (Nov 2025). "Push-response anomalies
 *   in high-frequency S&P 500 price series." arXiv:2511.06177.
 *
 * Key finding: Large negative pushes (sell-side shocks) → disproportionately
 * stronger positive responses. Asymmetric replenishment creates tradable
 * "pockets" of conditional nonrandomness beyond 5K ticks.
 *
 * Implementation: Detect "push" events (large directional moves with volume),
 * measure subsequent "response" (mean-reversion or continuation), and trade
 * the asymmetric pattern: fade sell-offs, follow breakouts on buy surges.
 *
 * Market logic: Sell-side liquidity shocks create temporary imbalances that
 * market makers replenish at better prices. Large sellers exhaust themselves,
 * creating mean-reversion opportunities.
 */
import type { Bar, Strategy, StrategyContext, StrategySignal, TradeSide } from "../domain.js";
import { calculateRr } from "../risk/guardrails.js";
import { averageTrueRange } from "../utils/indicators.js";
import { inferBarIntervalMinutes } from "../utils/time.js";

const TARGET_SYMBOLS = ["ES", "NQ", "CL"];
const PUSH_ATR_MULTIPLE = 2.0; // bar must exceed 2x ATR to qualify as "push"
const RESPONSE_LOOKBACK = 10; // bars after push to measure response

interface PushEvent {
  direction: "up" | "down";
  magnitudeAtr: number;
  volumeRatio: number;
  barIndex: number;
}

function detectPush(history: Bar[], atr: number): PushEvent | null {
  if (history.length < 3) return null;
  const bar = history[history.length - 2]!; // Previous bar (we're measuring response NOW)
  const prevBar = history[history.length - 3]!;
  const range = bar.high - bar.low;
  if (range < atr * PUSH_ATR_MULTIPLE) return null;
  const direction = bar.close > bar.open ? "up" : "down";
  const magnitudeAtr = range / atr;
  const avgVol = history.slice(-20, -2).reduce((s, b) => s + b.volume, 0) / 18;
  const volumeRatio = avgVol > 0 ? bar.volume / avgVol : 1;
  return { direction, magnitudeAtr, volumeRatio, barIndex: history.length - 2 };
}

function measureResponse(history: Bar[], push: PushEvent): {
  direction: "mean-reverting" | "continuing"; strength: number;
} {
  const barsAfter = history.slice(push.barIndex + 1);
  if (barsAfter.length < 2) return { direction: "mean-reverting", strength: 0 };
  const pushBar = history[push.barIndex]!;
  const pushClose = pushBar.close;
  const responseCloses = barsAfter.map((b) => b.close);
  const avgResponse = responseCloses.reduce((a, b) => a + b, 0) / responseCloses.length;
  const responsePct = (avgResponse - pushClose) / pushClose;
  if (push.direction === "down") {
    // Sell push → positive response = mean-reversion (buy the dip)
    return {
      direction: responsePct > 0.001 ? "mean-reverting" : "continuing",
      strength: Math.abs(responsePct) * 100,
    };
  }
  // Buy push → negative response = mean-reversion (sell the rip)
  return {
    direction: responsePct < -0.001 ? "mean-reverting" : "continuing",
    strength: Math.abs(responsePct) * 100,
  };
}

export class PushResponseAnomalyStrategy implements Strategy {
  public readonly id = "push-response-anomaly";
  public readonly description =
    "Push-response anomaly detection. Fades large directional moves (sell-off → buy, " +
    "rally → fade) based on asymmetric liquidity replenishment. Source: Vlasiuk 2025 arXiv:2511.06177.";

  private readonly symbolHistory: Map<string, Bar[]> = new Map();

  public generateSignal(context: StrategyContext): StrategySignal | null {
    if (!TARGET_SYMBOLS.includes(context.symbol)) return null;
    const prevBarTs = context.history[context.history.length - 1]?.ts;
    const barIntervalMinutes = inferBarIntervalMinutes(prevBarTs, context.bar.ts);
    if (barIntervalMinutes >= 240) return null;

    let history = this.symbolHistory.get(context.symbol) ?? [];
    history = [...history, context.bar];
    if (history.length > 200) history = history.slice(-200);
    this.symbolHistory.set(context.symbol, history);

    const atr = averageTrueRange(context.sessionHistory, 14);
    if (atr <= 0) return null;

    const push = detectPush(history, atr);
    if (!push) return null;

    const response = measureResponse(history, push);

    // Only trade mean-reverting responses (asymmetric edge)
    if (response.direction !== "mean-reverting") return null;
    // Need minimum response strength
    if (response.strength < 2) return null;

    // Direction: fade the push
    const side: TradeSide = push.direction === "down" ? "long" : "short";
    const risk = atr * 1.0;
    const targetRr = Math.max(context.config.guardrails.minRr, 2.0);
    const entry = context.bar.close;
    const stop = side === "long" ? entry - risk : entry + risk;
    const target = side === "long" ? entry + risk * targetRr : entry - risk * targetRr;

    const rr = calculateRr(entry, stop, target, side);
    if (rr <= 0) return null;

    const confidence = Math.min(0.75, 0.45 + response.strength * 0.05);

    return {
      symbol: context.symbol, strategyId: "push-response-anomaly", side, entry, stop, target, rr,
      confidence, contracts: 1, maxHoldMinutes: 10,
      meta: {
        pushDirection: push.direction,
        pushMagnitude: Math.round(push.magnitudeAtr * 100) / 100,
        responseStrength: Math.round(response.strength * 100) / 100,
        paper: "arXiv:2511.06177",
      },
    };
  }
}
