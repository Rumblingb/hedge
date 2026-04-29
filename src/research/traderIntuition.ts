import { readFile } from "node:fs/promises";
import { resolve } from "node:path";
import { ALLOWED_TOPSTEP_MARKETS, SUPPORTED_STRATEGY_IDS, type SupportedStrategyId } from "../domain.js";

export interface TraderIntuition {
  paths: string[];
  loadedPaths: string[];
  preferredStrategies: SupportedStrategyId[];
  preferredSymbols: string[];
  riskNotes: string[];
  summaryLines: string[];
}

const STRATEGY_KEYWORDS: Array<{ strategyId: SupportedStrategyId; needles: string[] }> = [
  { strategyId: "session-momentum", needles: ["session momentum", "trend day", "continuation", "open drive", "breakout"] },
  { strategyId: "opening-range-reversal", needles: ["opening range", "opening reversal", "open reversal", "opening auction"] },
  { strategyId: "liquidity-reversion", needles: ["liquidity sweep", "sweep and reverse", "mean reversion", "fade", "rebalance"] },
  { strategyId: "ict-displacement", needles: ["ict", "displacement", "fair value gap", "fvg", "market structure shift", "mss"] }
];

const SYMBOL_ALIASES: Array<{ symbol: string; needles: string[] }> = [
  { symbol: "NQ", needles: ["nq", "nasdaq", "nas100", "mnq"] },
  { symbol: "ES", needles: ["es", "s&p", "spx", "mes"] },
  { symbol: "CL", needles: ["cl", "crude", "wti", "oil"] },
  { symbol: "GC", needles: ["gc", "gold", "xau"] },
  { symbol: "6E", needles: ["6e", "eurusd", "euro"] },
  { symbol: "ZN", needles: ["zn", "10y", "10-year", "treasury"] }
];

function unique<T>(values: T[]): T[] {
  return Array.from(new Set(values));
}

function defaultPaths(env: NodeJS.ProcessEnv): string[] {
  const configured = env.BILL_TRADER_INTUITION_PATHS
    ?.split(",")
    .map((path) => path.trim())
    .filter(Boolean);
  return configured && configured.length > 0
    ? configured
    : [
        "docs/FOUNDER_INPUTS.md",
        ".rumbling-hedge/research/trader-intuition.md",
        ".rumbling-hedge/research/trader-intuition.json"
      ];
}

function extractRiskNotes(text: string): string[] {
  return text
    .split(/\r?\n/)
    .map((line) => line.trim().replace(/^-+\s*/, ""))
    .filter((line) => /(risk|drawdown|no[-\s]?go|blackout|default:|survivability|repeatability|demo|paper|guardrail)/i.test(line))
    .slice(0, 10);
}

export async function loadTraderIntuition(options: {
  paths?: string[];
  env?: NodeJS.ProcessEnv;
} = {}): Promise<TraderIntuition> {
  const env = options.env ?? process.env;
  const paths = options.paths ?? defaultPaths(env);
  const loadedPaths: string[] = [];
  const texts: string[] = [];

  for (const path of paths) {
    const resolvedPath = resolve(path);
    try {
      texts.push(await readFile(resolvedPath, "utf8"));
      loadedPaths.push(resolvedPath);
    } catch {
      // Optional founder/local intuition files are best-effort.
    }
  }

  const corpus = texts.join("\n\n").toLowerCase();
  const allowedSymbolSet = new Set<string>(ALLOWED_TOPSTEP_MARKETS);
  const preferredStrategies = unique(
    STRATEGY_KEYWORDS
      .filter((entry) => entry.needles.some((needle) => corpus.includes(needle)))
      .map((entry) => entry.strategyId)
      .filter((strategyId) => (SUPPORTED_STRATEGY_IDS as readonly string[]).includes(strategyId))
  );
  const preferredSymbols = unique(
    SYMBOL_ALIASES
      .filter((entry) => allowedSymbolSet.has(entry.symbol) && entry.needles.some((needle) => corpus.includes(needle)))
      .map((entry) => entry.symbol)
  );
  const riskNotes = unique(texts.flatMap(extractRiskNotes));
  const summaryLines = loadedPaths.length === 0
    ? ["no trader intuition files loaded"]
    : [
        `loaded ${loadedPaths.length} trader intuition file(s)`,
        `intuition strategies: ${preferredStrategies.join(", ") || "none"}`,
        `intuition symbols: ${preferredSymbols.join(", ") || "none"}`,
        `risk notes: ${riskNotes.length}`
      ];

  return {
    paths: paths.map((path) => resolve(path)),
    loadedPaths,
    preferredStrategies,
    preferredSymbols,
    riskNotes,
    summaryLines
  };
}
