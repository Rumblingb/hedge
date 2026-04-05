import type { StrategySignal } from "../../domain.js";

export interface ExecutionReceipt {
  accepted: boolean;
  orderId: string;
  message: string;
}

export interface ExecutionAdapter {
  submit(signal: StrategySignal): Promise<ExecutionReceipt>;
  flattenAll(): Promise<void>;
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
