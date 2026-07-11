import type { Bar } from "../domain.js";

export interface FiveMinuteEdgeBucket {
  label: string;
  count: number;
  upCount: number;
  downCount: number;
  flatCount: number;
  pUp: number;
  pGe: number;
  averageReturnBps: number;
}

export interface FiveMinuteEdgeSnapshot {
  ts: string;
  outcome: "up" | "down" | "flat";
  realizedReturnBps: number;
  priorTrendZ: number;
  priorVolBps: number;
}

export interface FiveMinuteEdgeReport {
  sampleSize: number;
  trendLookbackBars: number;
  volatilityLookbackBars: number;
  trendThresholdZ: number;
  volatilityMedianBps: number;
  unconditional: FiveMinuteEdgeBucket;
  states: FiveMinuteEdgeBucket[];
  latestSignal: {
    ts: string;
    trendState: "bullish" | "bearish" | "neutral";
    volatilityState: "high-vol" | "low-vol";
    priorTrendZ: number;
    priorVolBps: number;
  } | null;
  liveComparison?: {
    liveUpImplied: number;
    unconditionalEdgePct: number;
    stateEdgePct?: number;
    stateLabel?: string;
  };
}

function mean(values: number[]): number {
  if (values.length === 0) return 0;
  return values.reduce((sum, value) => sum + value, 0) / values.length;
}

function sampleStd(values: number[]): number {
  if (values.length < 2) return 0;
  const avg = mean(values);
  const variance = values.reduce((sum, value) => sum + ((value - avg) ** 2), 0) / (values.length - 1);
  return Math.sqrt(Math.max(0, variance));
}

function median(values: number[]): number {
  if (values.length === 0) return 0;
  const sorted = [...values].sort((left, right) => left - right);
  const mid = Math.floor(sorted.length / 2);
  return sorted.length % 2 === 0
    ? (sorted[mid - 1]! + sorted[mid]!) / 2
    : sorted[mid]!;
}

function toBps(value: number): number {
  return value * 10_000;
}

function classifyOutcome(bar: Bar): "up" | "down" | "flat" {
  if (bar.close > bar.open) return "up";
  if (bar.close < bar.open) return "down";
  return "flat";
}

function buildBucket(label: string, rows: FiveMinuteEdgeSnapshot[]): FiveMinuteEdgeBucket {
  const upCount = rows.filter((row) => row.outcome === "up").length;
  const downCount = rows.filter((row) => row.outcome === "down").length;
  const flatCount = rows.filter((row) => row.outcome === "flat").length;
  const count = rows.length;
  const geCount = upCount + flatCount;

  return {
    label,
    count,
    upCount,
    downCount,
    flatCount,
    pUp: count === 0 ? 0 : Number((upCount / count).toFixed(6)),
    pGe: count === 0 ? 0 : Number((geCount / count).toFixed(6)),
    averageReturnBps: Number(mean(rows.map((row) => row.realizedReturnBps)).toFixed(4))
  };
}

export function buildBtcFiveMinuteEdgeReport(args: {
  bars: Bar[];
  trendLookbackBars?: number;
  volatilityLookbackBars?: number;
  trendThresholdZ?: number;
  liveUpImplied?: number;
}): FiveMinuteEdgeReport {
  const trendLookbackBars = args.trendLookbackBars ?? 3;
  const volatilityLookbackBars = args.volatilityLookbackBars ?? 12;
  const trendThresholdZ = args.trendThresholdZ ?? 0.75;
  const bars = [...args.bars].sort((left, right) => Date.parse(left.ts) - Date.parse(right.ts));
  const minIndex = Math.max(trendLookbackBars, volatilityLookbackBars);
  const snapshots: FiveMinuteEdgeSnapshot[] = [];
  const priorVols: number[] = [];

  for (let index = minIndex; index < bars.length; index += 1) {
    const current = bars[index]!;
    const trendWindow = bars.slice(index - trendLookbackBars, index);
    const volWindow = bars.slice(index - volatilityLookbackBars, index);
    const trendStart = trendWindow[0]!;
    const trendEnd = trendWindow[trendWindow.length - 1]!;
    const priorTrendReturn = trendEnd.close / Math.max(trendStart.open, 1e-9) - 1;
    const volReturns = volWindow.map((bar) => bar.close / Math.max(bar.open, 1e-9) - 1);
    const perBarStd = sampleStd(volReturns);
    const aggregateStd = perBarStd * Math.sqrt(Math.max(1, trendLookbackBars));
    const priorTrendZ = aggregateStd > 1e-9 ? priorTrendReturn / aggregateStd : 0;
    const priorVolBps = toBps(perBarStd);
    priorVols.push(priorVolBps);

    snapshots.push({
      ts: current.ts,
      outcome: classifyOutcome(current),
      realizedReturnBps: Number(toBps(current.close / Math.max(current.open, 1e-9) - 1).toFixed(4)),
      priorTrendZ: Number(priorTrendZ.toFixed(6)),
      priorVolBps: Number(priorVolBps.toFixed(4))
    });
  }

  const volatilityMedianBps = Number(median(priorVols).toFixed(4));
  const classifyTrendState = (row: FiveMinuteEdgeSnapshot): "bullish" | "bearish" | "neutral" => {
    if (row.priorTrendZ >= trendThresholdZ) return "bullish";
    if (row.priorTrendZ <= -trendThresholdZ) return "bearish";
    return "neutral";
  };
  const classifyVolatilityState = (row: FiveMinuteEdgeSnapshot): "high-vol" | "low-vol" =>
    row.priorVolBps >= volatilityMedianBps ? "high-vol" : "low-vol";

  const unconditional = buildBucket("unconditional", snapshots);
  const stateRows = [
    buildBucket("bullish", snapshots.filter((row) => classifyTrendState(row) === "bullish")),
    buildBucket("bearish", snapshots.filter((row) => classifyTrendState(row) === "bearish")),
    buildBucket("neutral", snapshots.filter((row) => classifyTrendState(row) === "neutral")),
    buildBucket("high-vol", snapshots.filter((row) => classifyVolatilityState(row) === "high-vol")),
    buildBucket("low-vol", snapshots.filter((row) => classifyVolatilityState(row) === "low-vol")),
    buildBucket(
      "bullish-high-vol",
      snapshots.filter((row) => classifyTrendState(row) === "bullish" && classifyVolatilityState(row) === "high-vol")
    ),
    buildBucket(
      "bearish-high-vol",
      snapshots.filter((row) => classifyTrendState(row) === "bearish" && classifyVolatilityState(row) === "high-vol")
    )
  ].filter((bucket) => bucket.count > 0);

  const latest = snapshots[snapshots.length - 1];
  const liveComparison = args.liveUpImplied === undefined
    ? undefined
    : (() => {
        const matchingState = latest
          ? stateRows.find((bucket) =>
            bucket.label === `${classifyTrendState(latest)}-${classifyVolatilityState(latest)}`
            || bucket.label === classifyTrendState(latest)
          )
          : undefined;

        return {
          liveUpImplied: Number(args.liveUpImplied.toFixed(6)),
          unconditionalEdgePct: Number(((unconditional.pGe - args.liveUpImplied) * 100).toFixed(3)),
          stateEdgePct: matchingState
            ? Number(((matchingState.pGe - args.liveUpImplied) * 100).toFixed(3))
            : undefined,
          stateLabel: matchingState?.label
        };
      })();

  return {
    sampleSize: snapshots.length,
    trendLookbackBars,
    volatilityLookbackBars,
    trendThresholdZ,
    volatilityMedianBps,
    unconditional,
    states: stateRows,
    latestSignal: latest
      ? {
          ts: latest.ts,
          trendState: classifyTrendState(latest),
          volatilityState: classifyVolatilityState(latest),
          priorTrendZ: latest.priorTrendZ,
          priorVolBps: latest.priorVolBps
        }
      : null,
    ...(liveComparison ? { liveComparison } : {})
  };
}
