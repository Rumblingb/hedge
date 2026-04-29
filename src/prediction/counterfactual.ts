import { readFile } from "node:fs/promises";
import { resolve } from "node:path";
import type { PredictionCandidate } from "./types.js";

export interface CounterfactualReasonBucket {
  reason: string;
  count: number;
  share: number;
  meanGrossEdgePct: number;
  meanNetEdgePct: number;
  meanFeeDragPct: number;
  nearMissCount: number;
}

export interface CounterfactualNearMiss {
  candidateId: string;
  reasons: string[];
  grossEdgePct: number;
  netEdgePct: number;
  feeDragPct: number;
  matchScore: number;
}

export interface CounterfactualVenuePair {
  venuePair: string;
  total: number;
  rejected: number;
  share: number;
}

export interface CounterfactualReport {
  generatedAt: string;
  windowHours: number;
  totalCandidates: number;
  acceptedCount: number;
  rejectedCount: number;
  rejectionReasons: CounterfactualReasonBucket[];
  nearMisses: CounterfactualNearMiss[];
  venuePairRejectionRates: CounterfactualVenuePair[];
  suggestions: string[];
}

async function readJsonl<T>(path: string): Promise<T[]> {
  const buf = await readFile(path, "utf8");
  const out: T[] = [];
  for (const line of buf.split("\n")) {
    const t = line.trim();
    if (!t) continue;
    try {
      out.push(JSON.parse(t) as T);
    } catch {
      // skip malformed
    }
  }
  return out;
}

export function aggregateCounterfactual(rows: PredictionCandidate[], windowHours = 24, now = new Date()): CounterfactualReport {
  const cutoff = now.getTime() - windowHours * 3_600_000;
  const scoped = rows.filter((r) => {
    const t = Date.parse(r.ts);
    return Number.isFinite(t) ? t >= cutoff : true;
  });
  const total = scoped.length;
  const accepted = scoped.filter((r) => r.verdict !== "reject");
  const rejected = scoped.filter((r) => r.verdict === "reject");

  const reasonAgg = new Map<string, { count: number; gross: number; net: number; drag: number; near: number }>();
  for (const row of rejected) {
    const reasons = row.reasons ?? [];
    for (const reason of reasons) {
      const cur = reasonAgg.get(reason) ?? { count: 0, gross: 0, net: 0, drag: 0, near: 0 };
      cur.count += 1;
      cur.gross += row.grossEdgePct;
      cur.net += row.netEdgePct;
      cur.drag += row.feeDragPct;
      if (reasons.length === 1) cur.near += 1;
      reasonAgg.set(reason, cur);
    }
  }
  const rejectedCount = rejected.length;
  const rejectionReasons: CounterfactualReasonBucket[] = Array.from(reasonAgg.entries())
    .map(([reason, v]) => ({
      reason,
      count: v.count,
      share: rejectedCount > 0 ? v.count / rejectedCount : 0,
      meanGrossEdgePct: v.count ? v.gross / v.count : 0,
      meanNetEdgePct: v.count ? v.net / v.count : 0,
      meanFeeDragPct: v.count ? v.drag / v.count : 0,
      nearMissCount: v.near
    }))
    .sort((a, b) => b.count - a.count);

  const nearMisses: CounterfactualNearMiss[] = rejected
    .filter((r) => (r.reasons ?? []).length === 1)
    .map((r) => ({
      candidateId: r.candidateId,
      reasons: r.reasons ?? [],
      grossEdgePct: r.grossEdgePct,
      netEdgePct: r.netEdgePct,
      feeDragPct: r.feeDragPct,
      matchScore: r.matchScore
    }))
    .sort((a, b) => b.grossEdgePct - a.grossEdgePct)
    .slice(0, 25);

  const venuePairAgg = new Map<string, { total: number; rejected: number }>();
  for (const row of scoped) {
    const pair = `${row.venueA}->${row.venueB}`;
    const cur = venuePairAgg.get(pair) ?? { total: 0, rejected: 0 };
    cur.total += 1;
    if (row.verdict === "reject") cur.rejected += 1;
    venuePairAgg.set(pair, cur);
  }
  const venuePairRejectionRates: CounterfactualVenuePair[] = Array.from(venuePairAgg.entries())
    .map(([venuePair, v]) => ({ venuePair, total: v.total, rejected: v.rejected, share: v.total ? v.rejected / v.total : 0 }))
    .sort((a, b) => b.total - a.total);

  const suggestions: string[] = [];
  const reasonShare = new Map(rejectionReasons.map((r) => [r.reason, r.share]));
  const costDrag = reasonShare.get("cost-drag-exceeds-edge") ?? 0;
  const negNet = reasonShare.get("negative-net-edge") ?? 0;
  const thinSize = reasonShare.get("thin-size") ?? 0;
  const weakMatch = reasonShare.get("weak-match") ?? 0;
  const subscale = reasonShare.get("subscale-edge") ?? 0;
  const meanGrossWhenNegNet = rejectionReasons.find((r) => r.reason === "negative-net-edge")?.meanGrossEdgePct ?? 0;

  if (costDrag > 0.4) {
    suggestions.push("cost-drag dominates rejections; hunt lower-fee venues, larger edges, or revisit the fee model.");
  }
  if (negNet > 0.4 && meanGrossWhenNegNet > 2) {
    suggestions.push("negative-net-edge is dominant despite >2% gross — fee-model assumptions may be too conservative.");
  }
  if (thinSize > 0.25) {
    suggestions.push("thin-size is blocking >25% of rejections; consider relaxing size gate for paper mode.");
  }
  if (weakMatch > 0.35) {
    suggestions.push("weak-match >35% of rejections; inspect near-misses for normalizer false-negatives.");
  }
  if (subscale > 0.15) {
    suggestions.push("subscale-edge is frequent; min stake may be cutting off viable small trades — consider lowering minStake or relaxing for paper.");
  }
  const nearSubscale = nearMisses.filter((n) => n.reasons.includes("subscale-edge") && n.netEdgePct > 0).length;
  if (nearSubscale >= 3) {
    suggestions.push(`${nearSubscale} near-miss candidates have positive net edge but sub-threshold stake — lowering minStake would unblock them.`);
  }
  if (suggestions.length === 0 && rejectedCount > 0) {
    suggestions.push("no single reason dominates; pipeline is healthy but edge is thin — focus on new edge sources (flow signals, fair-value model).");
  }

  return {
    generatedAt: now.toISOString(),
    windowHours,
    totalCandidates: total,
    acceptedCount: accepted.length,
    rejectedCount,
    rejectionReasons,
    nearMisses,
    venuePairRejectionRates,
    suggestions
  };
}

export async function buildCounterfactualReport(args: { journalPath: string; windowHours?: number; now?: Date }): Promise<CounterfactualReport> {
  const path = resolve(args.journalPath);
  const rows = await readJsonl<PredictionCandidate>(path);
  return aggregateCounterfactual(rows, args.windowHours ?? 24, args.now ?? new Date());
}

export function summarizeCounterfactual(report: CounterfactualReport): string {
  const lines: string[] = [];
  lines.push(`Counterfactual (${report.windowHours}h window, generated ${report.generatedAt})`);
  lines.push(`Total candidates: ${report.totalCandidates} | accepted: ${report.acceptedCount} | rejected: ${report.rejectedCount}`);
  if (report.rejectedCount > 0) {
    lines.push("");
    lines.push("Rejection reasons:");
    for (const r of report.rejectionReasons.slice(0, 8)) {
      lines.push(
        `  ${r.reason.padEnd(28)} n=${String(r.count).padStart(4)} share=${(r.share * 100).toFixed(1).padStart(5)}% grossMean=${r.meanGrossEdgePct.toFixed(2)}% netMean=${r.meanNetEdgePct.toFixed(2)}% near-miss=${r.nearMissCount}`
      );
    }
  }
  if (report.nearMisses.length > 0) {
    lines.push("");
    lines.push("Top near-misses (single-reason rejections, highest gross edge):");
    for (const m of report.nearMisses.slice(0, 5)) {
      lines.push(`  [${m.reasons.join(",")}] gross=${m.grossEdgePct.toFixed(2)}% net=${m.netEdgePct.toFixed(2)}% match=${m.matchScore.toFixed(2)} ${m.candidateId}`);
    }
  }
  if (report.venuePairRejectionRates.length > 0) {
    lines.push("");
    lines.push("Venue pair rejection rates:");
    for (const vp of report.venuePairRejectionRates.slice(0, 5)) {
      lines.push(`  ${vp.venuePair.padEnd(28)} total=${vp.total} rejected=${vp.rejected} (${(vp.share * 100).toFixed(1)}%)`);
    }
  }
  if (report.suggestions.length > 0) {
    lines.push("");
    lines.push("Suggestions:");
    for (const s of report.suggestions) lines.push(`  • ${s}`);
  }
  return lines.join("\n");
}
