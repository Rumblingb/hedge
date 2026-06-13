// crossVenueEdge.ts
// Cross-venue edge detector for Bill's prediction lane.
// READ-ONLY: fetches public market prices from Polymarket + Kalshi and runs the
// matcher/fee pipeline to surface net-of-cost cross-venue arb candidates. It NEVER
// places, signs, or routes an order — it only writes a measurement report + flag.
// Dry-run safe: if adapters can't fetch (no creds/network), it falls back to the
// graceful skip so build/test/offline runs don't fail.

import { promises as fs } from 'fs';
import { join } from 'path';
import { writeOutbox } from './lib/reporting.js';
import { fetchPolymarketLiveSnapshot } from './adapters/polymarket.js';
import { fetchKalshiLiveSnapshot } from './adapters/kalshi.js';
import { scanPredictionCandidates } from './matcher.js';
import { buildPredictionFeeConfigFromEnv } from './fees.js';
import { buildPredictionSizingConfigFromEnv } from './sizing.js';
import type { PredictionMarketSnapshot } from './types.js';

const FLAG_PATH = join(process.cwd(), '.rumbling-hedge/state/cross-venue-edge-flag.json');
const REPORT_PATH = join(process.cwd(), '.rumbling-hedge/state/cross-venue-edge.latest.json');

export async function detectCrossVenueEdge() {
  const ts = new Date().toISOString();

  // Read-only fetch from both venues. Either venue failing (no creds, offline)
  // degrades to dry-run rather than throwing — the prediction lane stays safe.
  let polymarket: PredictionMarketSnapshot[] = [];
  let kalshi: PredictionMarketSnapshot[] = [];
  const fetchErrors: string[] = [];
  try {
    polymarket = await fetchPolymarketLiveSnapshot(40);
  } catch (e) {
    fetchErrors.push(`polymarket: ${(e as Error).message}`);
  }
  try {
    kalshi = await fetchKalshiLiveSnapshot(40);
  } catch (e) {
    fetchErrors.push(`kalshi: ${(e as Error).message}`);
  }

  if (polymarket.length === 0 || kalshi.length === 0) {
    // Dry-run fallback: need both venues to compute a cross-venue edge.
    console.log(
      `[crossVenueEdge] dry-run: insufficient live data ` +
        `(polymarket=${polymarket.length}, kalshi=${kalshi.length}); skipping.`
    );
    const entry = {
      ts,
      edges: [],
      note: 'dry-run — one or both venues returned no markets',
      fetchErrors,
    };
    await writeOutbox('cross-venue-edge-dry', entry);
    await fs.mkdir(join(process.cwd(), '.rumbling-hedge/state'), { recursive: true });
    await fs.writeFile(FLAG_PATH, JSON.stringify({ detected: false, ts }), 'utf8');
    return;
  }

  // Real measurement: matcher gates same-venue pairs and computes gross edge,
  // fee drag (venue-aware), net edge, sizing, and a verdict per candidate.
  const fees = buildPredictionFeeConfigFromEnv();
  const sizing = buildPredictionSizingConfigFromEnv();
  const candidates = scanPredictionCandidates({ markets: [...polymarket, ...kalshi], fees, sizing, ts });

  // 'paper-trade' is the strongest verdict the matcher assigns (reject|watch|paper-trade).
  const actionable = candidates.filter((c) => c.verdict === 'paper-trade');
  const positiveNet = candidates.filter((c) => c.netEdgePct > 0);
  const topNet = candidates.slice().sort((a, b) => b.netEdgePct - a.netEdgePct).slice(0, 10);
  const detected = actionable.length > 0;

  const entry = {
    ts,
    venues: { polymarket: polymarket.length, kalshi: kalshi.length },
    candidateCount: candidates.length,
    actionableCount: actionable.length,
    positiveNetCount: positiveNet.length,
    fetchErrors,
    edges: topNet.map((c) => ({
      eventA: c.eventTitleA,
      eventB: c.eventTitleB,
      outcomeA: c.outcomeA,
      outcomeB: c.outcomeB,
      grossEdgePct: c.grossEdgePct,
      feeDragPct: c.feeDragPct,
      netEdgePct: c.netEdgePct,
      matchScore: c.matchScore,
      verdict: c.verdict,
      sizeVerdict: c.sizeVerdict,
      reasons: c.reasons,
    })),
  };

  await writeOutbox('cross-venue-edge', entry);
  await fs.mkdir(join(process.cwd(), '.rumbling-hedge/state'), { recursive: true });
  await fs.writeFile(REPORT_PATH, JSON.stringify(entry, null, 2), 'utf8');
  await fs.writeFile(FLAG_PATH, JSON.stringify({ detected, ts }), 'utf8');
  console.log(
    `[crossVenueEdge] scanned ${candidates.length} cross-venue pairs: ` +
      `${actionable.length} paper-trade, ${positiveNet.length} net-positive. ` +
      `Top net edge: ${topNet[0]?.netEdgePct ?? 0}% (${topNet[0]?.verdict ?? 'none'}).`
  );
}

// Optional: helper to set detected=true when real edges are found (to be called later)
export async function setCrossVenueDetected() {
  await fs.mkdir(join(process.cwd(), '.rumbling-hedge/state'), { recursive: true });
  await fs.writeFile(FLAG_PATH, JSON.stringify({ detected: true, ts: new Date().toISOString() }), 'utf8');
}

if (import.meta.url === `file://${process.argv[1]}`) {
  detectCrossVenueEdge().catch((e) => {
    console.error('[crossVenueEdge] error:', e);
    process.exit(1);
  });
}
