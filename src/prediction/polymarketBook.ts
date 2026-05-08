export interface ClobOrderLevel {
  price?: string | number;
  size?: string | number;
}

export interface ClobBook {
  bids?: ClobOrderLevel[];
  asks?: ClobOrderLevel[];
}

export interface PolymarketQuote {
  bestBid?: number;
  bestAsk?: number;
  bidSize?: number;
  askSize?: number;
  topBookDepth?: number;
  spreadPct?: number;
}

function toNumber(value: unknown): number | undefined {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string") {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : undefined;
  }
  return undefined;
}

function normalizeLevels(levels: ClobOrderLevel[] | undefined): Array<{ price: number; size: number }> {
  return (levels ?? [])
    .map((level) => ({ price: toNumber(level.price), size: toNumber(level.size) }))
    .filter((level): level is { price: number; size: number } =>
      level.price !== undefined
      && level.size !== undefined
      && level.price > 0
      && level.price < 1
      && level.size > 0
    );
}

export function quoteFromBook(book: ClobBook): PolymarketQuote {
  const bids = normalizeLevels(book.bids).sort((left, right) => right.price - left.price);
  const asks = normalizeLevels(book.asks).sort((left, right) => left.price - right.price);
  const bestBid = bids[0]?.price;
  const bestAsk = asks[0]?.price;
  const bidSize = bids[0]?.size;
  const askSize = asks[0]?.size;
  const topBookDepth = (bidSize ?? 0) + (askSize ?? 0);
  const spreadPct = bestBid !== undefined && bestAsk !== undefined
    ? Number(((bestAsk - bestBid) * 100).toFixed(2))
    : undefined;

  return {
    ...(bestBid !== undefined ? { bestBid } : {}),
    ...(bestAsk !== undefined ? { bestAsk } : {}),
    ...(bidSize !== undefined ? { bidSize } : {}),
    ...(askSize !== undefined ? { askSize } : {}),
    ...(topBookDepth > 0 ? { topBookDepth } : {}),
    ...(spreadPct !== undefined ? { spreadPct } : {}),
  };
}

export async function fetchPolymarketBook(tokenId: string, timeoutMs = 8_000): Promise<ClobBook | null> {
  const url = new URL("https://clob.polymarket.com/book");
  url.searchParams.set("token_id", tokenId);
  const response = await fetch(url, {
    headers: { accept: "application/json", "user-agent": "rumbling-hedge/0.1" },
    signal: AbortSignal.timeout(timeoutMs),
  });
  if (!response.ok) return null;
  return response.json() as Promise<ClobBook>;
}

export async function fetchPolymarketQuote(tokenId: string, timeoutMs = 8_000): Promise<PolymarketQuote | null> {
  const book = await fetchPolymarketBook(tokenId, timeoutMs);
  return book ? quoteFromBook(book) : null;
}
