import { mkdir, readFile, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import type { MacroContextSnapshot } from "../domain.js";

export interface FreeMacroPoint {
  ts: string;
  value: number;
}

export interface FreeMacroSeries {
  id: string;
  yahooSymbol: string;
  title: string;
  points: FreeMacroPoint[];
  latest: FreeMacroPoint | null;
  previous: FreeMacroPoint | null;
  change1dPct: number | null;
  change20dPct: number | null;
  change60dPct: number | null;
  warning?: string;
}

export interface FreeMacroContextReport {
  command: "macro-context-free";
  generatedAt: string;
  outputPath: string;
  csvPath: string;
  source: "yahoo-public-chart";
  range: string;
  series: FreeMacroSeries[];
  derived: {
    tailScore: number;
    riskRegime: "normal" | "elevated" | "stress";
    vixLevel: number | null;
    vixTermStructure: "contango" | "backwardation" | "unknown";
    vix3mMinusVix: number | null;
    yieldCurveProxyBps: number | null;
    creditRiskProxy: "normal" | "weakening" | "unknown";
    equityTrendProxy: "risk-on" | "risk-off" | "unknown";
    notes: string[];
  };
}

const DEFAULT_OUTPUT_PATH = ".rumbling-hedge/research/macro/free-macro-context.latest.json";
const DEFAULT_CSV_PATH = "data/research/macro/free-macro-context.latest.csv";

const DEFAULT_SERIES = [
  { id: "vix", yahooSymbol: "^VIX", title: "CBOE VIX" },
  { id: "vix3m", yahooSymbol: "^VIX3M", title: "CBOE 3M VIX" },
  { id: "tnx", yahooSymbol: "^TNX", title: "10Y Treasury yield proxy" },
  { id: "fvx", yahooSymbol: "^FVX", title: "5Y Treasury yield proxy" },
  { id: "irx", yahooSymbol: "^IRX", title: "13W Treasury bill yield proxy" },
  { id: "dxy", yahooSymbol: "DX-Y.NYB", title: "US Dollar Index" },
  { id: "hyg", yahooSymbol: "HYG", title: "High yield credit ETF" },
  { id: "lqd", yahooSymbol: "LQD", title: "Investment grade credit ETF" },
  { id: "spy", yahooSymbol: "SPY", title: "S&P 500 ETF" },
  { id: "tlt", yahooSymbol: "TLT", title: "Long Treasury ETF" }
] as const;

function finite(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function pctChange(latest: FreeMacroPoint | null, prior: FreeMacroPoint | null): number | null {
  if (!latest || !prior || prior.value === 0) return null;
  return Number((((latest.value / prior.value) - 1) * 100).toFixed(2));
}

function getLookback(points: FreeMacroPoint[], sessions: number): FreeMacroPoint | null {
  if (points.length <= sessions) return null;
  return points[points.length - 1 - sessions] ?? null;
}

export function parseYahooMacroChart(args: { payload: unknown }): FreeMacroPoint[] {
  const data = args.payload as {
    chart?: {
      result?: Array<{
        timestamp?: number[];
        indicators?: { quote?: Array<{ close?: Array<number | null> }> };
      }>;
      error?: { description?: string } | null;
    };
  };
  if (data.chart?.error) {
    throw new Error(data.chart.error.description ?? "Yahoo returned an error.");
  }
  const first = data.chart?.result?.[0];
  const closes = first?.indicators?.quote?.[0]?.close;
  if (!first?.timestamp || !closes) {
    throw new Error("Yahoo macro response missing timestamps or closes.");
  }
  const points: FreeMacroPoint[] = [];
  first.timestamp.forEach((epoch, index) => {
    const value = finite(closes[index]);
    if (value === null) return;
    points.push({ ts: new Date(epoch * 1000).toISOString(), value });
  });
  return points;
}

export function summarizeFreeMacroSeries(args: {
  id: string;
  yahooSymbol: string;
  title: string;
  points: FreeMacroPoint[];
  warning?: string;
}): FreeMacroSeries {
  const latest = args.points.at(-1) ?? null;
  const previous = args.points.at(-2) ?? null;
  return {
    id: args.id,
    yahooSymbol: args.yahooSymbol,
    title: args.title,
    points: args.points,
    latest,
    previous,
    change1dPct: pctChange(latest, previous),
    change20dPct: pctChange(latest, getLookback(args.points, 20)),
    change60dPct: pctChange(latest, getLookback(args.points, 60)),
    ...(args.warning ? { warning: args.warning } : {})
  };
}

function byId(series: FreeMacroSeries[], id: string): FreeMacroSeries | null {
  return series.find((item) => item.id === id) ?? null;
}

function latestValue(series: FreeMacroSeries[], id: string): number | null {
  return byId(series, id)?.latest?.value ?? null;
}

export function deriveFreeMacroContext(series: FreeMacroSeries[]): FreeMacroContextReport["derived"] {
  const vix = latestValue(series, "vix");
  const vix3m = latestValue(series, "vix3m");
  const tnx = latestValue(series, "tnx");
  const fvx = latestValue(series, "fvx");
  const irx = latestValue(series, "irx");
  const hyg = byId(series, "hyg");
  const lqd = byId(series, "lqd");
  const spy = byId(series, "spy");
  const notes: string[] = [];

  const vix3mMinusVix = vix !== null && vix3m !== null ? Number((vix3m - vix).toFixed(2)) : null;
  const vixTermStructure = vix3mMinusVix === null ? "unknown" : vix3mMinusVix < 0 ? "backwardation" : "contango";
  const yieldCurveProxyBps = tnx !== null && (fvx !== null || irx !== null)
    ? Number(((tnx - (fvx ?? irx ?? tnx)) * 100).toFixed(1))
    : null;
  const creditSpreadProxy20d = hyg?.change20dPct != null && lqd?.change20dPct != null
    ? Number((hyg.change20dPct - lqd.change20dPct).toFixed(2))
    : null;
  const creditRiskProxy = creditSpreadProxy20d === null ? "unknown" : creditSpreadProxy20d < -2 ? "weakening" : "normal";
  const equityTrendProxy = spy?.change20dPct === null ? "unknown" : (spy?.change20dPct ?? 0) < -4 ? "risk-off" : "risk-on";

  let tailScore = 0;
  if (vix !== null) {
    tailScore += Math.max(0, Math.min(35, (vix - 14) * 2.1));
    if (vix >= 25) notes.push("VIX is above the stress watch zone.");
    if (vix >= 32) notes.push("VIX is in outright stress territory.");
  }
  if (vixTermStructure === "backwardation") {
    tailScore += 28;
    notes.push("VIX curve is backwardated; reduce directional risk before adding new exposure.");
  }
  if (yieldCurveProxyBps !== null && yieldCurveProxyBps < 0) {
    tailScore += 12;
    notes.push("Yield-curve proxy is inverted.");
  }
  if (creditRiskProxy === "weakening") {
    tailScore += 15;
    notes.push("High-yield credit is weakening versus investment-grade credit.");
  }
  if (equityTrendProxy === "risk-off") {
    tailScore += 10;
    notes.push("SPY 20-session trend is risk-off.");
  }
  const roundedTailScore = Math.min(100, Math.max(0, Number(tailScore.toFixed(1))));
  if (notes.length === 0) notes.push("No free macro proxy is currently flagging acute tail stress.");
  return {
    tailScore: roundedTailScore,
    riskRegime: roundedTailScore >= 65 ? "stress" : roundedTailScore >= 35 ? "elevated" : "normal",
    vixLevel: vix,
    vixTermStructure,
    vix3mMinusVix,
    yieldCurveProxyBps,
    creditRiskProxy,
    equityTrendProxy,
    notes
  };
}

async function fetchYahooMacroSeries(args: {
  id: string;
  yahooSymbol: string;
  title: string;
  range: string;
  timeoutMs: number;
}): Promise<FreeMacroSeries> {
  try {
    const url = new URL(`https://query1.finance.yahoo.com/v8/finance/chart/${encodeURIComponent(args.yahooSymbol)}`);
    url.searchParams.set("interval", "1d");
    url.searchParams.set("range", args.range);
    const response = await fetch(url, { signal: AbortSignal.timeout(args.timeoutMs), headers: { "user-agent": "rumbling-hedge/0.1" } });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const points = parseYahooMacroChart({ payload: await response.json() });
    if (points.length === 0) throw new Error("no valid points");
    return summarizeFreeMacroSeries({ ...args, points });
  } catch (error) {
    return summarizeFreeMacroSeries({ ...args, points: [], warning: error instanceof Error ? error.message : String(error) });
  }
}

function toCsv(report: FreeMacroContextReport): string {
  const rows = ["series_id,yahoo_symbol,ts,value,change_1d_pct,change_20d_pct,change_60d_pct"];
  for (const series of report.series) {
    if (!series.latest) continue;
    rows.push([series.id, series.yahooSymbol, series.latest.ts, series.latest.value, series.change1dPct ?? "", series.change20dPct ?? "", series.change60dPct ?? ""].join(","));
  }
  return `${rows.join("\n")}\n`;
}

export async function buildFreeMacroContextReport(args: {
  outputPath?: string;
  csvPath?: string;
  range?: string;
  now?: () => string;
  timeoutMs?: number;
} = {}): Promise<FreeMacroContextReport> {
  const outputPath = resolve(args.outputPath ?? DEFAULT_OUTPUT_PATH);
  const csvPath = resolve(args.csvPath ?? DEFAULT_CSV_PATH);
  const range = args.range ?? "6mo";
  const generatedAt = args.now?.() ?? new Date().toISOString();
  const timeoutMs = args.timeoutMs ?? 10_000;
  const series = await Promise.all(DEFAULT_SERIES.map((item) => fetchYahooMacroSeries({ ...item, range, timeoutMs })));
  const report: FreeMacroContextReport = {
    command: "macro-context-free",
    generatedAt,
    outputPath,
    csvPath,
    source: "yahoo-public-chart",
    range,
    series,
    derived: deriveFreeMacroContext(series)
  };
  await mkdir(dirname(outputPath), { recursive: true });
  await mkdir(dirname(csvPath), { recursive: true });
  await writeFile(outputPath, `${JSON.stringify(report, null, 2)}\n`, "utf8");
  await writeFile(csvPath, toCsv(report), "utf8");
  return report;
}

export function freeMacroReportToSnapshot(report: FreeMacroContextReport): MacroContextSnapshot {
  return {
    source: "free-macro-context",
    generatedAt: report.generatedAt,
    tailScore: report.derived.tailScore,
    riskRegime: report.derived.riskRegime,
    vixLevel: report.derived.vixLevel,
    vixTermStructure: report.derived.vixTermStructure,
    yieldCurveProxyBps: report.derived.yieldCurveProxyBps,
    creditRiskProxy: report.derived.creditRiskProxy,
    equityTrendProxy: report.derived.equityTrendProxy
  };
}

export async function loadLatestFreeMacroContextSnapshot(args: {
  path?: string;
  env?: NodeJS.ProcessEnv;
} = {}): Promise<MacroContextSnapshot | null> {
  const artifactPath = resolve(args.path ?? args.env?.BILL_FREE_MACRO_CONTEXT_PATH ?? DEFAULT_OUTPUT_PATH);
  try {
    const raw = await readFile(artifactPath, "utf8");
    const parsed = JSON.parse(raw) as FreeMacroContextReport;
    if (parsed.command !== "macro-context-free" || !parsed.derived) {
      return null;
    }
    return freeMacroReportToSnapshot(parsed);
  } catch {
    return null;
  }
}
