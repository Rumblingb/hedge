import { createHash } from "node:crypto";
import { mkdir, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import type { Bar } from "../domain.js";

export interface FeatureObservation {
  ts: string;
  symbol: string;
  featureVersion: string;
  features: Record<string, number>;
  forwardReturns: Record<string, number>;
}

export interface AlphaValidationFold {
  foldId: string;
  trainRows: number;
  testRows: number;
  trainIc: number;
  testIc: number;
  netEdgePct: number;
}

export interface AlphaRegimeValidation {
  regime: "low-vol" | "mid-vol" | "high-vol";
  observations: number;
  testIc: number;
  netEdgePct: number;
  verdict: "pass" | "fail";
}

export interface PaperAlphaStrategyDefinition {
  strategyId: string;
  source: "alpha-lab";
  status: "paper-only";
  symbol: string;
  feature: string;
  direction: "long" | "short";
  horizonBars: number;
  entryRule: string;
  exitRule: string;
  riskRule: string;
  promotionBlockers: string[];
}

export interface AlphaCandidate {
  candidateId: string;
  symbol: string;
  feature: string;
  horizonBars: number;
  direction: "long" | "short";
  trainIc: number;
  testIc: number;
  stability: number;
  observations: number;
  trainObservations: number;
  testObservations: number;
  featureCenter: number;
  purgedWalkforward: AlphaValidationFold[];
  cvMeanTestIc: number;
  cvPositiveFoldRate: number;
  cvMinNetEdgePct: number;
  regimeValidation: AlphaRegimeValidation[];
  meanForwardReturnPct: number;
  costStressPct: number;
  netEdgePct: number;
  paperStrategy: PaperAlphaStrategyDefinition | null;
  verdict: "research" | "shadow" | "reject";
  blockers: string[];
}

export interface AlphaLabReport {
  command: "alpha-lab";
  generatedAt: string;
  csvPath: string;
  featureStorePath: string | null;
  candidatePath: string | null;
  bars: number;
  symbols: string[];
  featureVersion: string;
  featureRows: number;
  horizonsBars: number[];
  trainFraction: number;
  purgeBars: number;
  costStressPct: number;
  topCandidates: AlphaCandidate[];
  blockers: string[];
}

export interface AlphaLabArgs {
  bars: Bar[];
  csvPath: string;
  featureStorePath?: string;
  candidatePath?: string;
  maxCandidates?: number;
  horizonsBars?: number[];
  trainFraction?: number;
  purgeBars?: number;
  costStressPct?: number;
  now?: () => string;
}

interface SymbolSeries {
  symbol: string;
  bars: Bar[];
}

const DEFAULT_HORIZONS = [5, 15, 30, 60];
const DEFAULT_FEATURE_STORE_PATH = ".rumbling-hedge/features/futures-alpha-features.latest.jsonl";
const DEFAULT_CANDIDATE_PATH = ".rumbling-hedge/state/alpha-lab.latest.json";
const FEATURE_SCHEMA = [
  "ret_1",
  "ret_5",
  "ret_15",
  "ret_30",
  "range_pct_5",
  "range_pct_15",
  "rv_15",
  "rv_30",
  "volume_z_20",
  "close_to_open_pct"
];

export function alphaFeatureVersion(horizonsBars: number[] = DEFAULT_HORIZONS): string {
  return createHash("sha256")
    .update(JSON.stringify({ schema: FEATURE_SCHEMA, horizonsBars: [...horizonsBars].sort((left, right) => left - right), version: 1 }))
    .digest("hex")
    .slice(0, 16);
}

function finite(value: number): number | null {
  return Number.isFinite(value) ? value : null;
}

function mean(values: number[]): number {
  return values.length === 0 ? 0 : values.reduce((sum, value) => sum + value, 0) / values.length;
}

function median(values: number[]): number {
  if (values.length === 0) return 0;
  const sorted = [...values].sort((left, right) => left - right);
  const middle = Math.floor(sorted.length / 2);
  return sorted.length % 2 === 0 ? (sorted[middle - 1] + sorted[middle]) / 2 : sorted[middle];
}

function std(values: number[]): number {
  if (values.length < 2) return 0;
  const avg = mean(values);
  const variance = mean(values.map((value) => (value - avg) ** 2));
  return Math.sqrt(variance);
}

function pctReturn(from: number, to: number): number {
  if (from <= 0 || to <= 0) return 0;
  return ((to - from) / from) * 100;
}

function correlation(left: number[], right: number[]): number {
  if (left.length !== right.length || left.length < 8) return 0;
  const leftMean = mean(left);
  const rightMean = mean(right);
  let numerator = 0;
  let leftDenominator = 0;
  let rightDenominator = 0;

  for (let index = 0; index < left.length; index += 1) {
    const leftDiff = left[index] - leftMean;
    const rightDiff = right[index] - rightMean;
    numerator += leftDiff * rightDiff;
    leftDenominator += leftDiff ** 2;
    rightDenominator += rightDiff ** 2;
  }

  const denominator = Math.sqrt(leftDenominator * rightDenominator);
  return denominator === 0 ? 0 : numerator / denominator;
}

function groupBarsBySymbol(bars: Bar[]): SymbolSeries[] {
  const groups = new Map<string, Bar[]>();
  for (const bar of bars) {
    const existing = groups.get(bar.symbol) ?? [];
    existing.push(bar);
    groups.set(bar.symbol, existing);
  }

  return Array.from(groups.entries())
    .map(([symbol, symbolBars]) => ({
      symbol,
      bars: [...symbolBars].sort((left, right) => Date.parse(left.ts) - Date.parse(right.ts))
    }))
    .sort((left, right) => left.symbol.localeCompare(right.symbol));
}

function rollingReturns(bars: Bar[], index: number, lookback: number): number | null {
  if (index < lookback) return null;
  return finite(pctReturn(bars[index - lookback].close, bars[index].close));
}

function rollingRangePct(bars: Bar[], index: number, lookback: number): number | null {
  if (index < lookback) return null;
  const window = bars.slice(index - lookback + 1, index + 1);
  const ranges = window.map((bar) => bar.close > 0 ? ((bar.high - bar.low) / bar.close) * 100 : 0);
  return finite(mean(ranges));
}

function rollingVolumeZ(bars: Bar[], index: number, lookback: number): number | null {
  if (index < lookback) return null;
  const prior = bars.slice(index - lookback, index).map((bar) => bar.volume);
  const sigma = std(prior);
  if (sigma === 0) return 0;
  return finite((bars[index].volume - mean(prior)) / sigma);
}

function rollingRealizedVol(bars: Bar[], index: number, lookback: number): number | null {
  if (index < lookback + 1) return null;
  const returns: number[] = [];
  for (let cursor = index - lookback + 1; cursor <= index; cursor += 1) {
    returns.push(pctReturn(bars[cursor - 1].close, bars[cursor].close));
  }
  return finite(std(returns));
}

function addFeature(target: Record<string, number>, key: string, value: number | null): void {
  if (value !== null && Number.isFinite(value)) {
    target[key] = Number(value.toFixed(8));
  }
}

interface AlphaPair {
  ts: string;
  feature: number;
  forward: number;
  regime: "low-vol" | "mid-vol" | "high-vol";
}

function regimeForRow(row: FeatureObservation): AlphaPair["regime"] {
  const rv = row.features.rv_30 ?? row.features.rv_15 ?? 0;
  if (rv >= 0.045) return "high-vol";
  if (rv <= 0.018) return "low-vol";
  return "mid-vol";
}

function signalSign(feature: number, featureCenter: number): number {
  const centered = feature - featureCenter;
  return centered === 0 ? 0 : Math.sign(centered);
}

function signedEdgePct(pairs: AlphaPair[], direction: "long" | "short", featureCenter: number): number {
  return mean(pairs.map((row) => signalSign(row.feature, featureCenter) * row.forward * (direction === "long" ? 1 : -1)));
}

function buildPurgedFolds(pairs: AlphaPair[], direction: "long" | "short", costStressPct: number, purgeBars: number): AlphaValidationFold[] {
  if (pairs.length < 160) return [];
  const folds = 4;
  const testSize = Math.floor(pairs.length / (folds + 1));
  const results: AlphaValidationFold[] = [];

  for (let fold = 0; fold < folds; fold += 1) {
    const testStart = testSize * (fold + 1);
    const testEnd = fold === folds - 1 ? pairs.length : Math.min(pairs.length, testStart + testSize);
    const train = pairs.filter((_, index) => index < testStart - purgeBars || index >= testEnd + purgeBars);
    const test = pairs.slice(testStart, testEnd);
    if (train.length < 40 || test.length < 20) continue;

    const trainIc = correlation(train.map((row) => row.feature), train.map((row) => row.forward));
    const testIc = correlation(test.map((row) => row.feature), test.map((row) => row.forward));
    const featureCenter = median(train.map((row) => row.feature));
    results.push({
      foldId: `purged-${fold + 1}`,
      trainRows: train.length,
      testRows: test.length,
      trainIc: Number(trainIc.toFixed(6)),
      testIc: Number(testIc.toFixed(6)),
      netEdgePct: Number((signedEdgePct(test, direction, featureCenter) - costStressPct).toFixed(6))
    });
  }

  return results;
}

function buildRegimeValidation(pairs: AlphaPair[], direction: "long" | "short", costStressPct: number, featureCenter: number): AlphaRegimeValidation[] {
  return (["low-vol", "mid-vol", "high-vol"] as const).map((regime) => {
    const regimePairs = pairs.filter((row) => row.regime === regime);
    const testIc = correlation(regimePairs.map((row) => row.feature), regimePairs.map((row) => row.forward));
    const netEdgePct = signedEdgePct(regimePairs, direction, featureCenter) - costStressPct;
    const icSignOk = testIc !== 0 && Math.sign(testIc) === (direction === "long" ? 1 : -1);
    return {
      regime,
      observations: regimePairs.length,
      testIc: Number(testIc.toFixed(6)),
      netEdgePct: Number(netEdgePct.toFixed(6)),
      verdict: regimePairs.length >= 40 && icSignOk && Math.abs(testIc) >= 0.02 && netEdgePct > 0 ? "pass" : "fail"
    };
  });
}

function paperStrategyFor(candidate: Omit<AlphaCandidate, "paperStrategy">): PaperAlphaStrategyDefinition | null {
  if (candidate.verdict !== "shadow") return null;
  return {
    strategyId: `alpha-lab-${candidate.symbol.toLowerCase()}-${candidate.feature.replace(/_/g, "-")}-${candidate.horizonBars}`,
    source: "alpha-lab",
    status: "paper-only",
    symbol: candidate.symbol,
    feature: candidate.feature,
    direction: candidate.direction,
    horizonBars: candidate.horizonBars,
    entryRule: `${candidate.direction} ${candidate.symbol} when ${candidate.feature} crosses its point-in-time center ${candidate.featureCenter}; threshold must be recalibrated out-of-sample before routing.`,
    exitRule: `Exit after ${candidate.horizonBars} bars or earlier if live execution quality degrades beyond modeled cost stress.`,
    riskRule: "Shadow/paper only; max one micro-equivalent probe until purged walk-forward, regime validation, and execution-quality evidence are promoted by separate gates.",
    promotionBlockers: [
      "paper-only-alpha-definition",
      "requires-purged-oos-repeat",
      "requires-execution-quality-analysis",
      "requires-portfolio-correlation-check"
    ]
  };
}

export function buildFuturesFeatureStore(bars: Bar[], horizonsBars: number[] = DEFAULT_HORIZONS): FeatureObservation[] {
  const rows: FeatureObservation[] = [];
  const maxHorizon = Math.max(...horizonsBars);
  const featureVersion = alphaFeatureVersion(horizonsBars);

  for (const series of groupBarsBySymbol(bars)) {
    for (let index = 30; index < series.bars.length - maxHorizon; index += 1) {
      const bar = series.bars[index];
      const features: Record<string, number> = {};
      const forwardReturns: Record<string, number> = {};

      addFeature(features, "ret_1", rollingReturns(series.bars, index, 1));
      addFeature(features, "ret_5", rollingReturns(series.bars, index, 5));
      addFeature(features, "ret_15", rollingReturns(series.bars, index, 15));
      addFeature(features, "ret_30", rollingReturns(series.bars, index, 30));
      addFeature(features, "range_pct_5", rollingRangePct(series.bars, index, 5));
      addFeature(features, "range_pct_15", rollingRangePct(series.bars, index, 15));
      addFeature(features, "rv_15", rollingRealizedVol(series.bars, index, 15));
      addFeature(features, "rv_30", rollingRealizedVol(series.bars, index, 30));
      addFeature(features, "volume_z_20", rollingVolumeZ(series.bars, index, 20));
      addFeature(features, "close_to_open_pct", bar.open > 0 ? ((bar.close - bar.open) / bar.open) * 100 : null);

      for (const horizon of horizonsBars) {
        forwardReturns[`fwd_ret_${horizon}`] = Number(pctReturn(bar.close, series.bars[index + horizon].close).toFixed(8));
      }

      rows.push({
        ts: bar.ts,
        symbol: series.symbol,
        featureVersion,
        features,
        forwardReturns
      });
    }
  }

  return rows;
}

function scoreCandidate(args: {
  rows: FeatureObservation[];
  symbol: string;
  feature: string;
  horizonBars: number;
  trainFraction: number;
  purgeBars: number;
  costStressPct: number;
}): AlphaCandidate {
  const pairs = args.rows
    .filter((row) => row.symbol === args.symbol)
    .map((row) => ({
      ts: row.ts,
      feature: row.features[args.feature],
      forward: row.forwardReturns[`fwd_ret_${args.horizonBars}`],
      regime: regimeForRow(row)
    }))
    .filter((row): row is AlphaPair => Number.isFinite(row.feature) && Number.isFinite(row.forward));

  const split = Math.max(8, Math.floor(pairs.length * args.trainFraction));
  const train = pairs.slice(0, split);
  const test = pairs.slice(split);
  const trainIc = correlation(train.map((row) => row.feature), train.map((row) => row.forward));
  const testIc = correlation(test.map((row) => row.feature), test.map((row) => row.forward));
  const direction: AlphaCandidate["direction"] = testIc >= 0 ? "long" : "short";
  const featureCenter = median(train.map((row) => row.feature));
  const purgedWalkforward = buildPurgedFolds(pairs, direction, args.costStressPct, args.purgeBars);
  const regimeValidation = buildRegimeValidation(test, direction, args.costStressPct, featureCenter);
  const cvMeanTestIc = mean(purgedWalkforward.map((fold) => fold.testIc));
  const cvPositiveFoldRate = purgedWalkforward.length === 0
    ? 0
    : purgedWalkforward.filter((fold) => Math.sign(fold.testIc) === Math.sign(testIc) && fold.netEdgePct > 0).length / purgedWalkforward.length;
  const cvMinNetEdgePct = purgedWalkforward.length === 0 ? 0 : Math.min(...purgedWalkforward.map((fold) => fold.netEdgePct));
  const meanForwardReturnPct = signedEdgePct(test, direction, featureCenter);
  const netEdgePct = meanForwardReturnPct - args.costStressPct;
  const stability = Math.max(0, 1 - Math.abs(trainIc - testIc));
  const blockers = [
    ...(pairs.length < 120 ? ["too-few-observations"] : []),
    ...(Math.abs(trainIc) < 0.03 ? ["weak-train-ic"] : []),
    ...(Math.abs(testIc) < 0.03 ? ["weak-test-ic"] : []),
    ...(Math.sign(trainIc) !== Math.sign(testIc) ? ["ic-sign-flip"] : []),
    ...(purgedWalkforward.length < 3 ? ["too-few-purged-folds"] : []),
    ...(cvPositiveFoldRate < 0.5 ? ["purged-fold-hit-rate-below-50pct"] : []),
    ...(cvMinNetEdgePct <= -args.costStressPct ? ["purged-fold-tail-edge-negative"] : []),
    ...(regimeValidation.filter((regime) => regime.verdict === "pass").length < 1 ? ["no-regime-bucket-survived"] : []),
    ...(netEdgePct <= 0 ? ["net-edge-after-costs-not-positive"] : [])
  ];
  const verdict: AlphaCandidate["verdict"] = blockers.length === 0 && Math.abs(testIc) >= 0.07 && netEdgePct > args.costStressPct
    ? "shadow"
    : blockers.length <= 1 && netEdgePct > 0
      ? "research"
      : "reject";
  const candidateWithoutStrategy: Omit<AlphaCandidate, "paperStrategy"> = {
    candidateId: `${args.symbol}:${args.feature}:${args.horizonBars}`,
    symbol: args.symbol,
    feature: args.feature,
    horizonBars: args.horizonBars,
    direction,
    trainIc: Number(trainIc.toFixed(6)),
    testIc: Number(testIc.toFixed(6)),
    stability: Number(stability.toFixed(6)),
    observations: pairs.length,
    trainObservations: train.length,
    testObservations: test.length,
    featureCenter: Number(featureCenter.toFixed(8)),
    purgedWalkforward,
    cvMeanTestIc: Number(cvMeanTestIc.toFixed(6)),
    cvPositiveFoldRate: Number(cvPositiveFoldRate.toFixed(6)),
    cvMinNetEdgePct: Number(cvMinNetEdgePct.toFixed(6)),
    regimeValidation,
    meanForwardReturnPct: Number(meanForwardReturnPct.toFixed(6)),
    costStressPct: args.costStressPct,
    netEdgePct: Number(netEdgePct.toFixed(6)),
    verdict,
    blockers
  };

  return {
    ...candidateWithoutStrategy,
    paperStrategy: paperStrategyFor(candidateWithoutStrategy)
  };
}

export function rankAlphaCandidates(args: {
  rows: FeatureObservation[];
  horizonsBars?: number[];
  trainFraction?: number;
  purgeBars?: number;
  costStressPct?: number;
  maxCandidates?: number;
}): AlphaCandidate[] {
  const horizons = args.horizonsBars ?? DEFAULT_HORIZONS;
  const trainFraction = args.trainFraction ?? 0.7;
  const purgeBars = args.purgeBars ?? Math.max(...horizons);
  const costStressPct = args.costStressPct ?? 0.015;
  const symbols = Array.from(new Set(args.rows.map((row) => row.symbol))).sort();
  const features = Array.from(new Set(args.rows.flatMap((row) => Object.keys(row.features)))).sort();
  const candidates: AlphaCandidate[] = [];

  for (const symbol of symbols) {
    for (const feature of features) {
      for (const horizonBars of horizons) {
        candidates.push(scoreCandidate({
          rows: args.rows,
          symbol,
          feature,
          horizonBars,
          trainFraction,
          purgeBars,
          costStressPct
        }));
      }
    }
  }

  return candidates
    .sort((left, right) => {
      const leftScore = Math.abs(left.testIc) * left.stability + Math.max(0, left.netEdgePct);
      const rightScore = Math.abs(right.testIc) * right.stability + Math.max(0, right.netEdgePct);
      return rightScore - leftScore;
    })
    .slice(0, args.maxCandidates ?? 25);
}

async function writeJsonl(path: string, rows: FeatureObservation[]): Promise<void> {
  await mkdir(dirname(path), { recursive: true });
  await writeFile(path, `${rows.map((row) => JSON.stringify(row)).join("\n")}\n`, "utf8");
}

async function writeJson(path: string, value: unknown): Promise<void> {
  await mkdir(dirname(path), { recursive: true });
  await writeFile(path, `${JSON.stringify(value, null, 2)}\n`, "utf8");
}

export async function buildAlphaLabReport(args: AlphaLabArgs): Promise<AlphaLabReport> {
  const horizonsBars = args.horizonsBars ?? DEFAULT_HORIZONS;
  const trainFraction = args.trainFraction ?? 0.7;
  const purgeBars = args.purgeBars ?? Math.max(...horizonsBars);
  const costStressPct = args.costStressPct ?? 0.015;
  const featureStorePath = resolve(args.featureStorePath ?? DEFAULT_FEATURE_STORE_PATH);
  const candidatePath = resolve(args.candidatePath ?? DEFAULT_CANDIDATE_PATH);
  const featureVersion = alphaFeatureVersion(horizonsBars);
  const rows = buildFuturesFeatureStore(args.bars, horizonsBars);
  const topCandidates = rankAlphaCandidates({
    rows,
    horizonsBars,
    trainFraction,
    purgeBars,
    costStressPct,
    maxCandidates: args.maxCandidates
  });
  const symbols = Array.from(new Set(args.bars.map((bar) => bar.symbol))).sort();
  const blockers = [
    ...(rows.length < 500 ? ["feature-store-too-small"] : []),
    ...(topCandidates.every((candidate) => candidate.verdict === "reject") ? ["no-alpha-candidate-survived-train-test-cost-stress"] : [])
  ];

  const report: AlphaLabReport = {
    command: "alpha-lab",
    generatedAt: args.now?.() ?? new Date().toISOString(),
    csvPath: args.csvPath,
    featureStorePath,
    candidatePath,
    bars: args.bars.length,
    symbols,
    featureVersion,
    featureRows: rows.length,
    horizonsBars,
    trainFraction,
    purgeBars,
    costStressPct,
    topCandidates,
    blockers
  };

  await writeJsonl(featureStorePath, rows);
  await writeJson(candidatePath, report);
  return report;
}
