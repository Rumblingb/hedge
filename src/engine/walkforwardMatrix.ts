import { mkdir, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import type { Bar, LabConfig, SummaryReport, TradeRecord } from "../domain.js";
import type { NewsGate } from "../news/base.js";
import { mergeProfile, RESEARCH_PROFILES } from "../research/profiles.js";
import { buildDefaultEnsemble } from "../strategies/wctcEnsemble.js";
import { chicagoDateKey } from "../utils/time.js";
import { runBacktest } from "./backtest.js";
import { summarizeTrades } from "./report.js";

export type WalkforwardMatrixMode = "fixed" | "anchored";

export interface WalkforwardMatrixReport {
  command: "walkforward-matrix";
  generatedAt: string;
  outputPath: string;
  csvPath: string;
  status: "robust-candidate" | "research-only" | "reject";
  contract: {
    objective: string;
    selectionRule: string;
    rejectionCondition: string;
  };
  configs: WalkforwardMatrixConfigResult[];
  comparison: {
    bestConfigId: string | null;
    robustConfigCount: number;
    commonFailureModes: string[];
  };
  recommendation: string[];
}

export interface WalkforwardMatrixConfigResult {
  configId: string;
  mode: WalkforwardMatrixMode;
  trainDays: number;
  testDays: number;
  embargoDays: number;
  windowsEvaluated: number;
  stitchedOos: {
    totalTrades: number;
    netTotalR: number;
    profitFactor: number;
    sharpePerTrade: number;
    maxDrawdownR: number;
    cvar95TradeR: number;
    wfe: number;
    deployableWindows: number;
    positiveWindows: number;
  };
  sigmaStress: SigmaStressReport;
  windows: WalkforwardMatrixWindowResult[];
  failureModes: string[];
}

export interface WalkforwardMatrixWindowResult {
  windowId: number;
  trainStartDay: string;
  trainEndDay: string;
  testStartDay: string;
  testEndDay: string;
  selectedProfileId: string;
  trainScore: number;
  trainSummary: Pick<SummaryReport, "totalTrades" | "netTotalR" | "profitFactor" | "maxDrawdownR"> & {
    expectancyR: number;
    sharpePerTrade: number;
  };
  oosSummary: Pick<SummaryReport, "totalTrades" | "netTotalR" | "profitFactor" | "maxDrawdownR"> & {
    expectancyR: number;
    sharpePerTrade: number;
  };
}

export interface SigmaStressReport {
  meanTradeR: number;
  stdTradeR: number;
  observedWorstTradeR: number;
  observedTailBreaches: Record<"3sigma" | "4sigma" | "5sigma" | "6sigma", number>;
  oneShockEquityR: Record<"3sigma" | "4sigma" | "5sigma" | "6sigma", number>;
  note: string;
}

const DEFAULT_OUTPUT_PATH = ".rumbling-hedge/state/walkforward-matrix.latest.json";

function round(value: number): number {
  return Number(value.toFixed(4));
}

function uniqueDays(bars: Bar[]): string[] {
  return Array.from(new Set(bars.map((bar) => chicagoDateKey(bar.ts)))).sort();
}

function barsForDays(bars: Bar[], days: string[]): Bar[] {
  const set = new Set(days);
  return bars.filter((bar) => set.has(chicagoDateKey(bar.ts)));
}

function buildWindows(args: {
  bars: Bar[];
  mode: WalkforwardMatrixMode;
  trainDays: number;
  testDays: number;
  embargoDays: number;
  maxWindows: number;
}): Array<{ trainDays: string[]; testDays: string[] }> {
  const days = uniqueDays(args.bars);
  const out: Array<{ trainDays: string[]; testDays: string[] }> = [];
  let cursor = args.trainDays;

  while (out.length < args.maxWindows) {
    const trainStart = args.mode === "anchored" ? 0 : cursor - args.trainDays;
    const trainEnd = cursor;
    const testStart = trainEnd + args.embargoDays;
    const testEnd = testStart + args.testDays;
    if (trainStart < 0 || trainEnd <= trainStart || testEnd > days.length) break;
    out.push({
      trainDays: days.slice(trainStart, trainEnd),
      testDays: days.slice(testStart, testEnd)
    });
    cursor = testEnd;
  }

  return out;
}

function scoreTrainSummary(summary: SummaryReport): number {
  if (summary.totalTrades === 0) return -999;
  const pf = Math.min(3, Math.max(0, summary.profitFactor));
  const expectancy = summary.tradeQuality.expectancyR;
  const sharpe = summary.tradeQuality.sharpePerTrade;
  const tradeSupport = Math.min(1, summary.totalTrades / 20);
  return round(
    (summary.netTotalR * 0.45)
    + (expectancy * 8)
    + (pf * 0.8)
    + (sharpe * 1.2)
    + (tradeSupport * 1.5)
    - (summary.maxDrawdownR * 0.7)
    - (summary.frictionR * 0.25)
  );
}

function compactSummary(summary: SummaryReport): WalkforwardMatrixWindowResult["trainSummary"] {
  return {
    totalTrades: summary.totalTrades,
    netTotalR: round(summary.netTotalR),
    profitFactor: round(summary.profitFactor),
    maxDrawdownR: round(summary.maxDrawdownR),
    expectancyR: round(summary.tradeQuality.expectancyR),
    sharpePerTrade: round(summary.tradeQuality.sharpePerTrade)
  };
}

function annualizedEfficiency(args: {
  isNetR: number;
  isDays: number;
  oosNetR: number;
  oosDays: number;
}): number {
  const isRate = args.isDays > 0 ? args.isNetR / args.isDays : 0;
  const oosRate = args.oosDays > 0 ? args.oosNetR / args.oosDays : 0;
  if (isRate <= 0) return oosRate > 0 ? 1 : 0;
  return round(oosRate / isRate);
}

function sampleStd(values: number[]): number {
  if (values.length < 2) return 0;
  const mean = values.reduce((sum, value) => sum + value, 0) / values.length;
  const variance = values.reduce((sum, value) => sum + ((value - mean) ** 2), 0) / (values.length - 1);
  return Math.sqrt(Math.max(0, variance));
}

function buildSigmaStress(trades: TradeRecord[], stitched: SummaryReport): SigmaStressReport {
  const values = trades.map((trade) => trade.netRMultiple);
  const mean = values.length === 0 ? 0 : values.reduce((sum, value) => sum + value, 0) / values.length;
  const std = sampleStd(values);
  const thresholds = {
    "3sigma": mean - (3 * std),
    "4sigma": mean - (4 * std),
    "5sigma": mean - (5 * std),
    "6sigma": mean - (6 * std)
  };
  const breaches = Object.fromEntries(
    Object.entries(thresholds).map(([key, threshold]) => [key, values.filter((value) => value <= threshold).length])
  ) as SigmaStressReport["observedTailBreaches"];
  const oneShockEquity = Object.fromEntries(
    Object.entries(thresholds).map(([key, shock]) => [key, round(stitched.netTotalR + shock)])
  ) as SigmaStressReport["oneShockEquityR"];

  return {
    meanTradeR: round(mean),
    stdTradeR: round(std),
    observedWorstTradeR: round(values.length > 0 ? Math.min(...values) : 0),
    observedTailBreaches: breaches,
    oneShockEquityR: oneShockEquity,
    note: "Gaussian sigma shocks are a stress lens, not a probability model; markets have fat tails and correlated failures."
  };
}

function failureModes(args: {
  stitched: SummaryReport;
  wfe: number;
  windows: WalkforwardMatrixWindowResult[];
}): string[] {
  return [
    ...(args.windows.length < 4 ? ["too-few-walkforward-windows"] : []),
    ...(args.stitched.totalTrades < 20 ? ["stitched-oos-sample-too-thin"] : []),
    ...(args.stitched.netTotalR <= 0 ? ["stitched-oos-net-negative"] : []),
    ...(args.stitched.profitFactor < 1.4 ? ["profit-factor-below-contract"] : []),
    ...(args.stitched.tradeQuality.sharpePerTrade < 0.15 ? ["weak-oos-sharpe"] : []),
    ...(args.stitched.maxDrawdownR > 4 ? ["oos-drawdown-too-high"] : []),
    ...(args.wfe < 0.5 ? ["walkforward-efficiency-below-0.5"] : []),
    ...(args.windows.filter((window) => window.oosSummary.netTotalR > 0).length < Math.ceil(args.windows.length * 0.6) ? ["too-few-positive-oos-windows"] : [])
  ];
}

async function evaluateConfig(args: {
  bars: Bar[];
  baseConfig: LabConfig;
  newsGate: NewsGate;
  mode: WalkforwardMatrixMode;
  trainDays: number;
  testDays: number;
  embargoDays: number;
  maxWindows: number;
  configId: string;
}): Promise<WalkforwardMatrixConfigResult> {
  const rawWindows = buildWindows(args);
  const windows: WalkforwardMatrixWindowResult[] = [];
  const selectedOosTrades: TradeRecord[] = [];
  let selectedTrainNetR = 0;
  let selectedTrainDays = 0;
  let selectedOosNetR = 0;
  let selectedOosDays = 0;

  for (let index = 0; index < rawWindows.length; index += 1) {
    const window = rawWindows[index]!;
    const trainBars = barsForDays(args.bars, window.trainDays);
    const testBars = barsForDays(args.bars, window.testDays);
    const candidates = [];

    for (const profile of RESEARCH_PROFILES) {
      const config = mergeProfile(args.baseConfig, profile);
      const train = await runBacktest({
        bars: trainBars,
        strategy: buildDefaultEnsemble(config),
        config,
        newsGate: args.newsGate
      });
      const trainSummary = summarizeTrades(train.trades);
      candidates.push({ profile, config, trainSummary, trainScore: scoreTrainSummary(trainSummary) });
    }

    candidates.sort((left, right) => right.trainScore - left.trainScore);
    const selected = candidates[0];
    if (!selected) continue;
    const oos = await runBacktest({
      bars: testBars,
      strategy: buildDefaultEnsemble(selected.config),
      config: selected.config,
      newsGate: args.newsGate
    });
    const oosSummary = summarizeTrades(oos.trades);
    selectedOosTrades.push(...oos.trades);
    selectedTrainNetR += selected.trainSummary.netTotalR;
    selectedTrainDays += window.trainDays.length;
    selectedOosNetR += oosSummary.netTotalR;
    selectedOosDays += window.testDays.length;

    windows.push({
      windowId: index + 1,
      trainStartDay: window.trainDays[0] ?? "",
      trainEndDay: window.trainDays.at(-1) ?? "",
      testStartDay: window.testDays[0] ?? "",
      testEndDay: window.testDays.at(-1) ?? "",
      selectedProfileId: selected.profile.id,
      trainScore: selected.trainScore,
      trainSummary: compactSummary(selected.trainSummary),
      oosSummary: compactSummary(oosSummary)
    });
  }

  const stitched = summarizeTrades(selectedOosTrades);
  const wfe = annualizedEfficiency({
    isNetR: selectedTrainNetR,
    isDays: selectedTrainDays,
    oosNetR: selectedOosNetR,
    oosDays: selectedOosDays
  });
  const failures = failureModes({ stitched, wfe, windows });

  return {
    configId: args.configId,
    mode: args.mode,
    trainDays: args.trainDays,
    testDays: args.testDays,
    embargoDays: args.embargoDays,
    windowsEvaluated: windows.length,
    stitchedOos: {
      totalTrades: stitched.totalTrades,
      netTotalR: round(stitched.netTotalR),
      profitFactor: round(stitched.profitFactor),
      sharpePerTrade: round(stitched.tradeQuality.sharpePerTrade),
      maxDrawdownR: round(stitched.maxDrawdownR),
      cvar95TradeR: round(stitched.tradeQuality.cvar95TradeR),
      wfe,
      deployableWindows: windows.filter((window) =>
        window.oosSummary.totalTrades >= 4
        && window.oosSummary.netTotalR > 0
        && window.oosSummary.profitFactor >= 1.2
      ).length,
      positiveWindows: windows.filter((window) => window.oosSummary.netTotalR > 0).length
    },
    sigmaStress: buildSigmaStress(selectedOosTrades, stitched),
    windows,
    failureModes: failures
  };
}

export async function buildWalkforwardMatrixReport(args: {
  bars: Bar[];
  baseConfig: LabConfig;
  newsGate: NewsGate;
  csvPath: string;
  outputPath?: string;
  maxWindows?: number;
  now?: () => string;
}): Promise<WalkforwardMatrixReport> {
  const generatedAt = args.now?.() ?? new Date().toISOString();
  const outputPath = resolve(args.outputPath ?? process.env.BILL_WALKFORWARD_MATRIX_PATH ?? DEFAULT_OUTPUT_PATH);
  const maxWindows = Math.max(1, args.maxWindows ?? Number.parseInt(process.env.BILL_WALKFORWARD_MATRIX_MAX_WINDOWS ?? "8", 10));
  const configsToRun = [
    { configId: "fixed-20d-5d", mode: "fixed" as const, trainDays: 20, testDays: 5, embargoDays: 1 },
    { configId: "anchored-20d-5d", mode: "anchored" as const, trainDays: 20, testDays: 5, embargoDays: 1 },
    { configId: "fixed-10d-5d", mode: "fixed" as const, trainDays: 10, testDays: 5, embargoDays: 1 },
    { configId: "fixed-30d-3d", mode: "fixed" as const, trainDays: 30, testDays: 3, embargoDays: 1 }
  ];
  const configs = [];

  for (const config of configsToRun) {
    configs.push(await evaluateConfig({
      bars: args.bars,
      baseConfig: args.baseConfig,
      newsGate: args.newsGate,
      maxWindows,
      ...config
    }));
  }

  const robust = configs.filter((config) => config.failureModes.length === 0);
  const ranked = [...configs].sort((left, right) =>
    left.failureModes.length - right.failureModes.length
    || right.stitchedOos.netTotalR - left.stitchedOos.netTotalR
    || right.stitchedOos.wfe - left.stitchedOos.wfe
  );
  const commonFailureModes = Array.from(new Set(configs.flatMap((config) => config.failureModes)));
  const status: WalkforwardMatrixReport["status"] = robust.length > 0
    ? "robust-candidate"
    : configs.some((config) => config.stitchedOos.netTotalR > 0 && config.stitchedOos.wfe >= 0.5)
      ? "research-only"
      : "reject";

  const report: WalkforwardMatrixReport = {
    command: "walkforward-matrix",
    generatedAt,
    outputPath,
    csvPath: resolve(args.csvPath),
    status,
    contract: {
      objective: "Compare fixed, anchored, stitched pseudo-live, and varying IS/OOS walk-forward tests without selecting profiles on OOS data.",
      selectionRule: "For each window, choose the best research profile by train-only score, then stitch only unseen OOS trades.",
      rejectionCondition: "Reject if stitched OOS is net negative, WFE < 0.5, PF < 1.4, sample < 20 trades, drawdown > 4R, or fewer than 60% positive OOS windows."
    },
    configs,
    comparison: {
      bestConfigId: ranked[0]?.configId ?? null,
      robustConfigCount: robust.length,
      commonFailureModes
    },
    recommendation: [
      ...(status === "robust-candidate" ? ["Promote the best matrix config to a clean spec and rerun live-readiness stress."] : []),
      ...(status !== "robust-candidate" ? ["Do not use this matrix as permission to widen demo/live risk; use it to choose the next research branch."] : []),
      "Use stitched OOS as the pseudo-live equity curve; individual green windows are insufficient.",
      "Treat 6-sigma output as a capital survival stress, not a forecast probability."
    ]
  };

  await mkdir(dirname(outputPath), { recursive: true });
  await writeFile(outputPath, `${JSON.stringify(report, null, 2)}\n`, "utf8");
  return report;
}
