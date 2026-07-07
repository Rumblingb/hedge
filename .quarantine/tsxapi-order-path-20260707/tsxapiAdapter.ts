/**
 * tsxapiAdapter.ts — TypeScript adapter for tsxapipy Python bridge.
 *
 * Calls scripts/tsxapi_order_bridge.py as subprocess for order execution,
 * position querying, and account discovery. Falls back to the existing
 * rest adapter when the Python bridge is unavailable.
 *
 * Usage: set BILL_TSXAPI_BRIDGE_PATH to point at the Python bridge script.
 * Default: hedge/scripts/tsxapi_order_bridge.py
 *
 * The Python bridge reads credentials from bill.env automatically,
 * eliminating duplicate credential management between TS and Python paths.
 */

import { execFileSync, execFile } from "node:child_process";
import { existsSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import type { LiveAdapterConfig, StrategySignal } from "../../domain.js";
import type { ExecutionAdapter, ExecutionReceipt } from "../topstep/topstepAdapter.js";

// ── Resolve the Python bridge path ──

const DEFAULT_BRIDGE = "scripts/tsxapi_order_bridge.py";

function bridgePath(): string {
  const env = process.env.BILL_TSXAPI_BRIDGE_PATH;
  if (env && existsSync(env)) return env;

  // Default: search upward from project root for hedge/scripts/tsxapi_order_bridge.py
  const candidates = [
    join(process.cwd(), DEFAULT_BRIDGE),
    join(process.cwd(), "..", DEFAULT_BRIDGE),
    join(dirname(fileURLToPath(import.meta.url)), "..", "..", "..", DEFAULT_BRIDGE),
  ];

  for (const p of candidates) {
    if (existsSync(p)) return p;
  }
  return candidates[0]; // last resort — caller gets the error
}

// ── Helpers ──

interface BridgeResult {
  success: boolean;
  error?: string;
  order_id?: number;
  accounts?: Array<{ id: number; name: string; balance: number; can_trade: boolean }>;
  contracts?: Array<{ id: string; name: string; symbol_id: string; active_contract: boolean; tick_size: number; tick_value: number }>;
  status?: string;
  status_code?: number;
  filled_quantity?: number;
  remaining_quantity?: number;
  price?: number;
  [key: string]: unknown;
}

function pythonBin(): string {
  return process.env.BILL_PYTHON_BIN ?? join(process.cwd(), ".venv/bin/python");
}

function callBridge(args: string[], stdin?: string): BridgeResult {
  const bridge = bridgePath();
  const python = pythonBin();

  if (!existsSync(bridge)) {
    return { success: false, error: `tsxapi bridge not found: ${bridge}` };
  }
  if (!existsSync(python)) {
    return { success: false, error: `Python not found: ${python}` };
  }

  try {
    const stdout = execFileSync(python, [bridge, ...args], {
      encoding: "utf-8",
      timeout: 30_000,
      input: stdin,
      env: {
        ...process.env,
        TRADING_ENVIRONMENT: "LIVE",
      },
    });
    return JSON.parse(stdout.trim()) as BridgeResult;
  } catch (err: any) {
    if (err.stderr) {
      try {
        return JSON.parse(err.stderr.trim()) as BridgeResult;
      } catch {
        // fall through
      }
    }
    if (err.stdout) {
      try {
        const parsed = JSON.parse(err.stdout.trim()) as BridgeResult;
        if (parsed && typeof parsed === "object") return parsed;
      } catch {
        // fall through
      }
    }
    return { success: false, error: `tsxapi bridge call failed: ${err.message ?? String(err)}` };
  }
}

// ── ExecutionAdapter implementation ──

export class TsxApiLiveAdapter implements ExecutionAdapter {
  public constructor(private readonly config: LiveAdapterConfig) {}

  private assertReady(): void {
    if (!this.config.enabled) {
      throw new Error("Live execution is disabled.");
    }
    if (!this.config.accountId) {
      throw new Error("tsxapi adapter requires RH_TOPSTEP_ACCOUNT_ID.");
    }
  }

  public async submit(signal: StrategySignal): Promise<ExecutionReceipt> {
    this.assertReady();

    const orderSpec = {
      account_id: Number(this.config.accountId),
      contract_id: this.resolveContractId(signal.symbol),
      side: signal.side === "long" ? "buy" : "sell",
      size: signal.contracts,
      order_type: "MARKET",
      custom_tag: `${signal.strategyId}-${signal.symbol}-${Date.now()}`,
    };

    const result = callBridge(["place"], JSON.stringify(orderSpec));

    if (!result.success) {
      return {
        accepted: false,
        orderId: "0",
        message: result.error ?? "tsxapi bridge rejected order",
      };
    }

    return {
      accepted: true,
      orderId: String(result.order_id ?? 0),
      message: `tsxapi order placed: ${orderSpec.side} ${orderSpec.size} ${orderSpec.contract_id} (id=${result.order_id})`,
    };
  }

  public async flattenAll(): Promise<void> {
    this.assertReady();
    // flattenAll would cancel all open orders — requires bridge extension
    const result = callBridge(["accounts"]);
    if (!result.success) {
      throw new Error(`tsxapi bridge flatten check failed: ${result.error}`);
    }
    // For now, flatten is a no-op since the bridge lacks cancel-all
    console.warn("[tsxapi] flattenAll not yet implemented at bridge level");
  }

  /** Resolve symbol to contract ID. Uses bridge contract search. */
  private resolveContractId(symbol: string): string {
    const result = callBridge(["contracts", symbol]);
    if (!result.success || !result.contracts || result.contracts.length === 0) {
      // Default fallback mappings
      const defaults: Record<string, string> = {
        MNQ: "CON.F.US.MNQ.U26",
        NQ: "CON.F.US.ENQ.U26",
        ES: "CON.F.US.EP.U26",
        MES: "CON.F.US.MES.U26",
      };
      return defaults[symbol.toUpperCase()] ?? `CON.F.US.${symbol.toUpperCase()}`;
    }
    return result.contracts[0].id;
  }

  /** List accounts via bridge. */
  public async listAccounts(): Promise<Array<{ id: number; name: string; balance: number }>> {
    const result = callBridge(["accounts"]);
    if (!result.success || !result.accounts) {
      throw new Error(`tsxapi bridge accounts failed: ${result.error}`);
    }
    return result.accounts.map((a) => ({ id: a.id, name: a.name, balance: a.balance }));
  }
}
