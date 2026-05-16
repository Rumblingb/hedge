#!/usr/bin/env node
// gengarExecutionWatcher.ts — Auto-executes gengar signals via Polymarket CLOB V2.
//
// Watches gengar-signals.jsonl for new signals and executes them.
// Dry-run by default (no keys needed). Set POLYMARKET_PRIVATE_KEY for live.
//
// Run: npx tsx src/prediction/gengarExecutionWatcher.ts

import { readFile, appendFile, mkdir, writeFile } from "node:fs/promises";
import { join } from "node:path";
import { PolymarketExecutor, toExecutionSignal, type OrderResult } from "./polymarketExecution.js";

const SIGNALS_PATH = join(process.cwd(), ".rumbling-hedge/journal/gengar-signals.jsonl");
const FILLS_PATH = join(process.cwd(), ".rumbling-hedge/journal/gengar-fills.jsonl");
const STATE_PATH = join(process.cwd(), ".rumbling-hedge/state/gengar-execution.json");
const REQUIRE_EXECUTABLE_QUOTE = process.env.BILL_GENGAR_EXEC_REQUIRE_CLOB !== "false";

interface ExecutionState {
  lastExecutedSignal: number; // index into signals array
  totalExecuted: number;
  totalFilled: number;
  totalRejected: number;
}

async function loadSignals(): Promise<any[]> {
  try {
    const raw = await readFile(SIGNALS_PATH, "utf8");
    return raw.trim().split("\n").filter(Boolean).map(l => JSON.parse(l));
  } catch { return []; }
}

async function run() {
  await mkdir(join(process.cwd(), ".rumbling-hedge/journal"), { recursive: true });
  await mkdir(join(process.cwd(), ".rumbling-hedge/state"), { recursive: true });

  const dryRun = !process.env.POLYMARKET_PRIVATE_KEY;

  let executor = new PolymarketExecutor({
    dryRun,
    privateKey: process.env.POLYMARKET_PRIVATE_KEY,
    funderAddress: process.env.POLYMARKET_PROFILE_ADDRESS,
    apiKey: process.env.POLYMARKET_API_KEY,
    apiSecret: process.env.POLYMARKET_API_SECRET,
    apiPassphrase: process.env.POLYMARKET_API_PASSPHRASE,
  });

  const initialized = await executor.initialize();
  if (!initialized) {
    console.error("[gengar-exec] Failed to initialize executor");
    // Keep running in dry-run fallback mode instead of crashing
    console.log("[gengar-exec] Falling back to DRY RUN mode");
    const dryExecutor = new PolymarketExecutor({ dryRun: true });
    await dryExecutor.initialize();
    executor = dryExecutor;
  }

  let state: ExecutionState = { lastExecutedSignal: -1, totalExecuted: 0, totalFilled: 0, totalRejected: 0 };
  try {
    const saved = JSON.parse(await readFile(STATE_PATH, "utf8"));
    state = { ...state, ...saved };
  } catch {}

  console.log(`[gengar-exec] Starting execution watcher (${dryRun ? "DRY RUN" : "LIVE"})`);
  console.log(`[gengar-exec] Last executed: #${state.lastExecutedSignal}, Total: ${state.totalExecuted}`);

  while (true) {
    try {
      const signals = await loadSignals();

      for (let i = state.lastExecutedSignal + 1; i < signals.length; i++) {
        const entry = signals[i];
        if (REQUIRE_EXECUTABLE_QUOTE && entry.executablePrice === undefined && entry.bestAsk === undefined) {
          const fillEntry = {
            ts: new Date().toISOString(),
            signalIndex: i,
            signalTs: entry.ts,
            signalSide: entry.side,
            success: false,
            orderId: "",
            status: "REJECTED",
            side: "BUY",
            price: entry.marketPrice ?? 0,
            amountUsd: entry.recommendedBet ?? 0,
            shares: 0,
            sharesRemaining: 0,
            tokenId: "",
            error: "missing executable CLOB quote",
            dryRun,
          };
          await appendFile(FILLS_PATH, JSON.stringify(fillEntry) + "\n");
          state.lastExecutedSignal = i;
          state.totalExecuted++;
          state.totalRejected++;
          await writeFile(STATE_PATH, JSON.stringify(state));
          console.log(`[gengar-exec] Rejecting signal #${i}: missing executable CLOB quote`);
          continue;
        }

        const exec = toExecutionSignal(entry);

        if (!exec) {
          state.lastExecutedSignal = i;
          await writeFile(STATE_PATH, JSON.stringify(state));
          continue;
        }

        const { signal, tokenId } = exec;

        console.log(`[gengar-exec] Executing signal #${i}: ${signal.side} @ $${signal.marketPrice.toFixed(3)} bet=$${signal.recommendedBet.toFixed(0)}`);

        const result = await executor.executeSignal(signal, tokenId);

        const fillEntry = {
          ts: new Date().toISOString(),
          signalIndex: i,
          signalTs: entry.ts,
          signalSide: signal.side,
          ...result,
        };

        await appendFile(FILLS_PATH, JSON.stringify(fillEntry) + "\n");

        state.lastExecutedSignal = i;
        state.totalExecuted++;

        if (result.success) {
          state.totalFilled++;
          console.log(`[gengar-exec] ✓ ${result.status} | ${result.side} ${result.shares.toFixed(0)} shares @ $${result.price.toFixed(3)} = $${result.amountUsd.toFixed(2)} | ${result.orderId}`);
        } else {
          state.totalRejected++;
          console.log(`[gengar-exec] ✗ ${result.status} | ${result.error}`);
        }

        await writeFile(STATE_PATH, JSON.stringify(state));
      }
    } catch (e) {
      console.error(`[gengar-exec] Error: ${(e as Error).message}`);
    }

    await sleep(5000); // Check every 5 seconds
  }
}

function sleep(ms: number): Promise<void> {
  return new Promise(resolve => setTimeout(resolve, ms));
}

run().catch(e => {
  console.error("[gengar-exec] Fatal:", e.message);
  process.exit(1);
});
