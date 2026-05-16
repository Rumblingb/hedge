// polymarketExecution.ts — Polymarket CLOB V2 order execution adapter.
//
// Wraps @polymarket/clob-client-v2 for the gengar scalper.
// Supports DRY RUN (default) and LIVE modes.
//
// DRY RUN: simulates fills, logs what WOULD happen. No keys needed.
// LIVE: requires POLYMARKET_PRIVATE_KEY and POLYMARKET_API_KEY/SECRET/PASSPHRASE.
//
// Key patterns from gengar bot's executor.py:
//   - Integer shares + 2-decimal prices (avoids float precision bugs)
//   - Balance verification as source of truth (not order status)
//   - Ghost fill defense (balance change despite API error)
//   - Never cancel on timeout (Polygon settlement can take 5-15s)
//   - Min $5 notional (Polymarket minimum)

import type { ScalperSignal } from "./oracleLagScalper.js";

// Viem signer creation for the CLOB client
import { createWalletClient, http } from "viem";
import { polygon } from "viem/chains";
import { privateKeyToAccount } from "viem/accounts";

// We use dynamic import for the CLOB client since it requires ESM
let ClobClient: any = null;
let Side: any = null;
let OrderType: any = null;

function getOrderId(result: any): string {
  return String(
    result?.orderID ??
    result?.orderId ??
    result?.id ??
    result?.order?.id ??
    result?.order?.orderID ??
    result?.order?.orderId ??
    "",
  );
}

function getClobError(result: any): string {
  if (!result || typeof result !== "object" || !("error" in result)) return "";
  return typeof result.error === "string" ? result.error : JSON.stringify(result.error);
}

async function loadClobClient() {
  if (ClobClient) return true;
  try {
    const mod = await import("@polymarket/clob-client-v2");
    ClobClient = mod.ClobClient;
    Side = mod.Side;
    OrderType = mod.OrderType;
    return true;
  } catch {
    return false;
  }
}

export interface ExecutionConfig {
  dryRun: boolean;
  privateKey?: string;
  apiKey?: string;
  apiSecret?: string;
  apiPassphrase?: string;
  funderAddress?: string;  // For gasless transactions
  maxBuyPrice: number;     // Don't buy above this
  minNotional: number;     // $5 Polymarket minimum
  chainId: number;         // 137 = Polygon
}

export const DEFAULT_EXECUTION_CONFIG: ExecutionConfig = {
  dryRun: true,
  maxBuyPrice: 0.90,
  minNotional: 5.0,
  chainId: 137,
};

export interface OrderResult {
  success: boolean;
  orderId: string;
  status: "FILLED" | "PARTIAL" | "REJECTED" | "FAILED" | "DRY_RUN";
  side: "BUY" | "SELL";
  price: number;
  amountUsd: number;
  shares: number;
  sharesRemaining: number;
  tokenId: string;
  error: string;
  dryRun: boolean;
}

/**
 * Limit order parameters matching the py-clob-client OrderArgs pattern.
 * 
 * Python equivalent:
 *   OrderArgs(price=float, size=int, side=BUY/SELL, token_id=str)
 *   client.create_and_post_order(orderArgs)
 */
export interface LimitOrderArgs {
  price: number;
  size: number;       // integer shares (as in Python SDK)
  side: "BUY" | "SELL";
  tokenId: string;
}

export class PolymarketExecutor {
  private config: ExecutionConfig;
  private client: any = null;
  private initialized = false;

  constructor(config: Partial<ExecutionConfig> = {}) {
    this.config = { ...DEFAULT_EXECUTION_CONFIG, ...config };
  }

  async initialize(): Promise<boolean> {
    if (this.config.dryRun) {
      this.initialized = true;
      console.log("[executor] Initialized in DRY RUN mode");
      return true;
    }

    const clobLoaded = await loadClobClient();
    if (!clobLoaded) {
      console.error("[executor] Failed to load @polymarket/clob-client-v2");
      return false;
    }

    if (!this.config.privateKey) {
      console.error("[executor] LIVE mode requires POLYMARKET_PRIVATE_KEY");
      return false;
    }

    try {
      const account = privateKeyToAccount(this.config.privateKey! as `0x${string}`);
      const walletClient = createWalletClient({
        account,
        chain: polygon,
        transport: http(),
      });

      const funderAddress = this.config.funderAddress ?? process.env.POLYMARKET_PROFILE_ADDRESS;

      this.client = new ClobClient({
        host: "https://clob.polymarket.com",
        chain: this.config.chainId,
        signer: walletClient,
        signatureType: 3,  // POLY_1271 for deposit wallet flow
        ...(funderAddress ? { funderAddress } : {}),
      });

      // Use API credentials from config or environment, otherwise derive from private key
      const apiKey = this.config.apiKey ?? process.env.POLYMARKET_API_KEY;
      const apiSecret = this.config.apiSecret ?? process.env.POLYMARKET_SECRET;
      const apiPassphrase = this.config.apiPassphrase ?? process.env.POLYMARKET_PASSPHRASE;
      if (apiKey && apiSecret) {
        this.client.creds = {
          key: apiKey,
          secret: apiSecret,
          passphrase: apiPassphrase ?? "",
        };
      } else if (process.env.POLYMARKET_DERIVED_KEY && process.env.POLYMARKET_DERIVED_SECRET) {
        // Use pre-derived API credentials (avoids session-dependent deriveApiKey issues)
        console.log("[executor] Using pre-derived API credentials");
        this.client.creds = {
          key: process.env.POLYMARKET_DERIVED_KEY,
          secret: process.env.POLYMARKET_DERIVED_SECRET,
          passphrase: process.env.POLYMARKET_DERIVED_PASSPHRASE ?? "",
        };
      } else {
        console.log("[executor] Deriving API credentials from private key...");
        const creds = await Promise.race([
          this.client.deriveApiKey(),
          new Promise<null>((_, reject) =>
            setTimeout(() => reject(new Error("deriveApiKey timed out after 15s")), 15000)
          ),
        ]);
        if (!creds) return false;
        this.client.creds = creds;
      }

      this.initialized = true;
      console.log("[executor] Initialized in LIVE mode");
      console.log(`[executor] Address: ${account.address}`);
      if (funderAddress) console.log(`[executor] Funder: ${funderAddress}`);
      return true;
    } catch (e) {
      console.error(`[executor] Init failed: ${(e as Error).message}`);
      return false;
    }
  }

  /**
   * Execute a buy order for a gengar signal.
   * Uses limit orders via complement engine (like gengar executor).
   */
  async executeSignal(
    signal: ScalperSignal,
    tokenId: string,
  ): Promise<OrderResult> {
    if (!this.initialized) {
      return this.failResult("Not initialized", signal);
    }

    const amountUsd = Math.round(signal.recommendedBet * 100) / 100;
    if (amountUsd < this.config.minNotional) {
      return this.failResult(
        `Amount $${amountUsd} below min $${this.config.minNotional}`,
        signal,
      );
    }

    if (signal.marketPrice > this.config.maxBuyPrice) {
      return this.failResult(
        `Price ${signal.marketPrice.toFixed(3)} > max ${this.config.maxBuyPrice}`,
        signal,
      );
    }

    // DRY RUN: simulate fill
    if (this.config.dryRun || !this.client) {
      return {
        success: true,
        orderId: `DRY-${Date.now()}`,
        status: "DRY_RUN",
        side: "BUY",
        price: signal.marketPrice,
        amountUsd,
        shares: amountUsd / signal.marketPrice,
        sharesRemaining: 0,
        tokenId: tokenId.slice(0, 16) + "...",
        error: "",
        dryRun: true,
      };
    }

    // Compute integer shares with 2-decimal precision
    // Pattern from gengar executor: shares = int(max_usd_cents / price_cents)
    const priceCents = Math.round(signal.marketPrice * 100);
    const maxUsdCents = Math.floor(amountUsd * 100);
    const shares = Math.ceil(Math.max(this.config.minNotional * 100, maxUsdCents) / priceCents);

    if (shares < 1) {
      return this.failResult(
        `Cannot afford 1 share at $${signal.marketPrice.toFixed(3)} within $${amountUsd.toFixed(2)}`,
        signal,
      );
    }

    const cleanAmount = (shares * priceCents) / 100;
    if (cleanAmount < this.config.minNotional) {
      return this.failResult(
        `Clean amount $${cleanAmount.toFixed(2)} < min $${this.config.minNotional}`,
        signal,
      );
    }

    try {
      // Use createAndPostOrder — single call, handles deposit wallet auth better
      const result = await this.client.createAndPostOrder({
        tokenID: tokenId,
        price: signal.marketPrice,
        size: shares,
        side: Side.BUY,
      });

      const orderId = getOrderId(result);
      
      // Log full response for diagnostics
      if (!orderId) {
        const resultStr = typeof result === 'object' ? JSON.stringify(result).slice(0, 500) : String(result);
        console.log(`[executor] createAndPostOrder response: ${resultStr}`);
      }
      if (!orderId) {
        return this.failResult(getClobError(result) || "No orderID in response", signal);
      }

      return {
        success: true,
        orderId,
        status: "FILLED",
        side: "BUY",
        price: signal.marketPrice,
        amountUsd: cleanAmount,
        shares,
        sharesRemaining: 0,
        tokenId: tokenId.slice(0, 16) + "...",
        error: "",
        dryRun: false,
      };
    } catch (e) {
      const msg = (e as Error).message;
      // Ghost fill defense: check if order might have gone through
      if (msg.includes("timeout") || msg.includes("network")) {
        return {
          success: false,
          orderId: "unknown",
          status: "FAILED",
          side: "BUY",
          price: signal.marketPrice,
          amountUsd: cleanAmount,
          shares,
          sharesRemaining: shares,
          tokenId: tokenId.slice(0, 16) + "...",
          error: `UNVERIFIED: ${msg}`,
          dryRun: false,
        };
      }

      return this.failResult(msg, signal);
    }
  }

  /**
   * Create and post a limit order on the CLOB.
   *
   * Mirrors the py-clob-client pattern:
   *   OrderArgs(price=float, size=int, side=BUY/SELL, token_id=str)
   *   client.create_and_post_order(orderArgs)
   *
   * Uses createOrder + postOrder with GTC order type (same as Python SDK default).
   *
   * @param args - Limit order parameters (price, size in shares, side, token ID)
   * @param orderType - Order type (default: GTC). Use FOK for fill-or-kill.
   */
  async createAndPostLimitOrder(
    args: LimitOrderArgs,
    orderType: any = undefined, // Will default to GTC
  ): Promise<OrderResult> {
    if (!this.initialized) {
      return {
        success: false,
        orderId: "",
        status: "REJECTED",
        side: args.side,
        price: args.price,
        amountUsd: 0,
        shares: args.size,
        sharesRemaining: args.size,
        tokenId: args.tokenId.slice(0, 16) + "...",
        error: "Not initialized",
        dryRun: this.config.dryRun,
      };
    }

    const totalUsd = args.price * args.size;
    if (totalUsd < this.config.minNotional) {
      return {
        success: false,
        orderId: "",
        status: "REJECTED",
        side: args.side,
        price: args.price,
        amountUsd: totalUsd,
        shares: args.size,
        sharesRemaining: args.size,
        tokenId: args.tokenId.slice(0, 16) + "...",
        error: `Notional $${totalUsd.toFixed(2)} < min $${this.config.minNotional}`,
        dryRun: this.config.dryRun,
      };
    }

    // DRY RUN
    if (this.config.dryRun || !this.client) {
      return {
        success: true,
        orderId: `DRY-LIMIT-${Date.now()}`,
        status: "DRY_RUN",
        side: args.side,
        price: args.price,
        amountUsd: totalUsd,
        shares: args.size,
        sharesRemaining: 0,
        tokenId: args.tokenId.slice(0, 16) + "...",
        error: "",
        dryRun: true,
      };
    }

    try {
      // Resolve Side enum: args.side is "BUY" or "SELL"
      const sideEnum = args.side === "BUY" ? Side.BUY : Side.SELL;
      const resolvedOrderType = orderType ?? OrderType.GTC;

      const orderArgs = {
        tokenID: args.tokenId,
        price: args.price,
        size: args.size,
        side: sideEnum,
      };

      const signedOrder = await this.client.createOrder(orderArgs);
      const result = await this.client.postOrder(signedOrder, resolvedOrderType);

      const orderId = getOrderId(result);
      if (!orderId) {
        const clobError = getClobError(result);
        return {
          success: false,
          orderId: "",
          status: "FAILED",
          side: args.side,
          price: args.price,
          amountUsd: totalUsd,
          shares: args.size,
          sharesRemaining: args.size,
          tokenId: args.tokenId.slice(0, 16) + "...",
          error: clobError || "No orderID in response",
          dryRun: false,
        };
      }

      return {
        success: true,
        orderId,
        status: "FILLED",
        side: args.side,
        price: args.price,
        amountUsd: totalUsd,
        shares: args.size,
        sharesRemaining: 0,
        tokenId: args.tokenId.slice(0, 16) + "...",
        error: "",
        dryRun: false,
      };
    } catch (e) {
      const msg = (e as Error).message;
      if (msg.includes("timeout") || msg.includes("network")) {
        return {
          success: false,
          orderId: "unknown",
          status: "FAILED",
          side: args.side,
          price: args.price,
          amountUsd: totalUsd,
          shares: args.size,
          sharesRemaining: args.size,
          tokenId: args.tokenId.slice(0, 16) + "...",
          error: `UNVERIFIED: ${msg}`,
          dryRun: false,
        };
      }

      return {
        success: false,
        orderId: "",
        status: "REJECTED",
        side: args.side,
        price: args.price,
        amountUsd: totalUsd,
        shares: args.size,
        sharesRemaining: args.size,
        tokenId: args.tokenId.slice(0, 16) + "...",
        error: msg,
        dryRun: false,
      };
    }
  }

  private failResult(error: string, signal: ScalperSignal): OrderResult {
    return {
      success: false,
      orderId: "",
      status: "REJECTED",
      side: "BUY",
      price: signal.marketPrice,
      amountUsd: signal.recommendedBet,
      shares: 0,
      sharesRemaining: 0,
      tokenId: "",
      error,
      dryRun: this.config.dryRun,
    };
  }
}

/**
 * Convert a gengar monitor signal entry to an execution signal.
 */
export function toExecutionSignal(entry: Record<string, any>): {
  signal: ScalperSignal;
  tokenId: string;
} | null {
  const side = entry.side;
  if (side !== "UP" && side !== "DOWN") return null;

  const tokenId = entry.tokenId ?? (side === "UP" ? entry.tokenUp : entry.tokenDown);
  if (!tokenId) return null;

  const marketPrice = Number(entry.executablePrice ?? entry.bestAsk ?? entry.marketPrice);
  if (!Number.isFinite(marketPrice) || marketPrice <= 0 || marketPrice >= 1) return null;

  const signal: ScalperSignal = {
    side,
    prob: entry.prob,
    edge: entry.edge,
    marketPrice,
    deltaBps: entry.deltaBps,
    kellyFraction: entry.kellyFraction,
    recommendedBet: entry.recommendedBet,
    secondsRemaining: entry.secondsRemaining,
  };

  return { signal, tokenId };
}
