import type { Bar } from "../domain.js";

export interface NormalizeUniverseResult {
  inputRows: number;
  outputRows: number;
  symbols: string[];
  keptTimestamps: number;
  droppedTimestamps: number;
  coverageBefore: Record<string, number>;
  coverageAfter: Record<string, number>;
  bars: Bar[];
}

function sortBars(bars: Bar[]): Bar[] {
  return bars.slice().sort((left, right) => {
    const tsDiff = Date.parse(left.ts) - Date.parse(right.ts);
    if (tsDiff !== 0) {
      return tsDiff;
    }

    return left.symbol.localeCompare(right.symbol);
  });
}

export function normalizeUniverseByInnerTimestamp(bars: Bar[]): NormalizeUniverseResult {
  const sorted = sortBars(bars);
  const symbols = Array.from(new Set(sorted.map((bar) => bar.symbol))).sort();
  const byTimestamp = new Map<string, Map<string, Bar>>();

  for (const bar of sorted) {
    const tsMap = byTimestamp.get(bar.ts) ?? new Map<string, Bar>();
    if (!tsMap.has(bar.symbol)) {
      tsMap.set(bar.symbol, bar);
    }
    byTimestamp.set(bar.ts, tsMap);
  }

  const output: Bar[] = [];
  let keptTimestamps = 0;
  let droppedTimestamps = 0;

  for (const [ts, symbolMap] of Array.from(byTimestamp.entries()).sort((a, b) => Date.parse(a[0]) - Date.parse(b[0]))) {
    if (symbols.every((symbol) => symbolMap.has(symbol))) {
      keptTimestamps += 1;
      for (const symbol of symbols) {
        const bar = symbolMap.get(symbol);
        if (bar) {
          output.push(bar);
        }
      }
      continue;
    }

    droppedTimestamps += 1;
  }

  const maxBeforeRows = Math.max(0, ...symbols.map((symbol) => sorted.filter((bar) => bar.symbol === symbol).length));
  const maxAfterRows = Math.max(0, ...symbols.map((symbol) => output.filter((bar) => bar.symbol === symbol).length));

  const coverageBefore = Object.fromEntries(
    symbols.map((symbol) => {
      const rows = sorted.filter((bar) => bar.symbol === symbol).length;
      return [symbol, maxBeforeRows > 0 ? Number((rows / maxBeforeRows).toFixed(6)) : 0];
    })
  );
  const coverageAfter = Object.fromEntries(
    symbols.map((symbol) => {
      const rows = output.filter((bar) => bar.symbol === symbol).length;
      return [symbol, maxAfterRows > 0 ? Number((rows / maxAfterRows).toFixed(6)) : 0];
    })
  );

  return {
    inputRows: sorted.length,
    outputRows: output.length,
    symbols,
    keptTimestamps,
    droppedTimestamps,
    coverageBefore,
    coverageAfter,
    bars: output
  };
}
