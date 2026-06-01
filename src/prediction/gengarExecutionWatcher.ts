/**
 * gengarExecutionWatcher.ts — Monitors signal journal, routes to Polymarket executor.
 * Uses builder credentials + deposit wallet flow for CLOB v2.
 */

import { readFile, writeFile, } from "node:fs/promises";
import { existsSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

import { PolymarketExecutor } from "./polymarketExecution.js";
import { toExecutionSignal } from "./polymarketExecution.js";
import { evaluateLiveGate } from "./execution/liveGate.js";
import type { ScalperSignal } from "./oracleLagScalper.js";

const __dirname = dirname(fileURLToPath(import.meta.url));
const STATE_PATH = join(__dirname, "../../.rumbling-hedge/state/gengar-execution.json");
const SIGNAL_PATH = join(__dirname, "../../.rumbling-hedge/journal/gengar-signals.jsonl");
const CREDS_PATH = join(__dirname, "../../.rumbling-hedge/credentials/polymarket.json");
const POLL_MS = 15_000;

interface ExecutionState {
  lastExecutedSignal: number;
  lastExecutedTs: string;
  totalExecuted: number;
  totalFilled: number;
  totalRejected: number;
}

interface PolymarketCreds {
  private_key: string;
  api_key: string;
  api_secret: string;
  api_passphrase: string;
  deposit_wallet: string;
  builder_address: string;
}

async function loadCreds(): Promise<PolymarketCreds | null> {
  try {
    const raw = await readFile(CREDS_PATH, "utf8");
    return JSON.parse(raw);
  } catch {
    return null;
  }
}

async function readSignals(): Promise<any[]> {
  try {
    const raw = await readFile(SIGNAL_PATH, "utf8");
    return raw.trim().split("\n").filter(Boolean).map(l => JSON.parse(l));
  } catch {
    return [];
  }
}

async function saveState(state: ExecutionState): Promise<void> {
  await writeFile(STATE_PATH, JSON.stringify(state), "utf8");
}

function envTrue(name: string): boolean {
  return /^(1|true|yes|on)$/i.test(String(process.env[name] ?? "").trim());
}

function envFlag(env: NodeJS.ProcessEnv, name: string): boolean {
  return /^(1|true|yes|on)$/i.test(String(env[name] ?? "").trim());
}

export function evaluateGengarLiveExecutionGate(env: NodeJS.ProcessEnv = process.env): {
  liveIntent: boolean;
  ok: boolean;
  failures: string[];
} {
  const failures: string[] = [];
  const liveIntent = envFlag(env, "BILL_GENGAR_LIVE_EXECUTION_ENABLED")
    || envFlag(env, "BILL_PREDICTION_LIVE_EXECUTION_ENABLED")
    || String(env.BILL_PREDICTION_EXECUTION_MODE ?? "").toLowerCase() === "live";

  if (!envFlag(env, "BILL_GENGAR_LIVE_EXECUTION_ENABLED")) {
    failures.push("BILL_GENGAR_LIVE_EXECUTION_ENABLED must be exactly 'true'.");
  }
  if (String(env.BILL_PREDICTION_EXECUTION_MODE ?? "").toLowerCase() !== "live") {
    failures.push("BILL_PREDICTION_EXECUTION_MODE must be live.");
  }

  const predictionLiveGate = evaluateLiveGate(env);
  failures.push(...predictionLiveGate.failures);
  return { liveIntent, ok: failures.length === 0, failures };
}

async function main() {
  const liveGate = evaluateGengarLiveExecutionGate(process.env);
  if (liveGate.liveIntent && !liveGate.ok) {
    console.error(`[gengar-exec] Live intent refused: ${liveGate.failures.join("; ")}`);
    process.exit(1);
  }
  const liveMode = liveGate.ok;
  const creds = liveMode ? await loadCreds() : await loadCreds().catch(() => null);
  if (liveMode && !creds) {
    console.error("[gengar-exec] Live mode requested but no credentials found — refusing to start");
    process.exit(1);
  }

  const executor = new PolymarketExecutor({
    dryRun: !liveMode,
    privateKey: creds?.private_key,            // EOA private key
    apiKey: creds?.api_key,                    // Builder API key
    apiSecret: creds?.api_secret,              // Builder API secret
    apiPassphrase: creds?.api_passphrase,      // Builder API passphrase
    funderAddress: creds?.deposit_wallet?.toLowerCase(),  // CLOB v2 requires lowercase
  });

  const initialized = await executor.initialize();
  if (!initialized) {
    console.error("[gengar-exec] Failed to initialize executor");
    process.exit(1);
  }

  let state: ExecutionState = { lastExecutedSignal: -1, lastExecutedTs: "", totalExecuted: 0, totalFilled: 0, totalRejected: 0 };
  try {
    const saved = JSON.parse(await readFile(STATE_PATH, "utf8"));
    state = { ...state, ...saved, lastExecutedTs: saved.lastExecutedTs ?? state.lastExecutedTs };
  } catch {}

  const mode = liveMode ? "LIVE" : "DRY_RUN";
  const wallet = creds?.deposit_wallet ?? "not-loaded";
  console.log(`[gengar-exec] Starting (${mode}) — deposit wallet: ${wallet}`);

  // Main polling loop
  while (true) {
    try {
      const signals = await readSignals();
      // Track by signalNumber if available, otherwise by ts
      let autoCounter = state.lastExecutedSignal;
      for (const entry of signals) {
        const signalNum = entry.signalNumber ?? entry.id;
        if (signalNum != null) {
          if (signalNum <= state.lastExecutedSignal) continue;
        } else {
          // No signalNumber — use ts-based dedup
          const ts = entry.ts ?? "";
          if (ts && ts <= state.lastExecutedTs) continue;
          if (!ts) continue; // skip entries without any identifier
          autoCounter = Math.max(autoCounter, state.lastExecutedSignal) + 1;
        }

        const parsed = toExecutionSignal(entry);
        if (!parsed) {
          if (signalNum != null) {
            state.lastExecutedSignal = Math.max(state.lastExecutedSignal, signalNum);
          }
          continue;
        }

        const { signal, tokenId } = parsed;
        const num = signalNum ?? autoCounter;

        // External-alpha audit guard: the public Polymarket websocket trade side is
        // not authoritative. Historical microstructure research shows frequent sign
        // flips, so never execute any future signal that explicitly depends on raw
        // websocket trade-side inference unless a stronger confirmation is attached.
        if (entry.tradeSideSource === "websocket" && entry.quoteReactionConfirmed !== true && entry.onchainFillConfirmed !== true) {
          state.lastExecutedSignal = num;
          state.lastExecutedTs = entry.ts ?? state.lastExecutedTs;
          state.totalRejected++;
          console.log(`[gengar-exec] ✗ REJECTED #${num} — websocket trade-side signal lacks on-chain/quote-reaction confirmation`);
          await saveState(state);
          continue;
        }

        state.lastExecutedSignal = num;
        state.lastExecutedTs = entry.ts ?? state.lastExecutedTs;
        state.totalExecuted++;
        console.log(`[gengar-exec] ${liveMode ? "Executing" : "Dry-run"} signal #${num}: ${signal.side} @ $${signal.marketPrice} bet=$${signal.recommendedBet}`);

        const result = await executor.executeSignal(signal, tokenId);
        if (result.success) {
          if (!result.dryRun) state.totalFilled++;
          console.log(`[gengar-exec] ${result.dryRun ? "DRY_RUN" : "FILLED"} #${num} — order: ${result.orderId}`);
        } else {
          state.totalRejected++;
          console.log(`[gengar-exec] ✗ REJECTED | ${result.error?.slice(0, 100)}`);
        }

        await saveState(state);
      }
    } catch (e: any) {
      console.error(`[gengar-exec] Loop error: ${e.message?.slice(0, 100)}`);
    }

    await new Promise(r => setTimeout(r, POLL_MS));
  }
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  main().catch(e => {
    console.error("[gengar-exec] Fatal:", e?.message?.slice(0, 200) ?? e);
    process.exit(1);
  });
}
