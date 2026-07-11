import { readFile, writeFile, mkdir } from "node:fs/promises";
import { dirname, resolve } from "node:path";

export interface FounderStrategyDirective {
  id: string;
  title: string;
  lane: "prediction" | "futures-core" | "options-us" | "crypto-liquid" | "macro-rates" | "long-only-compounder";
  edgeType: "structural-flow" | "behavioral" | "risk-premium" | "regime-gate" | "research-process";
  implementationStatus: "missing" | "partial" | "wired";
  requiredData: string[];
  implementationHooks: string[];
  guardrails: string[];
}

export interface FounderNotesIntake {
  command: "founder-notes-intake";
  generatedAt: string;
  sourcePaths: string[];
  outputPath: string;
  directives: FounderStrategyDirective[];
  priorityOrder: string[];
}

const DEFAULT_OUTPUT_PATH = ".rumbling-hedge/research/founder-notes/strategy-directives.latest.json";

async function readSafe(path: string): Promise<string> {
  try {
    return await readFile(path, "utf8");
  } catch {
    return "";
  }
}

function has(text: string, pattern: RegExp): boolean {
  return pattern.test(text);
}

function directive(args: FounderStrategyDirective): FounderStrategyDirective {
  return args;
}

export async function buildFounderNotesIntake(args: {
  sourcePaths?: string[];
  outputPath?: string;
  now?: () => string;
} = {}): Promise<FounderNotesIntake> {
  const sourcePaths = args.sourcePaths ?? [
    ".rumbling-hedge/research/founder-notes/apple-notes-2026-05-05.txt",
    "/Users/brain/hedge/.rumbling-hedge/research/founder-notes/apple-notes-2026-05-05.txt",
    "docs/FOUNDER_STRATEGY_NOTES_2026-05-05.md",
    "/Users/brain/hedge/docs/FOUNDER_STRATEGY_NOTES_2026-05-05.md",
    "/Users/brain/Documents/memorybrain/Agent-Shared/strategy-blueprint.md",
    "/Users/brain/Documents/memorybrain/Agent-Hermes/goal-bill-live-money.md"
  ];
  const resolvedSources = sourcePaths.map((path) => resolve(path));
  const text = (await Promise.all(resolvedSources.map(readSafe))).join("\n").toLowerCase();
  const generatedAt = args.now?.() ?? new Date().toISOString();
  const outputPath = resolve(args.outputPath ?? DEFAULT_OUTPUT_PATH);
  const directives: FounderStrategyDirective[] = [];

  if (has(text, /tail score|vix backwardation|capitulation/)) {
    directives.push(directive({
      id: "tail-score-risk-gate",
      title: "Tail Score risk gate from VIX, COT, and capitulation context",
      lane: "macro-rates",
      edgeType: "regime-gate",
      implementationStatus: "partial",
      requiredData: ["VIX spot and futures term structure", "COT leveraged/dealer z-scores", "put/call or capitulation proxy"],
      implementationHooks: ["MacroContext.tailScore", "risk sizing multiplier", "promotion gate blocker during backwardation stress"],
      guardrails: ["reduce exposure before adding convexity", "do not buy tail hedges without explicit options paper path"]
    }));
  }

  if (has(text, /post-news silence|institutional settlement|2\.5× atr|2\.5x atr/)) {
    directives.push(directive({
      id: "post-news-settlement",
      title: "Post-news settlement continuation after initial volatility resolves",
      lane: "futures-core",
      edgeType: "behavioral",
      implementationStatus: "missing",
      requiredData: ["economic calendar with release timestamps", "1m OHLCV with volume", "ATR and post-event volume normalization"],
      implementationHooks: ["red-folder event calendar", "news-spike detector", "volume-dry-up trigger"],
      guardrails: ["wait until blackout window exits or settlement bar confirms", "one contract max until 20+ paper events"]
    }));
  }

  if (has(text, /opening.*stop hunt|first 5 minutes|8:30-8:35|algo hunt/)) {
    directives.push(directive({
      id: "opening-stop-hunt",
      title: "Opening 5-minute stop hunt reversal around obvious levels",
      lane: "futures-core",
      edgeType: "structural-flow",
      implementationStatus: "partial",
      requiredData: ["prior session high/low", "round-number levels", "first five RTH minutes", "ATR"],
      implementationHooks: ["opening-stop-hunt profile", "session calendar", "VWAP target"],
      guardrails: ["RTH only", "max 30 minute hold", "reject if red-folder release overlaps open"]
    }));
  }

  if (has(text, /quarterly futures roll|roll window|front month|back month/)) {
    directives.push(directive({
      id: "quarterly-futures-roll-spread",
      title: "Quarterly futures roll spread, not directional outright",
      lane: "futures-core",
      edgeType: "structural-flow",
      implementationStatus: "missing",
      requiredData: ["front and next contract prices", "roll calendar", "spread history", "contract volume/open interest"],
      implementationHooks: ["expiryCalendar roll window", "calendar-spread simulator", "spread PnL ledger"],
      guardrails: ["spread-only exposure", "no outright directional surrogate", "paper fill model before live"]
    }));
  }

  if (has(text, /opex|gamma pin|max pain|zero-gamma|gex/)) {
    directives.push(directive({
      id: "opex-gamma-pin",
      title: "OPEX gamma pin and post-expiry volatility collapse",
      lane: "options-us",
      edgeType: "structural-flow",
      implementationStatus: "partial",
      requiredData: ["option chain open interest", "GEX/zero-gamma levels", "VIX term structure", "expiry calendar"],
      implementationHooks: ["dealerGamma status", "expiryCalendar", "options VRP report"],
      guardrails: ["no naked option selling", "defined-risk spreads only", "avoid short vol in backwardation/tail-score stress"]
    }));
  }

  if (has(text, /60\/40|quarterly.*rebalancing|last 3 trading days/)) {
    directives.push(directive({
      id: "quarterly-6040-rebalance",
      title: "Quarter-end 60/40 rebalance equity/bond flow",
      lane: "macro-rates",
      edgeType: "structural-flow",
      implementationStatus: "missing",
      requiredData: ["quarter-to-date equity return", "bond return", "last-three-trading-days calendar", "ES and ZN bars"],
      implementationHooks: ["calendar flow signal", "ES bias gate", "ZN bias gate"],
      guardrails: ["bias gate only until 12+ quarter-end samples", "do not trade if red-folder event dominates"]
    }));
  }

  if (has(text, /fomc.*fade|initial.*reaction|headline parsing/)) {
    directives.push(directive({
      id: "fomc-reaction-fade",
      title: "FOMC initial headline reaction fade",
      lane: "futures-core",
      edgeType: "behavioral",
      implementationStatus: "missing",
      requiredData: ["FOMC calendar", "market-implied surprise context", "first 5/15/30 minute bars", "pre-release level"],
      implementationHooks: ["red-folder event class", "event-spike-fade profile", "settlement review"],
      guardrails: ["paper-only for 20 FOMC-like events", "skip genuine surprise classifications until labeled"]
    }));
  }

  if (has(text, /yield curve|hy-ig|sofr|credit spreads/)) {
    directives.push(directive({
      id: "bond-credit-macro-progression",
      title: "Bond and credit leading-risk progression",
      lane: "macro-rates",
      edgeType: "regime-gate",
      implementationStatus: "missing",
      requiredData: ["10Y-2Y curve", "HY and IG OAS", "SOFR/Fed Funds spread", "Treasury auction metrics"],
      implementationHooks: ["FRED collector", "macro bias artifact", "futures/options sizing gate"],
      guardrails: ["context gate first", "no standalone macro execution before OOS validation"]
    }));
  }

  if (has(text, /research loop|rolling sharpe|suspend|strategy sharpe/)) {
    directives.push(directive({
      id: "weekly-research-retirement-loop",
      title: "Weekly research, promotion, and signal retirement loop",
      lane: "futures-core",
      edgeType: "research-process",
      implementationStatus: "partial",
      requiredData: ["strategy rolling Sharpe", "signal decay ledger", "paper/live fill outcomes", "OOS history"],
      implementationHooks: ["strategy-lab scheduler", "signal decay monitor", "promotion state"],
      guardrails: ["auto-suspend decay, never auto-promote live", "two-week demo shadow before live"]
    }));
  }

  const priorityOrder = [
    "tail-score-risk-gate",
    "weekly-research-retirement-loop",
    "post-news-settlement",
    "opening-stop-hunt",
    "quarterly-6040-rebalance",
    "quarterly-futures-roll-spread",
    "opex-gamma-pin",
    "fomc-reaction-fade",
    "bond-credit-macro-progression"
  ].filter((id) => directives.some((directive) => directive.id === id));

  const report: FounderNotesIntake = {
    command: "founder-notes-intake",
    generatedAt,
    sourcePaths: resolvedSources,
    outputPath,
    directives,
    priorityOrder
  };

  await mkdir(dirname(outputPath), { recursive: true });
  await writeFile(outputPath, `${JSON.stringify(report, null, 2)}\n`, "utf8");
  return report;
}
