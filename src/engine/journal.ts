import { mkdir, readFile, writeFile } from "node:fs/promises";
import { dirname } from "node:path";
import type { TradeRecord } from "../domain.js";

export async function writeJournal(path: string, trades: TradeRecord[]): Promise<void> {
  await mkdir(dirname(path), { recursive: true });
  const data = trades.map((trade) => JSON.stringify(trade)).join("\n");
  await writeFile(path, `${data}${data ? "\n" : ""}`, "utf8");
}

export async function readJournal(path: string): Promise<TradeRecord[]> {
  try {
    const raw = await readFile(path, "utf8");
    return raw
      .split(/\r?\n/)
      .map((line) => line.trim())
      .filter(Boolean)
      .map((line) => JSON.parse(line) as TradeRecord);
  } catch {
    return [];
  }
}
