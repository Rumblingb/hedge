const POLYMARKET_HEADERS = {
  accept: "application/json",
  "user-agent": "rumbling-hedge/0.1"
} as const;

export interface PredictionCopyTrader {
  rank: number;
  wallet: string;
  displayName: string;
  xUsername?: string;
  verifiedBadge: boolean;
  pnl: number;
  volume: number;
  activePositionCount: number;
  recentActivityCount: number;
  score: number;
  lastActivityTs?: string;
}

export interface PredictionCopyPosition {
  wallet: string;
  displayName: string;
  marketId: string;
  slug: string;
  title: string;
  outcome: string;
  size: number;
  avgPrice: number;
  currentPrice: number;
  currentValue: number;
  percentPnl: number;
  endDate?: string;
  lastActivityTs?: string;
  convictionScore: number;
}

export interface PredictionCopyIdea {
  id: string;
  slug: string;
  title: string;
  outcome: string;
  supporterCount: number;
  consensusPct: number;
  supporters: string[];
  totalCurrentValue: number;
  averageEntryPrice: number;
  currentPrice: number;
  averageLeaderPnl: number;
  averagePositionPnl: number;
  weightedScore: number;
  freshestActivityTs?: string;
  action: "watch" | "shadow-buy";
  reason: string;
}

export interface PredictionCopyDemoReport {
  ts: string;
  venue: "polymarket";
  cohort: {
    leaderboardPeriod: string;
    consideredLeaders: number;
    selectedLeaders: number;
    selectedWallets: string[];
    minPnlUsd: number;
    minConsensusWallets: number;
    minIdeaValueUsd: number;
    rejectionCounts?: Record<string, number>;
  };
  traders: PredictionCopyTrader[];
  positions: PredictionCopyPosition[];
  ideas: PredictionCopyIdea[];
  actionCounts: Record<PredictionCopyIdea["action"], number>;
  blockers: string[];
  summary: string;
}

export interface PredictionCopyDemoOptions {
  leaderboardLimit?: number;
  maxLeaders?: number;
  positionsPerLeader?: number;
  activityPerLeader?: number;
  leaderboardPeriod?: "DAY" | "WEEK" | "MONTH" | "ALL";
  minPnlUsd?: number;
  minConsensusWallets?: number;
  minIdeaValueUsd?: number;
  minHoursToExpiry?: number;
  minPositionPrice?: number;
  maxPositionPrice?: number;
}

interface PolymarketLeaderboardEntry {
  rank?: string | number;
  proxyWallet?: string;
  userName?: string;
  xUsername?: string;
  verifiedBadge?: boolean;
  pnl?: string | number;
  vol?: string | number;
}

interface PolymarketPosition {
  proxyWallet?: string;
  conditionId?: string;
  slug?: string;
  title?: string;
  outcome?: string;
  size?: string | number;
  avgPrice?: string | number;
  currentValue?: string | number;
  percentPnl?: string | number;
  curPrice?: string | number;
  redeemable?: boolean;
  endDate?: string;
}

interface PolymarketActivity {
  proxyWallet?: string;
  timestamp?: string | number;
  type?: string;
}

interface SelectedLeader {
  trader: PredictionCopyTrader;
  positions: PredictionCopyPosition[];
  rejectionCounts?: Record<string, number>;
}

const DEFAULT_OPTIONS: Required<PredictionCopyDemoOptions> = {
  leaderboardLimit: 12,
  maxLeaders: 6,
  positionsPerLeader: 20,
  activityPerLeader: 12,
  leaderboardPeriod: "MONTH",
  minPnlUsd: 50_000,
  minConsensusWallets: 2,
  minIdeaValueUsd: 2_500,
  minHoursToExpiry: 48,
  minPositionPrice: 0.08,
  maxPositionPrice: 0.92
};

function toNumber(value: unknown): number {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string") {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : 0;
  }
  return 0;
}

function toIsoFromUnixSeconds(value: unknown): string | undefined {
  const parsed = toNumber(value);
  if (parsed <= 0) return undefined;
  return new Date(parsed * 1000).toISOString();
}

function isFutureish(value?: string): boolean {
  if (!value) return true;
  const parsed = Date.parse(value);
  if (!Number.isFinite(parsed)) return true;
  return parsed >= Date.now() - 24 * 60 * 60 * 1000;
}

function hoursToExpiry(value?: string): number | null {
  if (!value) return null;
  const parsed = Date.parse(value);
  if (!Number.isFinite(parsed)) return null;
  return (parsed - Date.now()) / (60 * 60 * 1000);
}

type PredictionDomain = "macro" | "finance" | "crypto" | "politics" | "sports" | "esports" | "entertainment" | "other";

type PositionNormalizationResult = {
  position: PredictionCopyPosition | null;
  rejection?: string;
};

export function classifyPredictionDomain(args: { title: string; slug: string }): PredictionDomain {
  const text = `${args.title} ${args.slug}`.toLowerCase();

  if (/(bitcoin|btc|ethereum|eth|solana|sol\b|crypto|stablecoin|token|airdrop|nft|dogecoin|xrp|bnb|base chain|defi|memecoin)/i.test(text)) {
    return "crypto";
  }
  if (/(fed|fomc|interest rate|rate cut|rate hike|inflation|cpi|ppi|payrolls|jobs report|gdp|recession|treasury|yield|oil|wti|brent|gold|silver|tariff|etf|ipo|earnings|s&p|nasdaq|dow|stock market|tesla|nvidia|apple|microsoft)/i.test(text)) {
    return "macro";
  }
  if (/\b(election|president|presidential|prime minister|nomination|nominee|congress|senate|parliament|war|ceasefire|peace deal|treaty|cabinet|supreme court|policy|regulation|sec|cftc|white house|geopolitic|ukraine|iran|china|russia)\b/i.test(text)) {
    return "politics";
  }
  if (/(merger|acquisition|bankruptcy|revenue|valuation|funding|company|corporate|shareholder|antitrust|openai|google|meta|amazon)/i.test(text)) {
    return "finance";
  }
  if (/(lol|cs2|dota|valorant|lck|iem|esports?)/i.test(text)) {
    return "esports";
  }
  if (/(nba|nhl|mlb|nfl|wnba|ncaa|soccer|football|baseball|basketball|tennis|atp|wta|golf|fifa|world cup|ucl|epl|liga|rangers|lightning|warriors|clippers|roland garros)/i.test(text)) {
    return "sports";
  }
  if (/(oscar|grammy|emmy|movie|tv show|box office|album|celebrity|reality show)/i.test(text)) {
    return "entertainment";
  }
  return "other";
}

export function isFounderApprovedPredictionDomain(title: string, slug: string): boolean {
  const domain = classifyPredictionDomain({ title, slug });
  return domain === "macro" || domain === "finance" || domain === "crypto" || domain === "politics";
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

function displayName(args: {
  wallet: string;
  userName?: string;
  xUsername?: string;
}): string {
  const handle = args.xUsername?.trim();
  if (handle) return `@${handle.replace(/^@/, "")}`;
  const name = args.userName?.trim();
  if (name) return name;
  return `${args.wallet.slice(0, 6)}...${args.wallet.slice(-4)}`;
}

async function fetchJson<T>(url: URL): Promise<T> {
  const response = await fetch(url, {
    headers: POLYMARKET_HEADERS,
    signal: AbortSignal.timeout(10_000)
  });
  if (!response.ok) {
    throw new Error(`Polymarket copy-demo fetch failed: ${response.status} ${response.statusText}`);
  }
  return response.json() as Promise<T>;
}

export async function fetchPolymarketLeaderboard(options: PredictionCopyDemoOptions = {}): Promise<PolymarketLeaderboardEntry[]> {
  const resolved = { ...DEFAULT_OPTIONS, ...options };
  const url = new URL("https://data-api.polymarket.com/v1/leaderboard");
  url.searchParams.set("timePeriod", resolved.leaderboardPeriod);
  url.searchParams.set("category", "OVERALL");
  url.searchParams.set("orderBy", "PNL");
  url.searchParams.set("limit", String(resolved.leaderboardLimit));
  return fetchJson<PolymarketLeaderboardEntry[]>(url);
}

export async function fetchPolymarketUserPositions(wallet: string, options: PredictionCopyDemoOptions = {}): Promise<PolymarketPosition[]> {
  const resolved = { ...DEFAULT_OPTIONS, ...options };
  const url = new URL("https://data-api.polymarket.com/positions");
  url.searchParams.set("user", wallet);
  url.searchParams.set("limit", String(resolved.positionsPerLeader));
  url.searchParams.set("sortBy", "CURRENT");
  url.searchParams.set("sortDirection", "DESC");
  return fetchJson<PolymarketPosition[]>(url);
}

export async function fetchPolymarketUserActivity(wallet: string, options: PredictionCopyDemoOptions = {}): Promise<PolymarketActivity[]> {
  const resolved = { ...DEFAULT_OPTIONS, ...options };
  const url = new URL("https://data-api.polymarket.com/activity");
  url.searchParams.set("user", wallet);
  url.searchParams.set("limit", String(resolved.activityPerLeader));
  return fetchJson<PolymarketActivity[]>(url);
}

function normalizeTrader(entry: PolymarketLeaderboardEntry): PredictionCopyTrader | null {
  const wallet = String(entry.proxyWallet ?? "").toLowerCase();
  if (!wallet) return null;
  return {
    rank: Math.max(0, Math.trunc(toNumber(entry.rank))),
    wallet,
    displayName: displayName({
      wallet,
      userName: typeof entry.userName === "string" ? entry.userName : undefined,
      xUsername: typeof entry.xUsername === "string" ? entry.xUsername : undefined
    }),
    xUsername: typeof entry.xUsername === "string" && entry.xUsername.trim() ? entry.xUsername.trim() : undefined,
    verifiedBadge: entry.verifiedBadge === true,
    pnl: toNumber(entry.pnl),
    volume: toNumber(entry.vol),
    activePositionCount: 0,
    recentActivityCount: 0,
    score: 0
  };
}

function normalizePosition(args: {
  trader: PredictionCopyTrader;
  position: PolymarketPosition;
  lastActivityTs?: string;
  options: Required<PredictionCopyDemoOptions>;
}): PositionNormalizationResult {
  const position = args.position;
  const slug = String(position.slug ?? "").trim();
  const title = String(position.title ?? "").trim();
  const outcome = String(position.outcome ?? "").trim();
  const currentPrice = toNumber(position.curPrice);
  const currentValue = toNumber(position.currentValue);
  const avgPrice = toNumber(position.avgPrice);
  const size = toNumber(position.size);
  const percentPnl = toNumber(position.percentPnl);
  const marketId = String(position.conditionId ?? slug ?? title).trim();

  if (!slug || !title || !outcome || !marketId) return { position: null, rejection: "missing-fields" };
  if (!isFounderApprovedPredictionDomain(title, slug)) return { position: null, rejection: "out-of-domain" };
  if (position.redeemable === true) return { position: null, rejection: "redeemable" };
  if (!isFutureish(position.endDate)) return { position: null, rejection: "expired" };
  const expiryHours = hoursToExpiry(position.endDate);
  if (expiryHours !== null && expiryHours < args.options.minHoursToExpiry) return { position: null, rejection: "too-near-expiry" };
  if (currentValue <= 0) return { position: null, rejection: "no-current-value" };
  if (currentPrice <= 0 || currentPrice >= 1) return { position: null, rejection: "invalid-price" };
  if (currentPrice < args.options.minPositionPrice || currentPrice > args.options.maxPositionPrice) return { position: null, rejection: "price-out-of-range" };

  const convictionScore = Number((Math.max(1, currentValue) * Math.max(1, args.trader.score)).toFixed(2));
  return {
    position: {
      wallet: args.trader.wallet,
      displayName: args.trader.displayName,
      marketId,
      slug,
      title,
      outcome,
      size,
      avgPrice,
      currentPrice,
      currentValue,
      percentPnl,
      endDate: position.endDate,
      lastActivityTs: args.lastActivityTs,
      convictionScore
    }
  };
}

function scoreTrader(args: {
  trader: PredictionCopyTrader;
  positions: PredictionCopyPosition[];
  activities: PolymarketActivity[];
}): PredictionCopyTrader {
  const activePositionValue = args.positions.reduce((sum, position) => sum + position.currentValue, 0);
  const recentActivityCount = args.activities.filter((activity) => String(activity.type ?? "").trim().length > 0).length;
  const lastActivityTs = args.activities
    .map((activity) => toIsoFromUnixSeconds(activity.timestamp))
    .filter((value): value is string => Boolean(value))
    .sort()
    .at(-1);
  const score = Number((
    Math.log10(Math.max(args.trader.pnl, 1))
    + Math.log10(Math.max(activePositionValue, 1)) * 0.7
    + clamp(recentActivityCount / 5, 0, 1)
  ).toFixed(2));

  return {
    ...args.trader,
    activePositionCount: args.positions.length,
    recentActivityCount,
    score,
    lastActivityTs
  };
}

function buildIdeaReason(idea: Omit<PredictionCopyIdea, "reason">): string {
  if (idea.action === "shadow-buy") {
    return `${idea.supporterCount} leader wallets still hold this outcome with $${idea.totalCurrentValue.toFixed(0)} live value behind it.`;
  }
  return `Consensus exists, but it still needs broader leader overlap or more live value behind it.`;
}

export function buildPredictionCopyIdeas(args: {
  leaders: SelectedLeader[];
  minConsensusWallets: number;
  minIdeaValueUsd: number;
}): PredictionCopyIdea[] {
  const byIdea = new Map<string, {
    slug: string;
    title: string;
    outcome: string;
    weightedScore: number;
    totalCurrentValue: number;
    entryPriceWeight: number;
    currentPriceWeight: number;
    positionPnlWeight: number;
    supporters: Map<string, { displayName: string; pnl: number }>;
    freshestActivityMs: number;
  }>();

  for (const leader of args.leaders) {
    for (const position of leader.positions) {
      const key = `${position.slug}::${position.outcome.toLowerCase()}`;
      const existing = byIdea.get(key) ?? {
        slug: position.slug,
        title: position.title,
        outcome: position.outcome,
        weightedScore: 0,
        totalCurrentValue: 0,
        entryPriceWeight: 0,
        currentPriceWeight: 0,
        positionPnlWeight: 0,
        supporters: new Map<string, { displayName: string; pnl: number }>(),
        freshestActivityMs: 0
      };
      const weight = Math.max(1, position.currentValue);
      existing.totalCurrentValue += position.currentValue;
      existing.weightedScore += position.convictionScore;
      existing.entryPriceWeight += position.avgPrice * weight;
      existing.currentPriceWeight += position.currentPrice * weight;
      existing.positionPnlWeight += position.percentPnl * weight;
      existing.supporters.set(leader.trader.wallet, {
        displayName: leader.trader.displayName,
        pnl: leader.trader.pnl
      });
      if (position.lastActivityTs) {
        const lastActivityMs = Date.parse(position.lastActivityTs);
        if (Number.isFinite(lastActivityMs)) {
          existing.freshestActivityMs = Math.max(existing.freshestActivityMs, lastActivityMs);
        }
      }
      byIdea.set(key, existing);
    }
  }

  return Array.from(byIdea.entries())
    .map(([key, value]) => {
      const supporterEntries = Array.from(value.supporters.values());
      const supporterCount = supporterEntries.length;
      const ideaBase = {
        id: key,
        slug: value.slug,
        title: value.title,
        outcome: value.outcome,
        supporterCount,
        consensusPct: 0,
        supporters: supporterEntries.map((supporter) => supporter.displayName),
        totalCurrentValue: Number(value.totalCurrentValue.toFixed(2)),
        averageEntryPrice: Number((value.entryPriceWeight / Math.max(value.totalCurrentValue, 1)).toFixed(4)),
        currentPrice: Number((value.currentPriceWeight / Math.max(value.totalCurrentValue, 1)).toFixed(4)),
        averageLeaderPnl: Number((supporterEntries.reduce((sum, supporter) => sum + supporter.pnl, 0) / Math.max(supporterEntries.length, 1)).toFixed(2)),
        averagePositionPnl: Number((value.positionPnlWeight / Math.max(value.totalCurrentValue, 1)).toFixed(2)),
        weightedScore: Number(value.weightedScore.toFixed(2)),
        freshestActivityTs: value.freshestActivityMs > 0 ? new Date(value.freshestActivityMs).toISOString() : undefined,
        action: "watch" as const
      };
      const action = supporterCount >= args.minConsensusWallets
        && value.totalCurrentValue >= args.minIdeaValueUsd
        && ideaBase.currentPrice > 0.03
        && ideaBase.currentPrice < 0.97
          ? "shadow-buy" as const
          : "watch" as const;
      const idea: Omit<PredictionCopyIdea, "reason"> = {
        ...ideaBase,
        consensusPct: Number((supporterCount / Math.max(args.leaders.length, 1)).toFixed(2)),
        action
      };
      return {
        ...idea,
        reason: buildIdeaReason(idea)
      };
    })
    .sort((a, b) => b.weightedScore - a.weightedScore || b.totalCurrentValue - a.totalCurrentValue)
    .slice(0, 15);
}

export async function buildPredictionCopyDemoReport(options: PredictionCopyDemoOptions = {}): Promise<PredictionCopyDemoReport> {
  const resolved = { ...DEFAULT_OPTIONS, ...options };
  const ts = new Date().toISOString();
  const leaderboard = await fetchPolymarketLeaderboard(resolved);
  const candidateLeaders = leaderboard
    .map(normalizeTrader)
    .filter((trader): trader is PredictionCopyTrader => Boolean(trader))
    .filter((trader) => trader.pnl >= resolved.minPnlUsd)
    .slice(0, resolved.leaderboardLimit);

  const leadersWithData = await Promise.all(candidateLeaders.map(async (trader) => {
    const [positionsRaw, activities] = await Promise.all([
      fetchPolymarketUserPositions(trader.wallet, resolved).catch(() => []),
      fetchPolymarketUserActivity(trader.wallet, resolved).catch(() => [])
    ]);
    const lastActivityTs = activities
      .map((activity) => toIsoFromUnixSeconds(activity.timestamp))
      .filter((value): value is string => Boolean(value))
      .sort()
      .at(-1);
    const rejectionCounts: Record<string, number> = {};
    const positions = positionsRaw
      .map((position) => normalizePosition({ trader, position, lastActivityTs, options: resolved }))
      .flatMap((result) => {
        if (result.position) return [result.position];
        if (result.rejection) {
          rejectionCounts[result.rejection] = (rejectionCounts[result.rejection] ?? 0) + 1;
        }
        return [];
      });
    return {
      trader: scoreTrader({ trader, positions, activities }),
      positions,
      rejectionCounts
    } satisfies SelectedLeader;
  }));

  const selectedLeaders = leadersWithData
    .filter((leader) => leader.trader.activePositionCount > 0)
    .sort((a, b) => b.trader.score - a.trader.score || b.trader.pnl - a.trader.pnl)
    .slice(0, resolved.maxLeaders);
  const rejectionCounts = leadersWithData.reduce<Record<string, number>>((acc, leader) => {
    for (const [reason, count] of Object.entries(leader.rejectionCounts ?? {})) {
      acc[reason] = (acc[reason] ?? 0) + count;
    }
    return acc;
  }, {});

  const ideas = buildPredictionCopyIdeas({
    leaders: selectedLeaders,
    minConsensusWallets: resolved.minConsensusWallets,
    minIdeaValueUsd: resolved.minIdeaValueUsd
  });
  const actionCounts = ideas.reduce<Record<PredictionCopyIdea["action"], number>>((acc, idea) => {
    acc[idea.action] += 1;
    return acc;
  }, { watch: 0, "shadow-buy": 0 });
  const positions = selectedLeaders.flatMap((leader) => leader.positions)
    .sort((a, b) => b.convictionScore - a.convictionScore || b.currentValue - a.currentValue)
    .slice(0, 50);
  const blockers: string[] = [];

  if (candidateLeaders.length === 0) blockers.push("no-outsized-return-leaders");
  if (selectedLeaders.length === 0) blockers.push("no-active-leader-positions");
  if (rejectionCounts["out-of-domain"] > 0) blockers.push(`out-of-domain:${rejectionCounts["out-of-domain"]}`);
  if (ideas.length === 0) blockers.push("no-copy-ideas");
  if (actionCounts["shadow-buy"] === 0) blockers.push("no-shadow-buy-ideas");

  const summary = actionCounts["shadow-buy"] > 0
    ? `Built ${actionCounts["shadow-buy"]} shadow-buy idea(s) from ${selectedLeaders.length} active high-return Polymarket wallets inside the founder-approved domain filter.`
    : selectedLeaders.length > 0
      ? `Tracked ${selectedLeaders.length} active high-return Polymarket wallets inside the founder-approved domain filter, but no idea cleared the shadow-buy consensus gate yet.`
      : `No active Polymarket leader cohort was available for the founder-approved copy-demo lane${Object.keys(rejectionCounts).length > 0 ? ` (filters: ${Object.entries(rejectionCounts).map(([reason, count]) => `${reason}=${count}`).join(", ")})` : ""}.`;

  return {
    ts,
    venue: "polymarket",
    cohort: {
      leaderboardPeriod: resolved.leaderboardPeriod,
      consideredLeaders: candidateLeaders.length,
      selectedLeaders: selectedLeaders.length,
      selectedWallets: selectedLeaders.map((leader) => leader.trader.wallet),
      minPnlUsd: resolved.minPnlUsd,
      minConsensusWallets: resolved.minConsensusWallets,
      minIdeaValueUsd: resolved.minIdeaValueUsd,
      rejectionCounts
    },
    traders: selectedLeaders.map((leader) => leader.trader),
    positions,
    ideas,
    actionCounts,
    blockers,
    summary
  };
}
