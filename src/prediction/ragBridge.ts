// ragBridge.ts — Polymarket RAG pipeline TypeScript adapter.
//
// Calls the Python polymarket_rag_bridge.py via child_process, reads
// the resulting PredictionEdgeIntakeReport, and makes it available to
// the hedge prediction cycle via edgeIntake.ts or as a standalone command.
//
// Usage:
//   npx tsx src/prediction/ragBridge.ts                        # run + print report
//   npx tsx src/prediction/ragBridge.ts --dry-run              # stdout only
//   npx tsx src/prediction/ragBridge.ts --limit 100            # more events

import { execFile } from "node:child_process";
import { mkdir, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { homedir } from "node:os";

// ── Types matching the Python report output ───────────────────

export interface RagEdge {
  id: string;
  sourceBucket: string;
  category: string;
  title: string;
  confidence: "high" | "medium" | "low" | "unknown";
  edgeType: string;
  direction: string;
  edgeMagnitude: string | null;
  liquidityUsd: number | null;
  maxSpreadPct: number | null;
  marketSlugs: string[];
  verdict: "paper-watch" | "research-watch" | "avoid";
  blockers: string[];
  nextChecks: string[];
  tradeRecommendation?: {
    price?: number;
    size?: number;
    side?: string;
  };
}

export interface RagBridgeReport {
  command: "rag-bridge";
  generatedAt: string;
  inputPath: string;
  totalRawEdges: number;
  counts: Record<string, number>;
  topEdges: RagEdge[];
  avoidEdges: RagEdge[];
  blockers: string[];
  doctrine: string[];
  pipelineSteps: string[];
  elapsedSeconds: number;
  errors: string[];
}

// ── Configuration ─────────────────────────────────────────────

const DEFAULT_PYTHON = resolve(
  __dirname, "..", "..", "..",
  "polymarket-agents", ".venv", "bin", "python3"
);

const BRIDGE_SCRIPT = resolve(
  __dirname, "..", "..", "..",
  "hermes", "kanban", "boards", "bill-financial-markets",
  "workspaces", "t_07ddde34", "polymarket_rag_bridge.py"
);

const DEFAULT_OUTPUT = resolve(
  process.env.BILL_POLYMARKET_EDGE_SOURCE_PATH ? dirname(process.env.BILL_POLYMARKET_EDGE_SOURCE_PATH) : ".rumbling-hedge/state",
  "rag-bridge-report.latest.json"
);

// ── Run ───────────────────────────────────────────────────────

export interface RunRagBridgeOptions {
  python?: string;
  script?: string;
  limit?: number;
  embedder?: "openai" | "ollama";
  output?: string;
  dryRun?: boolean;
  signal?: AbortSignal;
}

export function runRagBridge(
  options: RunRagBridgeOptions = {}
): Promise<RagBridgeReport> {
  const python = options.python ?? DEFAULT_PYTHON;
  const script = options.script ?? BRIDGE_SCRIPT;
  const limit = options.limit ?? 50;
  const embedder = options.embedder ?? "openai";

  return new Promise<RagBridgeReport>((resolvePromise, reject) => {
    const args = [
      script,
      "--limit", String(limit),
      "--embedder", embedder,
    ];

    if (options.dryRun) {
      args.push("--dry-run");
    }
    if (options.output) {
      args.push("--output", options.output);
    }

    // Load .env and merge into child env so the Python bridge
    // gets API keys even when the parent process has a clean env.
    const env = { ...process.env };
    try {
      const dotenv = require("dotenv");
      const cfg = dotenv.config({ path: resolve(homedir(), ".hermes", "profiles", "deepseek-researcher", ".env") });
      if (cfg.parsed) Object.assign(env, cfg.parsed);
    } catch { /* dotenv not available or .env not found — proceed with process.env */ }

    const child = execFile(
      python,
      args,
      {
        maxBuffer: 10 * 1024 * 1024, // 10 MB
        timeout: 120_000, // 2 min
        signal: options.signal,
        env: {
          ...env,
          PYTHONPATH: `${dirname(script)}:${env.PYTHONPATH ?? ""}`,
          // Pass through API keys — explicit fallback
          DEEPSEEK_API_KEY: env.DEEPSEEK_API_KEY ?? "",
          OPENAI_API_KEY: env.OPENAI_API_KEY ?? "",
          TAVILY_API_KEY: env.TAVILY_API_KEY ?? "",
          NEWSAPI_API_KEY: env.NEWSAPI_API_KEY ?? "",
        },
      },
      (error, stdout, stderr) => {
        if (error) {
          reject(new Error(
            `RAG bridge failed: ${error.message}\nStderr: ${stderr.slice(0, 500)}`
          ));
          return;
        }
        try {
          const report = JSON.parse(stdout) as RagBridgeReport;
          resolvePromise(report);
        } catch (parseError) {
          reject(new Error(
            `Failed to parse RAG bridge output: ${parseError}\nStdout: ${stdout.slice(0, 500)}`
          ));
        }
      }
    );
  });
}

export async function writeRagBridgeReport(
  report: RagBridgeReport,
  outputPath?: string
): Promise<string> {
  const path = resolve(outputPath ?? DEFAULT_OUTPUT);
  await mkdir(dirname(path), { recursive: true });
  await writeFile(path, JSON.stringify(report, null, 2) + "\n", "utf8");
  return path;
}

// ── CLI Entrypoint ────────────────────────────────────────────

async function main() {
  const args = process.argv.slice(2);
  const dryRun = args.includes("--dry-run");
  const limitIdx = args.indexOf("--limit");
  const limit = limitIdx >= 0 ? parseInt(args[limitIdx + 1] ?? "50", 10) : 50;
  const embedderIdx = args.indexOf("--embedder");
  const embedder = embedderIdx >= 0
    ? (args[embedderIdx + 1] === "ollama" ? "ollama" as const : "openai" as const)
    : "openai";
  const outputIdx = args.indexOf("--output");
  const output = outputIdx >= 0 ? args[outputIdx + 1] : undefined;

  console.error(`[rag-bridge-ts] Running RAG pipeline (limit=${limit}, embedder=${embedder})...`);

  const report = await runRagBridge({
    limit,
    embedder,
    output,
    dryRun,
  });

  console.error(
    `[rag-bridge-ts] Done: ${report.totalRawEdges} edges ` +
    `(${report.counts["paper-watch"] ?? 0} paper-watch, ` +
    `${report.counts["research-watch"] ?? 0} research-watch) in ` +
    `${report.elapsedSeconds}s`
  );

  if (report.errors.length > 0) {
    console.error("[rag-bridge-ts] Errors:", report.errors.slice(0, 5));
  }

  if (!dryRun) {
    const path = await writeRagBridgeReport(report, output);
    console.log(JSON.stringify({ ...report, outputPath: path }, null, 2));
  } else {
    console.log(JSON.stringify(report, null, 2));
  }
}

if (require.main === module) {
  main().catch((err) => {
    console.error(err);
    process.exit(1);
  });
}

export default { runRagBridge, writeRagBridgeReport };
