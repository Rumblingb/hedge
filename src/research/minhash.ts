const MOD = 0xffffffff;

function fnv1a(str: string, seed: number): number {
  let h = (0x811c9dc5 ^ seed) >>> 0;
  for (let i = 0; i < str.length; i++) {
    h ^= str.charCodeAt(i);
    h = Math.imul(h, 0x01000193) >>> 0;
  }
  return h >>> 0;
}

function shingles(text: string, n: number): string[] {
  const tokens = text
    .toLowerCase()
    .replace(/[^a-z0-9\s]+/g, " ")
    .split(/\s+/)
    .filter(Boolean);
  if (tokens.length < n) return tokens.length > 0 ? [tokens.join(" ")] : [];
  const out: string[] = [];
  for (let i = 0; i <= tokens.length - n; i++) {
    out.push(tokens.slice(i, i + n).join(" "));
  }
  return out;
}

export interface MinHashSignature {
  ngram: number;
  hashes: number[];
}

export function minhash(text: string, opts: { numHashes?: number; ngram?: number } = {}): MinHashSignature {
  const numHashes = opts.numHashes ?? 64;
  const ngram = opts.ngram ?? 5;
  const sigs = new Array<number>(numHashes).fill(MOD);
  const shing = shingles(text, ngram);
  if (shing.length === 0) return { ngram, hashes: sigs };
  for (const s of shing) {
    for (let h = 0; h < numHashes; h++) {
      const v = fnv1a(s, h);
      if (v < sigs[h]) sigs[h] = v;
    }
  }
  return { ngram, hashes: sigs };
}

export function jaccardEstimate(a: MinHashSignature, b: MinHashSignature): number {
  if (a.hashes.length !== b.hashes.length) {
    throw new Error(`minhash length mismatch: ${a.hashes.length} vs ${b.hashes.length}`);
  }
  let eq = 0;
  for (let i = 0; i < a.hashes.length; i++) {
    if (a.hashes[i] === b.hashes[i]) eq++;
  }
  return eq / a.hashes.length;
}

export function isNearDuplicate(
  candidate: MinHashSignature,
  existing: Iterable<MinHashSignature>,
  threshold = 0.8
): boolean {
  for (const sig of existing) {
    if (jaccardEstimate(candidate, sig) >= threshold) return true;
  }
  return false;
}
