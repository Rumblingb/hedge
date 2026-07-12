import { mkdir, readFile, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { defaultCotCacheDir, fetchCotData, type CotReport, type CotSeries } from "./cot.js";
import { defaultGexOutDir, fetchDealerGamma, formatGexSummary, type DealerGammaReport } from "./dealerGamma.js";

export interface CotPositioningSummary {
  symbol: string;
  reportType: CotSeries["reportType"];
  latestDate?: string;
  dealerNet: number;
  dealerNetWow?: number;
  dealerNetZ52?: number;
  leveragedFundsNet: number;
  leveragedFundsNetWow?: number;
  largeSpecNet: number;
  largeSpecNetWow?: number;
  openInterest: number;
  interpretation: string;
}

export interface PositioningContextArtifact {
  command: "positioning-context";
  generatedAt: string;
  sources: {
    cot: string;
    dealerGamma: string;
    primeBrokerageProxy: string;
  };
  cot: {
    fetchedAt?: string;
    year?: number;
    symbols: CotPositioningSummary[];
  };
  dealerGamma: {
    reports: DealerGammaReport[];
    errors: string[];
  };
  strategyNotes: string[];
}

export function positioningContextLatestPath(env: NodeJS.ProcessEnv = process.env): string {
  return resolve(env.BILL_POSITIONING_CONTEXT_PATH ?? ".rumbling-hedge/research/positioning/latest.json");
}

export function positioningContextMarkdownPath(env: NodeJS.ProcessEnv = process.env): string {
  return resolve(env.BILL_POSITIONING_CONTEXT_MARKDOWN_PATH ?? ".rumbling-hedge/research/positioning/latest.md");
}

function summarizeCotSeries(series: CotSeries): CotPositioningSummary | null {
  const latest = series.records.at(-1);
  if (!latest) return null;
  const dealerZ = series.zScore52w?.dealerNet ?? 0;
  const levWow = series.weekOverWeekChange?.leveragedFundsNet ?? 0;
  const crowdedTrend = Math.abs(dealerZ) >= 1.5 || Math.abs(levWow) >= Math.max(10_000, latest.openInterest * 0.01);
  return {
    symbol: series.market,
    reportType: series.reportType,
    latestDate: series.latestDate,
    dealerNet: latest.dealerNet,
    dealerNetWow: series.weekOverWeekChange?.dealerNet,
    dealerNetZ52: series.zScore52w?.dealerNet,
    leveragedFundsNet: latest.leveragedFundsNet,
    leveragedFundsNetWow: series.weekOverWeekChange?.leveragedFundsNet,
    largeSpecNet: latest.largeSpecNet,
    largeSpecNetWow: series.weekOverWeekChange?.largeSpecNet,
    openInterest: latest.openInterest,
    interpretation: crowdedTrend
      ? "positioning is extended enough to require regime/risk filtering before adding exposure"
      : "positioning is present but not extreme enough to override intraday strategy gates"
  };
}

function buildStrategyNotes(args: {
  cot: CotPositioningSummary[];
  gammaReports: DealerGammaReport[];
  gammaErrors: string[];
}): string[] {
  const notes = [
    "Use COT as weekly regime/context only; never as an intraday entry trigger.",
    "Treat TFF dealer/intermediary and disaggregated swap-dealer categories as prime-brokerage/dealer proxies, not exact PB inventory.",
    "Use dealer gamma as index/ETF volatility context; paid greeks are preferred, Yahoo-derived gamma is approximate."
  ];
  const extendedCot = args.cot.filter((row) => Math.abs(row.dealerNetZ52 ?? 0) >= 1.5);
  if (extendedCot.length > 0) {
    notes.push(`COT extended dealer positioning: ${extendedCot.map((row) => `${row.symbol} z=${row.dealerNetZ52}`).join(", ")}.`);
  }
  const shortGamma = args.gammaReports.filter((report) => report.regime === "short-gamma");
  if (shortGamma.length > 0) {
    notes.push(`Short-gamma context detected in ${shortGamma.map((report) => report.underlying).join(", ")}; require tighter drawdown/session filters.`);
  }
  if (args.gammaErrors.length > 0) {
    notes.push(`Dealer gamma degraded for ${args.gammaErrors.length} source(s); do not promote gamma-conditioned strategies without fresh options data.`);
  }
  return notes;
}

export async function buildPositioningContext(args: {
  year?: number;
  cotReport?: CotReport;
  dealerGammaReports?: DealerGammaReport[];
  dealerGammaErrors?: string[];
} = {}): Promise<PositioningContextArtifact> {
  const cotReport = args.cotReport ?? await fetchCotData({
    year: args.year,
    cacheDir: defaultCotCacheDir()
  });
  const cot = [...cotReport.tff, ...cotReport.disaggregated]
    .map(summarizeCotSeries)
    .filter((row): row is CotPositioningSummary => Boolean(row));
  const gammaReports = args.dealerGammaReports ?? [];
  const gammaErrors = args.dealerGammaErrors ?? [];

  return {
    command: "positioning-context",
    generatedAt: new Date().toISOString(),
    sources: {
      cot: "CFTC historical compressed COT files",
      dealerGamma: "Polygon/Alpaca options greeks when available, Yahoo options chain with Black-Scholes gamma approximation as fallback",
      primeBrokerageProxy: "TFF Dealer/Intermediary for financial futures; Disaggregated Swap Dealer for commodities"
    },
    cot: {
      fetchedAt: cotReport.fetchedAt,
      year: cotReport.year,
      symbols: cot
    },
    dealerGamma: {
      reports: gammaReports,
      errors: gammaErrors
    },
    strategyNotes: buildStrategyNotes({ cot, gammaReports, gammaErrors })
  };
}

export async function fetchAndWritePositioningContext(args: {
  year?: number;
  underlyings?: string[];
  outputPath?: string;
  markdownPath?: string;
  env?: NodeJS.ProcessEnv;
} = {}): Promise<PositioningContextArtifact> {
  const env = args.env ?? process.env;
  const underlyings = args.underlyings ?? ["SPY", "QQQ", "IWM", "GLD", "TLT"];
  const gammaReports: DealerGammaReport[] = [];
  const gammaErrors: string[] = [];
  for (const underlying of underlyings) {
    try {
      gammaReports.push(await fetchDealerGamma({
        underlying,
        polygonApiKey: env.RH_POLYGON_API_KEY,
        apiKey: env.ALPACA_API_KEY,
        secretKey: env.ALPACA_SECRET_KEY ?? env.ALPACA_API_SECRET
      }));
    } catch (error) {
      gammaErrors.push(`${underlying}: ${error instanceof Error ? error.message : String(error)}`);
    }
  }

  const artifact = await buildPositioningContext({
    year: args.year,
    dealerGammaReports: gammaReports,
    dealerGammaErrors: gammaErrors
  });
  const outputPath = args.outputPath ?? positioningContextLatestPath(env);
  const markdownPath = args.markdownPath ?? positioningContextMarkdownPath(env);
  await mkdir(dirname(outputPath), { recursive: true });
  await mkdir(dirname(markdownPath), { recursive: true });
  await writeFile(outputPath, `${JSON.stringify(artifact, null, 2)}\n`, "utf8");
  await writeFile(markdownPath, `${formatPositioningContextMarkdown(artifact)}\n`, "utf8");
  return artifact;
}

export async function loadLatestPositioningContext(path = positioningContextLatestPath()): Promise<PositioningContextArtifact | null> {
  try {
    return JSON.parse(await readFile(path, "utf8")) as PositioningContextArtifact;
  } catch {
    return null;
  }
}

export function formatPositioningContextMarkdown(artifact: PositioningContextArtifact): string {
  return [
    "# Bill Positioning Context",
    "",
    `Generated: ${artifact.generatedAt}`,
    "",
    "## COT / Prime-Dealer Proxy",
    ...artifact.cot.symbols.map((row) =>
      `- ${row.symbol}: dealer=${row.dealerNet} wow=${row.dealerNetWow ?? "?"} z52=${row.dealerNetZ52 ?? "?"}; lev=${row.leveragedFundsNet} wow=${row.leveragedFundsNetWow ?? "?"}; ${row.interpretation}`
    ),
    "",
    "## Dealer Gamma",
    artifact.dealerGamma.reports.length > 0 ? formatGexSummary(artifact.dealerGamma.reports) : "- no dealer gamma reports available",
    ...(artifact.dealerGamma.errors.length > 0 ? ["", "## Gamma Errors", ...artifact.dealerGamma.errors.map((error) => `- ${error}`)] : []),
    "",
    "## Strategy Notes",
    ...artifact.strategyNotes.map((note) => `- ${note}`)
  ].join("\n");
}

export function defaultPositioningOutDir(): string {
  return ".rumbling-hedge/research/positioning";
}
