import type { Bar } from "../domain.js";

export interface DataQualityOptions {
  minCoveragePct: number;
  maxEndLagMinutes: number;
  requiredSymbols: string[];
}

export interface SymbolQuality {
  symbol: string;
  rows: number;
  coveragePct: number;
  startTs?: string;
  endTs?: string;
  endLagMinutes: number;
}

export interface DataQualityCheck {
  name: string;
  passed: boolean;
  reason: string;
}

export interface DataQualityReport {
  totalRows: number;
  symbols: string[];
  startTs?: string;
  endTs?: string;
  expectedStepSeconds?: number;
  options: DataQualityOptions;
  symbolQuality: SymbolQuality[];
  checks: DataQualityCheck[];
  pass: boolean;
}

const DEFAULT_OPTIONS: DataQualityOptions = {
  minCoveragePct: 0.95,
  maxEndLagMinutes: 180,
  requiredSymbols: []
};

function parseTs(value: string | undefined): number | null {
  if (!value) {
    return null;
  }

  const parsed = Date.parse(value);
  return Number.isNaN(parsed) ? null : parsed;
}

function estimateStepSeconds(bars: Bar[]): number | undefined {
  const uniqueTs = Array.from(new Set(bars.map((bar) => bar.ts)))
    .map((ts) => Date.parse(ts))
    .filter((value) => !Number.isNaN(value))
    .sort((left, right) => left - right);

  if (uniqueTs.length < 3) {
    return undefined;
  }

  const deltas: number[] = [];
  for (let index = 1; index < uniqueTs.length; index += 1) {
    const delta = uniqueTs[index] - uniqueTs[index - 1];
    if (delta > 0) {
      deltas.push(delta);
    }
  }

  if (deltas.length === 0) {
    return undefined;
  }

  deltas.sort((left, right) => left - right);
  const median = deltas[Math.floor(deltas.length / 2)];
  return Math.round(median / 1000);
}

export function assessBarsForResearch(bars: Bar[], options?: Partial<DataQualityOptions>): DataQualityReport {
  const resolvedOptions: DataQualityOptions = {
    minCoveragePct: options?.minCoveragePct ?? DEFAULT_OPTIONS.minCoveragePct,
    maxEndLagMinutes: options?.maxEndLagMinutes ?? DEFAULT_OPTIONS.maxEndLagMinutes,
    requiredSymbols: options?.requiredSymbols ?? DEFAULT_OPTIONS.requiredSymbols
  };

  const symbols = Array.from(new Set(bars.map((bar) => bar.symbol))).sort();
  const sortedByTs = bars.slice().sort((left, right) => Date.parse(left.ts) - Date.parse(right.ts));
  const startTs = sortedByTs[0]?.ts;
  const endTs = sortedByTs[sortedByTs.length - 1]?.ts;
  const endMs = parseTs(endTs);

  const rowsBySymbol = new Map<string, Bar[]>();
  for (const bar of bars) {
    const list = rowsBySymbol.get(bar.symbol) ?? [];
    list.push(bar);
    rowsBySymbol.set(bar.symbol, list);
  }

  const maxRows = Math.max(0, ...Array.from(rowsBySymbol.values()).map((rows) => rows.length));
  const symbolQuality: SymbolQuality[] = symbols.map((symbol) => {
    const rows = (rowsBySymbol.get(symbol) ?? []).slice().sort((left, right) => Date.parse(left.ts) - Date.parse(right.ts));
    const symbolEndMs = parseTs(rows[rows.length - 1]?.ts);
    const endLagMinutes = endMs !== null && symbolEndMs !== null
      ? Math.max(0, (endMs - symbolEndMs) / 60000)
      : Number.POSITIVE_INFINITY;

    return {
      symbol,
      rows: rows.length,
      coveragePct: maxRows > 0 ? rows.length / maxRows : 0,
      startTs: rows[0]?.ts,
      endTs: rows[rows.length - 1]?.ts,
      endLagMinutes: Number(endLagMinutes.toFixed(2))
    };
  });

  const checks: DataQualityCheck[] = [
    {
      name: "hasRows",
      passed: bars.length > 0,
      reason: bars.length > 0 ? "Dataset is not empty." : "Dataset has no bars."
    },
    {
      name: "minCoveragePct",
      passed: symbolQuality.every((entry) => entry.coveragePct >= resolvedOptions.minCoveragePct),
      reason: `All symbols must have >= ${(resolvedOptions.minCoveragePct * 100).toFixed(1)}% of max symbol rows.`
    },
    {
      name: "maxEndLagMinutes",
      passed: symbolQuality.every((entry) => entry.endLagMinutes <= resolvedOptions.maxEndLagMinutes),
      reason: `All symbols must end within ${resolvedOptions.maxEndLagMinutes} minutes of the latest symbol.`
    },
    {
      name: "requiredSymbols",
      passed: resolvedOptions.requiredSymbols.every((symbol) => symbols.includes(symbol)),
      reason: resolvedOptions.requiredSymbols.length > 0
        ? `Dataset must include required symbols: ${resolvedOptions.requiredSymbols.join(", ")}.`
        : "No required symbol set was provided."
    }
  ];

  return {
    totalRows: bars.length,
    symbols,
    startTs,
    endTs,
    expectedStepSeconds: estimateStepSeconds(bars),
    options: resolvedOptions,
    symbolQuality,
    checks,
    pass: checks.every((check) => check.passed)
  };
}

export function assertBarsResearchReady(bars: Bar[], options?: Partial<DataQualityOptions>): DataQualityReport {
  const report = assessBarsForResearch(bars, options);
  if (report.pass) {
    return report;
  }

  const failingChecks = report.checks.filter((check) => !check.passed).map((check) => check.name).join(", ");
  const weakSymbols = report.symbolQuality
    .filter((entry) => entry.coveragePct < report.options.minCoveragePct || entry.endLagMinutes > report.options.maxEndLagMinutes)
    .map((entry) => `${entry.symbol}(coverage=${(entry.coveragePct * 100).toFixed(1)}%, endLagMin=${entry.endLagMinutes})`)
    .join("; ");
  const missingSymbols = report.options.requiredSymbols
    .filter((symbol) => !report.symbols.includes(symbol))
    .join(", ");

  throw new Error(
    `Research data quality gate failed: ${failingChecks}. Weak symbols: ${weakSymbols || "none"}. ` +
    `Missing symbols: ${missingSymbols || "none"}. ` +
    `Set RH_ALLOW_INCOMPLETE_DATA=1 to bypass temporarily.`
  );
}
