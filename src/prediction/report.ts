import type { PredictionCandidate, PredictionVerdict } from "./types.js";

export function buildPredictionReport(rows: PredictionCandidate[]): {
  top10: PredictionCandidate[];
  counts: Record<PredictionVerdict, number>;
} {
  const counts: Record<PredictionVerdict, number> = { reject: 0, watch: 0, "paper-trade": 0 };
  for (const row of rows) counts[row.verdict] += 1;
  return { top10: rows.slice(0, 10), counts };
}
