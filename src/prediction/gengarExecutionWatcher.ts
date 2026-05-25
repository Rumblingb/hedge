/**
 * gengarExecutionWatcher.ts — Monitors signal journal, routes to Polymarket executor.
 * Uses builder credentials + deposit wallet flow for CLOB v2.
 */

import { readFile, writeFile, } from "node:fs/promises";
import { existsSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

import { PolymarketExecutor } from "./polymarketExecution.js";
import { toExecutionSignal } from "./polymarketExecution.js";
import type { ScalperSignal } from "./oracleLagScalper.js";

const __dirname = dirname(fileURLToPath(import.meta.url));
const STATE_PATH = join(__dirname, "../../.rumbling-hedge/state/gengar-execution.json");
const SIGNAL_PATH = join(__dirname, "../../.rumbling-hedge/journal/gengar-signals.jsonl");
const CREDS_PATH = join(__dirname, "../../.rumbling-hedge/credentials/polymarket.json");
const POLL_MS = 15_000;

interface ExecutionState {
  lastExecutedSignal: number;
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

async function main() {
  const creds = await loadCreds();
  if (!creds) {
    console.error("[gengar-exec] No credentials found — cannot start");
    process.exit(1);
  }

  // Use builder credentials for proper CLOB auth
  const executor = new PolymarketExecutor({
    dryRun: false,
    privateKey: creds.private_key,            // EOA private key
    apiKey: creds.api_key,                    // Builder API key (019e066b...)
    apiSecret: creds.api_secret,              // Builder API secret
    apiPassphrase: creds.api_passphrase,      // Builder API passphrase
    funderAddress: creds.deposit_wallet.toLowerCase(),  // CLOB v2 requires lowercase
  });

  const initialized = await executor.initialize();
  if (!initialized) {
    console.error("[gengar-exec] Failed to initialize executor");
    process.exit(1);
  }

  let state: ExecutionState = { lastExecutedSignal: -1, totalExecuted: 0, totalFilled: 0, totalRejected: 0 };
  try {
    const saved = JSON.parse(await readFile(STATE_PATH, "utf8"));
    state = { ...state, ...saved };
  } catch {}

  console.log(`[gengar-exec] Starting (LIVE) — deposit wallet: ${creds.deposit_wallet}`);

  // Main polling loop
  while (true) {
    try {
      const signals = await readSignals();
      for (const entry of signals) {
        const signalNum = entry.signalNumber ?? entry.id;
        if (signalNum == null) continue;
        if (signalNum <= state.lastExecutedSignal) continue;

        const parsed = toExecutionSignal(entry);
        if (!parsed) {
          state.lastExecutedSignal = Math.max(state.lastExecutedSignal, signalNum);
          continue;
        }

        const { signal, tokenId } = parsed;
        state.lastExecutedSignal = signalNum;
        state.totalExecuted++;
        console.log(`[gengar-exec] Executing signal #${signalNum}: ${signal.side} @ $${signal.marketPrice} bet=$${signal.recommendedBet}`);

        const result = await executor.executeSignal(signal, tokenId);
        if (result.success) {
          state.totalFilled++;
          console.log(`[gengar-exec] ✅ FILLED #${signalNum} — order: ${result.orderId}`);
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

main().catch(e => {
  console.error("[gengar-exec] Fatal:", e?.message?.slice(0, 200) ?? e);
  process.exit(1);
});
