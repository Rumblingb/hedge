// crossVenueEdge.ts
// Lightweight cross-venue edge detector for Bill's prediction lane.
// Dry-run safe: if clients are not wired, exits gracefully.

import { promises as fs } from 'fs';
import { join } from 'path';
import { writeOutbox } from './lib/reporting.js';

const FLAG_PATH = join(process.cwd(), '.rumbling-hedge/state/cross-venue-edge-flag.json');

export async function detectCrossVenueEdge() {
  // Dry-run guard: ensure we don’t rely on missing adapters during build/test.
  console.log('[crossVenueEdge] dry-run: no external clients wired; skipping.');
  const entry = {
    ts: new Date().toISOString(),
    edges: [],
    note: 'dry-run — no external adapters available',
  };
  await writeOutbox('cross-venue-edge-dry', entry);
  // Also write a JSON flag for the training pipeline to consume
  await fs.mkdir(join(process.cwd(), '.rumbling-hedge/state'), { recursive: true });
  await fs.writeFile(FLAG_PATH, JSON.stringify({ detected: false, ts: entry.ts }), 'utf8');
  console.log('[crossVenueEdge] dry-run entry written to OUTBOX and flag.');
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
