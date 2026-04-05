import { readFile } from "node:fs/promises";
import type { Bar } from "../domain.js";

export async function loadBarsFromCsv(path: string): Promise<Bar[]> {
  const raw = await readFile(path, "utf8");
  const lines = raw.split(/\r?\n/).map((line) => line.trim()).filter(Boolean);
  const [, ...rows] = lines;

  return rows.map((row) => {
    const [ts, symbol, open, high, low, close, volume] = row.split(",");
    return {
      ts,
      symbol,
      open: Number(open),
      high: Number(high),
      low: Number(low),
      close: Number(close),
      volume: Number(volume)
    };
  });
}
