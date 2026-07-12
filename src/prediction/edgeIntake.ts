import { mkdir, readFile, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";

export interface PredictionDiscoveredEdge {
  id: string;
  sourceBucket: string;
  category: string;
  title: string;
  confidence: "high" | "medium" | "low" | "unknown";
  edgeType: "calendar" | "logical" | "contrarian" | "near-certainty" | "liquidity-trap" | "other";
  direction: string;
  edgeMagnitude: string | null;
  liquidityUsd: number | null;
  maxSpreadPct: number | null;
  marketSlugs: string[];
  verdict: "paper-watch" | "research-watch" | "avoid";
  blockers: string[];
  nextChecks: string[];
}

export interface PredictionEdgeIntakeReport {
  command: "prediction-edge-intake";
  generatedAt: string;
  inputPath: string;
  totalRawEdges: number;
  counts: Record<PredictionDiscoveredEdge["verdict"], number>;
  topEdges: PredictionDiscoveredEdge[];
  avoidEdges: PredictionDiscoveredEdge[];
  blockers: string[];
  doctrine: string[];
}

type RawEdge = Record<string, any>;

function toNumber(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string") {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
}

function normalizeConfidence(value: unknown): PredictionDiscoveredEdge["confidence"] {
  const normalized = String(value ?? "").toLowerCase();
  if (normalized === "high" || normalized === "medium" || normalized === "low") return normalized;
  return "unknown";
}

function flattenRawEdges(parsed: any): Array<{ bucket: string; edge: RawEdge }> {
  const buckets = parsed?.edges && typeof parsed.edges === "object" ? parsed.edges : parsed;
  if (!buckets || typeof buckets !== "object") return [];
  return Object.entries(buckets).flatMap(([bucket, value]) =>
    Array.isArray(value) ? value.map((edge) => ({ bucket, edge: edge as RawEdge })) : []
  );
}

function edgeType(bucket: string, edge: RawEdge): PredictionDiscoveredEdge["edgeType"] {
  const text = `${bucket} ${edge.title ?? ""} ${edge.edge_type ?? ""} ${edge.description ?? ""} ${edge.analysis ?? ""}`.toLowerCase();
  if (bucket.includes("thin") || text.includes("avoid") || text.includes("liquidity trap") || text.includes("broken market")) return "liquidity-trap";
  if (text.includes("calendar") || text.includes("temporal") || text.includes("cross-date") || text.includes("series")) return "calendar";
  if (text.includes("logical") || text.includes("entailment") || text.includes("must")) return "logical";
  if (text.includes("near-certainty") || text.includes("daily yield")) return "near-certainty";
  if (text.includes("contrarian") || text.includes("tail risk")) return "contrarian";
  return "other";
}

function edgeMarkets(edge: RawEdge): RawEdge[] {
  if (Array.isArray(edge.markets)) return edge.markets as RawEdge[];
  if (edge.market && typeof edge.market === "object") return [edge.market as RawEdge];
  return [];
}

function scoreVerdict(args: {
  confidence: PredictionDiscoveredEdge["confidence"];
  type: PredictionDiscoveredEdge["edgeType"];
  liquidityUsd: number | null;
  maxSpreadPct: number | null;
  marketSlugs: string[];
}): { verdict: PredictionDiscoveredEdge["verdict"]; blockers: string[] } {
  const blockers = [
    ...(args.type === "liquidity-trap" ? ["liquidity-trap"] : []),
    ...(args.marketSlugs.length === 0 ? ["missing-market-slug"] : []),
    ...(args.liquidityUsd !== null && args.liquidityUsd < 2_500 ? ["thin-liquidity"] : []),
    ...(args.maxSpreadPct !== null && args.maxSpreadPct > 0.05 ? ["wide-spread"] : []),
    ...(args.confidence === "unknown" ? ["unknown-confidence"] : [])
  ];
  if (blockers.includes("liquidity-trap") || blockers.includes("thin-liquidity") || blockers.includes("wide-spread")) {
    return { verdict: "avoid", blockers };
  }
  if ((args.confidence === "high" || args.confidence === "medium") && args.marketSlugs.length > 0) {
    return { verdict: "paper-watch", blockers };
  }
  return { verdict: "research-watch", blockers };
}

function normalizeEdge(bucket: string, edge: RawEdge): PredictionDiscoveredEdge {
  const markets = edgeMarkets(edge);
  const slugs = markets.map((market) => String(market.slug ?? "").trim()).filter(Boolean);
  const liquidities = markets.map((market) => toNumber(market.liquidity)).filter((value): value is number => value !== null);
  const spreads = markets.map((market) => toNumber(market.spread)).filter((value): value is number => value !== null);
  const confidence = normalizeConfidence(edge.confidence);
  const type = edgeType(bucket, edge);
  const liquidityUsd = liquidities.length > 0 ? Math.min(...liquidities) : null;
  const maxSpreadPct = spreads.length > 0 ? Math.max(...spreads) : null;
  const { verdict, blockers } = scoreVerdict({ confidence, type, liquidityUsd, maxSpreadPct, marketSlugs: slugs });
  return {
    id: String(edge.id ?? `${bucket}:${edge.title ?? "edge"}`),
    sourceBucket: bucket,
    category: String(edge.category ?? "unknown"),
    title: String(edge.title ?? edge.question ?? "unknown edge"),
    confidence,
    edgeType: type,
    direction: String(edge.edge_direction ?? edge.structure ?? edge.trade ?? edge.edge_type ?? "manual review required"),
    edgeMagnitude: edge.edge_magnitude ? String(edge.edge_magnitude) : null,
    liquidityUsd,
    maxSpreadPct,
    marketSlugs: slugs,
    verdict,
    blockers,
    nextChecks: [
      "Verify the market is active and not expired in Gamma before any paper route.",
      "Fetch executable ask/bid/depth and reject if spread or top-book depth fails.",
      "Re-read settlement rules and identify the falsifying event.",
      "Record a paper fill and resolve outcome before live approval."
    ]
  };
}

export async function buildPredictionEdgeIntakeReport(args: {
  inputPath?: string;
  outputPath?: string;
  now?: () => string;
} = {}): Promise<PredictionEdgeIntakeReport> {
  const inputPath = resolve(args.inputPath ?? process.env.BILL_POLYMARKET_EDGE_SOURCE_PATH ?? "/Users/brain/polymarket_edges_all_categories.json");
  const parsed = JSON.parse(await readFile(inputPath, "utf8"));
  const edges = flattenRawEdges(parsed).map(({ bucket, edge }) => normalizeEdge(bucket, edge));
  const counts = edges.reduce<Record<PredictionDiscoveredEdge["verdict"], number>>((acc, edge) => {
    acc[edge.verdict] += 1;
    return acc;
  }, { "paper-watch": 0, "research-watch": 0, avoid: 0 });
  const report: PredictionEdgeIntakeReport = {
    command: "prediction-edge-intake",
    generatedAt: args.now?.() ?? new Date().toISOString(),
    inputPath,
    totalRawEdges: edges.length,
    counts,
    topEdges: edges
      .filter((edge) => edge.verdict !== "avoid")
      .sort((left, right) =>
        (left.verdict === "paper-watch" ? -1 : 1) - (right.verdict === "paper-watch" ? -1 : 1)
        || (left.confidence === "high" ? -1 : left.confidence === "medium" ? 0 : 1)
        - (right.confidence === "high" ? -1 : right.confidence === "medium" ? 0 : 1)
        || (right.liquidityUsd ?? 0) - (left.liquidityUsd ?? 0)
      )
      .slice(0, 20),
    avoidEdges: edges.filter((edge) => edge.verdict === "avoid").slice(0, 20),
    blockers: [
      ...(counts["paper-watch"] > 0 ? [] : ["no-paper-watch-edges"]),
      "edge-intake is not execution approval"
    ],
    doctrine: [
      "Structural/calendar Polymarket ideas enter Bill as paper-watch only until live market, settlement, and fillability checks pass.",
      "Thin-liquidity anomalies are negative memory, not contrarian live trades.",
      "Wallet consensus can upgrade attention but cannot bypass settlement or depth gates."
    ]
  };

  if (args.outputPath) {
    const outputPath = resolve(args.outputPath);
    await mkdir(dirname(outputPath), { recursive: true });
    await writeFile(outputPath, `${JSON.stringify(report, null, 2)}\n`, "utf8");
  }
  return report;
}
