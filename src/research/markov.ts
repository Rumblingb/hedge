import type { Bar } from "../domain.js";

export type MarkovSignal = "long" | "short" | "flat";

export interface MarkovReturnBacktestOptions {
  thresholds?: number[];
  minTrainingTransitions?: number;
  smoothing?: number;
  signalThreshold?: number;
  maxPredictionsPerSymbol?: number;
}

export interface MarkovReturnPrediction {
  symbol: string;
  predictedAtTs: string;
  targetTs: string;
  currentState: number;
  predictedState: number;
  predictedReturn: number;
  actualReturn: number;
  signal: MarkovSignal;
  hit: boolean;
  absError: number;
  squaredError: number;
  transitionCount: number;
  transitionProbabilities: number[];
}

export interface MarkovReturnSymbolReport {
  symbol: string;
  bars: number;
  returns: number;
  predictions: number;
  actionablePredictions: number;
  directionalAccuracy: number | null;
  actionableDirectionalAccuracy: number | null;
  mae: number | null;
  rmse: number | null;
  baselineMae: number | null;
  averagePredictedReturn: number | null;
  averageActualReturn: number | null;
  longSignals: number;
  shortSignals: number;
  flatSignals: number;
  stateLabels: string[];
  transitionCounts: number[][];
  latestPredictions: MarkovReturnPrediction[];
}

export interface MarkovReturnBacktestReport {
  model: "discrete-time-markov-return";
  options: Required<MarkovReturnBacktestOptions>;
  symbols: MarkovReturnSymbolReport[];
  aggregate: Omit<MarkovReturnSymbolReport, "symbol" | "bars" | "returns" | "stateLabels" | "transitionCounts" | "latestPredictions"> & {
    symbols: number;
    bars: number;
    returns: number;
  };
  notes: string[];
}

export interface MarkovOosOptions extends MarkovReturnBacktestOptions {
  trainReturns?: number;
  testReturns?: number;
  stepReturns?: number;
}

export interface MarkovOosWindowReport {
  symbol: string;
  window: number;
  trainStartTs: string;
  trainEndTs: string;
  testStartTs: string;
  testEndTs: string;
  trainReturns: number;
  testReturns: number;
  predictions: number;
  actionablePredictions: number;
  directionalAccuracy: number | null;
  actionableDirectionalAccuracy: number | null;
  mae: number | null;
  baselineMae: number | null;
  edgeMae: number | null;
  rmse: number | null;
  longSignals: number;
  shortSignals: number;
  flatSignals: number;
}

export interface MarkovOosSymbolReport {
  symbol: string;
  bars: number;
  returns: number;
  windows: number;
  predictions: number;
  actionablePredictions: number;
  directionalAccuracy: number | null;
  actionableDirectionalAccuracy: number | null;
  mae: number | null;
  baselineMae: number | null;
  edgeMae: number | null;
  rmse: number | null;
  longSignals: number;
  shortSignals: number;
  flatSignals: number;
  windowsWithPositiveEdge: number;
  edgeStability: number | null;
  latestWindows: MarkovOosWindowReport[];
}

export interface MarkovOosReport {
  model: "discrete-time-markov-return-oos";
  options: Required<MarkovOosOptions>;
  symbols: MarkovOosSymbolReport[];
  ranking: MarkovOosSymbolReport[];
  aggregate: Omit<MarkovOosSymbolReport, "symbol" | "bars" | "returns" | "latestWindows"> & {
    symbols: number;
    bars: number;
    returns: number;
  };
  notes: string[];
}

const DEFAULT_THRESHOLDS = [-0.015, -0.005, 0.005, 0.015];
const DEFAULT_MIN_TRAINING_TRANSITIONS = 60;
const DEFAULT_SMOOTHING = 1;
const DEFAULT_SIGNAL_THRESHOLD = 0.001;
const DEFAULT_MAX_PREDICTIONS_PER_SYMBOL = 12;
const DEFAULT_OOS_TRAIN_RETURNS = 20;
const DEFAULT_OOS_TEST_RETURNS = 5;
const DEFAULT_OOS_STEP_RETURNS = 5;

interface ReturnPoint {
  ts: string;
  previousTs: string;
  value: number;
}

interface PredictionAccumulator {
  predictions: number;
  actionablePredictions: number;
  directionalHits: number;
  directionalComparable: number;
  actionableHits: number;
  absError: number;
  squaredError: number;
  baselineAbsError: number;
  predictedReturn: number;
  actualReturn: number;
  longSignals: number;
  shortSignals: number;
  flatSignals: number;
}

function resolveOptions(options: MarkovReturnBacktestOptions = {}): Required<MarkovReturnBacktestOptions> {
  const thresholds = [...(options.thresholds ?? DEFAULT_THRESHOLDS)].sort((a, b) => a - b);
  if (thresholds.some((value) => !Number.isFinite(value))) {
    throw new Error("markov-return: thresholds must be finite numbers.");
  }

  return {
    thresholds,
    minTrainingTransitions: Math.max(2, Math.floor(options.minTrainingTransitions ?? DEFAULT_MIN_TRAINING_TRANSITIONS)),
    smoothing: Math.max(0, options.smoothing ?? DEFAULT_SMOOTHING),
    signalThreshold: Math.max(0, options.signalThreshold ?? DEFAULT_SIGNAL_THRESHOLD),
    maxPredictionsPerSymbol: Math.max(1, Math.floor(options.maxPredictionsPerSymbol ?? DEFAULT_MAX_PREDICTIONS_PER_SYMBOL))
  };
}

function resolveOosOptions(options: MarkovOosOptions = {}): Required<MarkovOosOptions> {
  const base = resolveOptions(options);
  const trainReturns = Math.max(3, Math.floor(options.trainReturns ?? DEFAULT_OOS_TRAIN_RETURNS));
  const testReturns = Math.max(1, Math.floor(options.testReturns ?? DEFAULT_OOS_TEST_RETURNS));
  return {
    ...base,
    trainReturns,
    testReturns,
    stepReturns: Math.max(1, Math.floor(options.stepReturns ?? testReturns))
  };
}

function stateCount(options: Required<MarkovReturnBacktestOptions>): number {
  return options.thresholds.length + 1;
}

function classifyReturn(value: number, thresholds: number[]): number {
  let state = 0;
  while (state < thresholds.length && value > thresholds[state]) {
    state += 1;
  }
  return state;
}

function stateLabels(thresholds: number[]): string[] {
  const labels: string[] = [];
  for (let index = 0; index <= thresholds.length; index += 1) {
    if (index === 0) {
      labels.push(`<=${formatPct(thresholds[0] ?? 0)}`);
    } else if (index === thresholds.length) {
      labels.push(`>${formatPct(thresholds[thresholds.length - 1] ?? 0)}`);
    } else {
      labels.push(`${formatPct(thresholds[index - 1] ?? 0)}..${formatPct(thresholds[index] ?? 0)}`);
    }
  }
  return labels;
}

function formatPct(value: number): string {
  return `${(value * 100).toFixed(2)}%`;
}

function groupBarsBySymbol(bars: Bar[]): Map<string, Bar[]> {
  const grouped = new Map<string, Bar[]>();
  for (const bar of bars) {
    const current = grouped.get(bar.symbol) ?? [];
    current.push(bar);
    grouped.set(bar.symbol, current);
  }

  for (const [symbol, symbolBars] of grouped) {
    grouped.set(
      symbol,
      [...symbolBars].sort((left, right) => Date.parse(left.ts) - Date.parse(right.ts))
    );
  }

  return grouped;
}

function buildReturns(bars: Bar[]): ReturnPoint[] {
  const returns: ReturnPoint[] = [];
  for (let index = 1; index < bars.length; index += 1) {
    const previous = bars[index - 1];
    const current = bars[index];
    if (!previous || !current || previous.close <= 0 || current.close <= 0) {
      continue;
    }
    returns.push({
      ts: current.ts,
      previousTs: previous.ts,
      value: (current.close / previous.close) - 1
    });
  }
  return returns;
}

function emptyMatrix(size: number): number[][] {
  return Array.from({ length: size }, () => Array.from({ length: size }, () => 0));
}

function emptyAccumulator(): PredictionAccumulator {
  return {
    predictions: 0,
    actionablePredictions: 0,
    directionalHits: 0,
    directionalComparable: 0,
    actionableHits: 0,
    absError: 0,
    squaredError: 0,
    baselineAbsError: 0,
    predictedReturn: 0,
    actualReturn: 0,
    longSignals: 0,
    shortSignals: 0,
    flatSignals: 0
  };
}

function sign(value: number): number {
  if (value > 0) return 1;
  if (value < 0) return -1;
  return 0;
}

function signalForPrediction(value: number, threshold: number): MarkovSignal {
  if (value > threshold) return "long";
  if (value < -threshold) return "short";
  return "flat";
}

function buildTrainingSnapshot(args: {
  returns: ReturnPoint[];
  targetIndex: number;
  thresholds: number[];
  size: number;
}): {
  currentState: number;
  matrix: number[][];
  nextReturnByState: Array<{ count: number; sum: number }>;
  globalMean: number;
} {
  const { returns, targetIndex, thresholds, size } = args;
  const matrix = emptyMatrix(size);
  const nextReturnByState = Array.from({ length: size }, () => ({ count: 0, sum: 0 }));
  let returnSum = 0;

  for (let index = 0; index < targetIndex; index += 1) {
    returnSum += returns[index]?.value ?? 0;
  }

  for (let index = 0; index < targetIndex - 1; index += 1) {
    const from = returns[index];
    const to = returns[index + 1];
    if (!from || !to) {
      continue;
    }
    const fromState = classifyReturn(from.value, thresholds);
    const toState = classifyReturn(to.value, thresholds);
    matrix[fromState][toState] += 1;
    nextReturnByState[fromState].count += 1;
    nextReturnByState[fromState].sum += to.value;
  }

  const previousReturn = returns[targetIndex - 1];
  if (!previousReturn) {
    throw new Error("markov-return: target index lacks a previous return.");
  }

  return {
    currentState: classifyReturn(previousReturn.value, thresholds),
    matrix,
    nextReturnByState,
    globalMean: returnSum / Math.max(1, targetIndex)
  };
}

function buildTransitionMatrix(returns: ReturnPoint[], thresholds: number[], size: number): number[][] {
  const matrix = emptyMatrix(size);
  for (let index = 0; index < returns.length - 1; index += 1) {
    const from = returns[index];
    const to = returns[index + 1];
    if (!from || !to) {
      continue;
    }
    matrix[classifyReturn(from.value, thresholds)][classifyReturn(to.value, thresholds)] += 1;
  }
  return matrix;
}

function transitionProbabilities(row: number[], smoothing: number): number[] {
  const denominator = row.reduce((sum, value) => sum + value, 0) + (smoothing * row.length);
  if (denominator <= 0) {
    return row.map(() => 1 / row.length);
  }
  return row.map((value) => (value + smoothing) / denominator);
}

function predictNextReturn(args: {
  trainReturns: ReturnPoint[];
  previousReturn: ReturnPoint;
  actualReturn: ReturnPoint;
  options: Required<MarkovReturnBacktestOptions>;
  size: number;
  symbol: string;
}): { prediction: MarkovReturnPrediction; baselineMean: number } {
  const { trainReturns, previousReturn, actualReturn, options, size, symbol } = args;
  const matrix = emptyMatrix(size);
  const nextReturnByState = Array.from({ length: size }, () => ({ count: 0, sum: 0 }));
  const baselineMean = trainReturns.reduce((sum, point) => sum + point.value, 0) / Math.max(1, trainReturns.length);

  for (let index = 0; index < trainReturns.length - 1; index += 1) {
    const from = trainReturns[index];
    const to = trainReturns[index + 1];
    if (!from || !to) {
      continue;
    }
    const fromState = classifyReturn(from.value, options.thresholds);
    const toState = classifyReturn(to.value, options.thresholds);
    matrix[fromState][toState] += 1;
    nextReturnByState[fromState].count += 1;
    nextReturnByState[fromState].sum += to.value;
  }

  const currentState = classifyReturn(previousReturn.value, options.thresholds);
  const row = matrix[currentState];
  const transitionCount = row.reduce((sum, value) => sum + value, 0);
  const conditional = nextReturnByState[currentState];
  const predictedReturn = (
    conditional.sum + (options.smoothing * baselineMean)
  ) / Math.max(1, conditional.count + options.smoothing);
  const probabilities = transitionProbabilities(row, options.smoothing);
  const predictedState = probabilities
    .map((probability, index) => ({ probability, index }))
    .sort((left, right) => right.probability - left.probability)[0]?.index ?? currentState;
  const signal = signalForPrediction(predictedReturn, options.signalThreshold);
  const hit = sign(predictedReturn) !== 0
    && sign(actualReturn.value) !== 0
    && sign(predictedReturn) === sign(actualReturn.value);

  return {
    baselineMean,
    prediction: {
      symbol,
      predictedAtTs: actualReturn.previousTs,
      targetTs: actualReturn.ts,
      currentState,
      predictedState,
      predictedReturn,
      actualReturn: actualReturn.value,
      signal,
      hit,
      absError: Math.abs(predictedReturn - actualReturn.value),
      squaredError: (predictedReturn - actualReturn.value) ** 2,
      transitionCount,
      transitionProbabilities: probabilities
    }
  };
}

function updateAccumulator(acc: PredictionAccumulator, prediction: MarkovReturnPrediction, baselineMean: number): void {
  acc.predictions += 1;
  acc.absError += prediction.absError;
  acc.squaredError += prediction.squaredError;
  acc.baselineAbsError += Math.abs(baselineMean - prediction.actualReturn);
  acc.predictedReturn += prediction.predictedReturn;
  acc.actualReturn += prediction.actualReturn;

  if (sign(prediction.predictedReturn) !== 0 && sign(prediction.actualReturn) !== 0) {
    acc.directionalComparable += 1;
    if (prediction.hit) {
      acc.directionalHits += 1;
    }
  }

  if (prediction.signal === "long") {
    acc.longSignals += 1;
    acc.actionablePredictions += 1;
    if (prediction.hit) acc.actionableHits += 1;
  } else if (prediction.signal === "short") {
    acc.shortSignals += 1;
    acc.actionablePredictions += 1;
    if (prediction.hit) acc.actionableHits += 1;
  } else {
    acc.flatSignals += 1;
  }
}

function finalizeMetrics(acc: PredictionAccumulator): Omit<MarkovReturnSymbolReport, "symbol" | "bars" | "returns" | "stateLabels" | "transitionCounts" | "latestPredictions"> {
  return {
    predictions: acc.predictions,
    actionablePredictions: acc.actionablePredictions,
    directionalAccuracy: acc.directionalComparable > 0 ? acc.directionalHits / acc.directionalComparable : null,
    actionableDirectionalAccuracy: acc.actionablePredictions > 0 ? acc.actionableHits / acc.actionablePredictions : null,
    mae: acc.predictions > 0 ? acc.absError / acc.predictions : null,
    rmse: acc.predictions > 0 ? Math.sqrt(acc.squaredError / acc.predictions) : null,
    baselineMae: acc.predictions > 0 ? acc.baselineAbsError / acc.predictions : null,
    averagePredictedReturn: acc.predictions > 0 ? acc.predictedReturn / acc.predictions : null,
    averageActualReturn: acc.predictions > 0 ? acc.actualReturn / acc.predictions : null,
    longSignals: acc.longSignals,
    shortSignals: acc.shortSignals,
    flatSignals: acc.flatSignals
  };
}

function finalizeOosMetrics(acc: PredictionAccumulator): Omit<MarkovOosWindowReport, "symbol" | "window" | "trainStartTs" | "trainEndTs" | "testStartTs" | "testEndTs" | "trainReturns" | "testReturns"> {
  const mae = acc.predictions > 0 ? acc.absError / acc.predictions : null;
  const baselineMae = acc.predictions > 0 ? acc.baselineAbsError / acc.predictions : null;
  return {
    predictions: acc.predictions,
    actionablePredictions: acc.actionablePredictions,
    directionalAccuracy: acc.directionalComparable > 0 ? acc.directionalHits / acc.directionalComparable : null,
    actionableDirectionalAccuracy: acc.actionablePredictions > 0 ? acc.actionableHits / acc.actionablePredictions : null,
    mae,
    baselineMae,
    edgeMae: mae !== null && baselineMae !== null ? baselineMae - mae : null,
    rmse: acc.predictions > 0 ? Math.sqrt(acc.squaredError / acc.predictions) : null,
    longSignals: acc.longSignals,
    shortSignals: acc.shortSignals,
    flatSignals: acc.flatSignals
  };
}

export function runMarkovReturnBacktest(
  bars: Bar[],
  optionsInput: MarkovReturnBacktestOptions = {}
): MarkovReturnBacktestReport {
  const options = resolveOptions(optionsInput);
  const size = stateCount(options);
  const labels = stateLabels(options.thresholds);
  const reports: MarkovReturnSymbolReport[] = [];
  const aggregateAcc = emptyAccumulator();
  let aggregateBars = 0;
  let aggregateReturns = 0;

  for (const [symbol, symbolBars] of groupBarsBySymbol(bars)) {
    const returns = buildReturns(symbolBars);
    const acc = emptyAccumulator();
    const latestPredictions: MarkovReturnPrediction[] = [];

    aggregateBars += symbolBars.length;
    aggregateReturns += returns.length;

    for (let targetIndex = options.minTrainingTransitions + 1; targetIndex < returns.length; targetIndex += 1) {
      const actual = returns[targetIndex];
      if (!actual) {
        continue;
      }
      const snapshot = buildTrainingSnapshot({
        returns,
        targetIndex,
        thresholds: options.thresholds,
        size
      });
      const row = snapshot.matrix[snapshot.currentState];
      const transitionCount = row.reduce((sum, value) => sum + value, 0);
      const conditional = snapshot.nextReturnByState[snapshot.currentState];
      const predictedReturn = (
        conditional.sum + (options.smoothing * snapshot.globalMean)
      ) / Math.max(1, conditional.count + options.smoothing);
      const probabilities = transitionProbabilities(row, options.smoothing);
      const predictedState = probabilities
        .map((probability, index) => ({ probability, index }))
        .sort((left, right) => right.probability - left.probability)[0]?.index ?? snapshot.currentState;
      const signal = signalForPrediction(predictedReturn, options.signalThreshold);
      const hit = sign(predictedReturn) !== 0
        && sign(actual.value) !== 0
        && sign(predictedReturn) === sign(actual.value);
      const prediction: MarkovReturnPrediction = {
        symbol,
        predictedAtTs: actual.previousTs,
        targetTs: actual.ts,
        currentState: snapshot.currentState,
        predictedState,
        predictedReturn,
        actualReturn: actual.value,
        signal,
        hit,
        absError: Math.abs(predictedReturn - actual.value),
        squaredError: (predictedReturn - actual.value) ** 2,
        transitionCount,
        transitionProbabilities: probabilities
      };

      updateAccumulator(acc, prediction, snapshot.globalMean);
      updateAccumulator(aggregateAcc, prediction, snapshot.globalMean);
      latestPredictions.push(prediction);
      if (latestPredictions.length > options.maxPredictionsPerSymbol) {
        latestPredictions.shift();
      }
    }

    reports.push({
      symbol,
      bars: symbolBars.length,
      returns: returns.length,
      ...finalizeMetrics(acc),
      stateLabels: labels,
      transitionCounts: buildTransitionMatrix(returns, options.thresholds, size),
      latestPredictions
    });
  }

  const aggregate = {
    symbols: reports.length,
    bars: aggregateBars,
    returns: aggregateReturns,
    ...finalizeMetrics(aggregateAcc)
  };

  return {
    model: "discrete-time-markov-return",
    options,
    symbols: reports,
    aggregate,
    notes: [
      "Predictions are generated walk-forward: each target return is scored using only earlier returns.",
      "Actual return is close-to-close: close[t] / close[t-1] - 1.",
      "This is research-only signal evidence. Do not route to live execution without promotion-gate review."
    ]
  };
}

export function runMarkovOosReport(
  bars: Bar[],
  optionsInput: MarkovOosOptions = {}
): MarkovOosReport {
  const options = resolveOosOptions(optionsInput);
  const size = stateCount(options);
  const reports: MarkovOosSymbolReport[] = [];
  const aggregateAcc = emptyAccumulator();
  let aggregateBars = 0;
  let aggregateReturns = 0;
  let aggregateWindows = 0;
  let aggregatePositiveWindows = 0;

  for (const [symbol, symbolBars] of groupBarsBySymbol(bars)) {
    const returns = buildReturns(symbolBars);
    const symbolAcc = emptyAccumulator();
    const latestWindows: MarkovOosWindowReport[] = [];
    let windowNumber = 0;
    let positiveWindows = 0;

    aggregateBars += symbolBars.length;
    aggregateReturns += returns.length;

    for (
      let trainStart = 0;
      trainStart + options.trainReturns + options.testReturns <= returns.length;
      trainStart += options.stepReturns
    ) {
      const trainEnd = trainStart + options.trainReturns;
      const testEnd = trainEnd + options.testReturns;
      const trainSlice = returns.slice(trainStart, trainEnd);
      const windowAcc = emptyAccumulator();
      windowNumber += 1;

      for (let targetIndex = trainEnd; targetIndex < testEnd; targetIndex += 1) {
        const previousReturn = returns[targetIndex - 1];
        const actualReturn = returns[targetIndex];
        if (!previousReturn || !actualReturn) {
          continue;
        }
        const { prediction, baselineMean } = predictNextReturn({
          trainReturns: trainSlice,
          previousReturn,
          actualReturn,
          options,
          size,
          symbol
        });
        updateAccumulator(windowAcc, prediction, baselineMean);
        updateAccumulator(symbolAcc, prediction, baselineMean);
        updateAccumulator(aggregateAcc, prediction, baselineMean);
      }

      const metrics = finalizeOosMetrics(windowAcc);
      if ((metrics.edgeMae ?? 0) > 0) {
        positiveWindows += 1;
        aggregatePositiveWindows += 1;
      }

      const report: MarkovOosWindowReport = {
        symbol,
        window: windowNumber,
        trainStartTs: trainSlice[0]?.ts ?? "",
        trainEndTs: trainSlice[trainSlice.length - 1]?.ts ?? "",
        testStartTs: returns[trainEnd]?.ts ?? "",
        testEndTs: returns[testEnd - 1]?.ts ?? "",
        trainReturns: trainSlice.length,
        testReturns: options.testReturns,
        ...metrics
      };

      latestWindows.push(report);
      if (latestWindows.length > options.maxPredictionsPerSymbol) {
        latestWindows.shift();
      }
    }

    aggregateWindows += windowNumber;
    const symbolMetrics = finalizeOosMetrics(symbolAcc);
    reports.push({
      symbol,
      bars: symbolBars.length,
      returns: returns.length,
      windows: windowNumber,
      ...symbolMetrics,
      windowsWithPositiveEdge: positiveWindows,
      edgeStability: windowNumber > 0 ? positiveWindows / windowNumber : null,
      latestWindows
    });
  }

  const ranking = [...reports].sort((left, right) => {
    const edgeDelta = (right.edgeMae ?? Number.NEGATIVE_INFINITY) - (left.edgeMae ?? Number.NEGATIVE_INFINITY);
    if (edgeDelta !== 0) return edgeDelta;
    return (right.directionalAccuracy ?? 0) - (left.directionalAccuracy ?? 0);
  });
  const aggregateMetrics = finalizeOosMetrics(aggregateAcc);

  return {
    model: "discrete-time-markov-return-oos",
    options,
    symbols: reports,
    ranking,
    aggregate: {
      symbols: reports.length,
      bars: aggregateBars,
      returns: aggregateReturns,
      windows: aggregateWindows,
      ...aggregateMetrics,
      windowsWithPositiveEdge: aggregatePositiveWindows,
      edgeStability: aggregateWindows > 0 ? aggregatePositiveWindows / aggregateWindows : null
    },
    notes: [
      "Each OOS window trains on a fixed past return window and scores the immediately following test returns.",
      "edgeMae is baselineMae - mae, so positive values mean the Markov forecast beat the rolling mean-return baseline.",
      "Ranking is research-only and should be used as a filter candidate, not as execution authority."
    ]
  };
}
