import type { StrategySignal } from "../../domain.js";
import { HARD_GUARDRAIL_BOUNDS } from "../../risk/guardrails.js";

export interface ExecutionReceipt {
  accepted: boolean;
  orderId: string;
  message: string;
}

export interface ExecutionAdapter {
  submit(signal: StrategySignal): Promise<ExecutionReceipt>;
  flattenAll(): Promise<void>;
}

export interface TopstepBracketOrderSpec {
  accountId: string;
  symbol: string;
  side: "buy" | "sell";
  quantity: number;
  entryPrice: number;
  stopPrice: number;
  targetPrice: number;
  rr: number;
  strategyTag: string;
}

function ensureFinitePositive(value: number, label: string): void {
  if (!Number.isFinite(value) || value <= 0) {
    throw new Error(`Topstep order spec has invalid ${label}: ${value}`);
  }
}

export function buildTopstepBracketOrderSpec(args: {
  signal: StrategySignal;
  accountId: string;
}): TopstepBracketOrderSpec {
  const { signal, accountId } = args;
  ensureFinitePositive(signal.entry, "entry price");
  ensureFinitePositive(signal.stop, "stop price");
  ensureFinitePositive(signal.target, "target price");

  if (!Number.isInteger(signal.contracts) || signal.contracts <= 0) {
    throw new Error(`Topstep order spec has invalid contracts: ${signal.contracts}`);
  }

  if (signal.contracts > HARD_GUARDRAIL_BOUNDS.maxContracts) {
    throw new Error(`Topstep order spec breaches hard max contracts: ${signal.contracts}`);
  }

  if (signal.rr < HARD_GUARDRAIL_BOUNDS.minRr) {
    throw new Error(`Topstep order spec breaches hard minimum RR: ${signal.rr}`);
  }

  const side = signal.side === "long" ? "buy" : "sell";

  return {
    accountId,
    symbol: signal.symbol,
    side,
    quantity: signal.contracts,
    entryPrice: signal.entry,
    stopPrice: signal.stop,
    targetPrice: signal.target,
    rr: Number(signal.rr.toFixed(4)),
    strategyTag: signal.strategyId
  };
}

export class TopstepLiveAdapter implements ExecutionAdapter {
  public constructor(private readonly config: { enabled: boolean; baseUrl?: string; accountId?: string; apiKey?: string }) {}

  private assertReady(): void {
    if (!this.config.enabled) {
      throw new Error("Live execution is disabled. Keep Rumbling Hedge in paper mode until you wire a reviewed local-device adapter.");
    }

    if (!this.config.baseUrl || !this.config.accountId || !this.config.apiKey) {
      throw new Error("Topstep live adapter is missing required credentials.");
    }
  }

  public async submit(signal: StrategySignal): Promise<ExecutionReceipt> {
    this.assertReady();
    throw new Error(`Live submit is intentionally not implemented in v0.1. Wire your reviewed Topstep client here before using ${signal.symbol}.`);
  }

  public async flattenAll(): Promise<void> {
    this.assertReady();
    throw new Error("Live flatten is intentionally not implemented in v0.1.");
  }
}
