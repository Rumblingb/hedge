import type { PredictionCandidate, PredictionVerdict } from "./types.js";

export function buildPredictionReport(rows: PredictionCandidate[]): {
  top10: PredictionCandidate[];
  counts: Record<PredictionVerdict, number>;
  reasons: Record<string, number>;
  venuePairs: Record<string, number>;
} {
  const counts: Record<PredictionVerdict, number> = { reject: 0, watch: 0, "paper-trade": 0 };
  const reasons: Record<string, number> = {};
  const venuePairs: Record<string, number> = {};
  for (const row of rows) {
    if (row.verdict === "reject" || row.verdict === "watch" || row.verdict === "paper-trade") {
      counts[row.verdict] += 1;
    }

    const venuePair = `${row.venueA ?? "unknown"}->${row.venueB ?? "unknown"}`;
    venuePairs[venuePair] = (venuePairs[venuePair] ?? 0) + 1;

    const rowReasons = Array.isArray(row.reasons) ? row.reasons : [];
    for (const reason of rowReasons) {
      reasons[reason] = (reasons[reason] ?? 0) + 1;
    }
  }
  return { top10: rows.slice(0, 10), counts, reasons, venuePairs };
}
