import { mkdir, readFile, writeFile } from "node:fs/promises";
import { dirname } from "node:path";
import type { PredictionCandidate } from "./types.js";

export async function writePredictionJournal(path: string, rows: PredictionCandidate[]): Promise<void> {
  await mkdir(dirname(path), { recursive: true });
  const data = rows.map((row) => JSON.stringify(row)).join("\n");
  await writeFile(path, `${data}${data ? "\n" : ""}`, "utf8");
}

export async function readPredictionJournal(path: string): Promise<PredictionCandidate[]> {
  try {
    const raw = await readFile(path, "utf8");
    return raw.split(/\r?\n/).map((line) => line.trim()).filter(Boolean).map((line) => JSON.parse(line) as PredictionCandidate);
  } catch {
    return [];
  }
}
