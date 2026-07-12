import type { Strategy, StrategyContext, StrategySignal, SupportedStrategyId } from "../domain.js";

function avgTrueRange(
  bars: { high: number; low: number; close: number }[],
  period: number,
): number {
  if (bars.length < period + 1) return 0;
  const trValues: number[] = [];
  for (let i = 1; i < bars.length; i++) {
    const prev = bars[i - 1]!;
    const curr = bars[i]!;
    trValues.push(
      Math.max(
        curr.high - curr.low,
        Math.abs(curr.high - prev.close),
        Math.abs(curr.low - prev.close),
      ),
    );
  }
  const window = trValues.slice(-period);
  if (window.length === 0) return 0;
  return window.reduce((sum, tr) => sum + tr, 0) / window.length;
}

export class PostNewsSettlementStrategy implements Strategy {
  public readonly id: SupportedStrategyId = "post-news-settlement";
  public readonly name = "Post-News Settlement";
  public readonly description =
    "After a news-driven spike (>2.5× ATR), wait for volume to drop below 70% of 20-bar average, then enter in the spike's direction. The institutional settlement trade.";
  public readonly tags = ["momentum", "news", "volume"];

  public generateSignal(context: StrategyContext): StrategySignal | null {
    const { bar, history } = context;
    if (history.length < 22) return null;

    const atr = avgTrueRange(
      history.map((b) => ({ high: b.high, low: b.low, close: b.close })),
      14,
    );
    if (atr <= 0) return null;

    const spikeThreshold = atr * 2.5;
    const recentWindow = history.slice(-5);
    let spikeIdx = -1;
    for (let i = recentWindow.length - 1; i >= 0; i--) {
      if (recentWindow[i]!.high - recentWindow[i]!.low >= spikeThreshold) {
        spikeIdx = i;
        break;
      }
    }
    if (spikeIdx === -1) return null;

    const spikeBar = recentWindow[spikeIdx]!;
    const afterSpike = recentWindow.slice(spikeIdx + 1);
    if (afterSpike.length === 0) return null;

    const volStart = history.length - 22 - afterSpike.length;
    const volEnd = history.length - 2 - afterSpike.length;
    const preSpikeBars = history.slice(Math.max(0, volStart), volEnd);
    if (preSpikeBars.length < 5) return null;
    const preVolAvg =
      preSpikeBars.reduce((sum, b) => sum + (b.volume ?? 0), 0) /
      preSpikeBars.length;
    if (preVolAvg <= 0) return null;

    let settlementBar: (typeof afterSpike)[0] | null = null;
    for (const ab of afterSpike) {
      if ((ab.volume ?? 0) > 0 && ab.volume! < preVolAvg * 0.7) {
        settlementBar = ab;
        break;
      }
    }
    if (!settlementBar) return null;

    const direction = spikeBar.close > spikeBar.open ? "long" : "short";
    if (direction === "long" && bar.close <= bar.open) return null;
    if (direction === "short" && bar.close >= bar.open) return null;

    const stopR = 1.0;
    const targetR = 1.8;

    if (direction === "long") {
      const stop = bar.close - atr * stopR;
      if (stop <= 0) return null;
      const target = bar.close + atr * targetR;
      return {
        symbol: context.symbol,
        strategyId: this.id,
        side: "long",
        entry: bar.close,
        stop,
        target,
        rr: targetR / stopR,
        confidence: 0.55,
        contracts: 1,
        maxHoldMinutes: 45,
        meta: {
          spikeAtrMultiple: ((spikeBar.high - spikeBar.low) / atr).toFixed(2),
          volDryUpRatio: (((settlementBar.volume ?? 0) / preVolAvg).toFixed(2)),
          strategy: "post-news-settlement",
        },
      };
    }

    const stop = bar.close + atr * stopR;
    const target = bar.close - atr * targetR;
    if (target <= 0) return null;
    return {
      symbol: context.symbol,
      strategyId: this.id,
      side: "short",
      entry: bar.close,
      stop,
      target,
      rr: targetR / stopR,
      confidence: 0.55,
      contracts: 1,
      maxHoldMinutes: 45,
      meta: {
        spikeAtrMultiple: ((spikeBar.high - spikeBar.low) / atr).toFixed(2),
        volDryUpRatio: (((settlementBar.volume ?? 0) / preVolAvg).toFixed(2)),
        strategy: "post-news-settlement",
      },
    };
  }
}
