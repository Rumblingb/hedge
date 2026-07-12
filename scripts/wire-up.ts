// wire-up.ts — Connect EOA's $143 USDC to the CLOB for trading.
// Uses ClobClient.updateBalanceAllowance() to sync on-chain deposits.
import { ClobClient } from "@polymarket/clob-client-v2";
import { createWalletClient, http, formatUnits, parseUnits } from "viem";
import { polygon } from "viem/chains";
import { privateKeyToAccount } from "viem/accounts";

const FUNDING_APPROVAL_ENV = "HERMES_ALLOW_POLYMARKET_FUNDING";
const FUNDING_APPROVAL_VALUE = "I_UNDERSTAND_THIS_MOVES_FUNDS";
const fundingEnabled = String(process.env.BILL_POLYMARKET_FUNDING_ENABLED ?? "").toLowerCase() === "true";

if (!fundingEnabled || process.env[FUNDING_APPROVAL_ENV] !== FUNDING_APPROVAL_VALUE) {
  console.error("[wire-up] BLOCKED: Polymarket funding helpers are quarantined.");
  console.error("- BILL_POLYMARKET_FUNDING_ENABLED must be true");
  console.error(`- ${FUNDING_APPROVAL_ENV} must equal ${FUNDING_APPROVAL_VALUE}`);
  console.error("Use read-only CLOB research commands unless this is a supervised manual funding run.");
  process.exit(2);
}

const PRIVATE_KEY = process.env.POLYMARKET_PRIVATE_KEY;
if (!PRIVATE_KEY) { console.error("POLYMARKET_PRIVATE_KEY required"); process.exit(1); }

const API_KEY = process.env.POLYMARKET_API_KEY || process.env.POLYMARKET_DERIVED_KEY;
const API_SECRET = process.env.POLYMARKET_API_SECRET || process.env.POLYMARKET_DERIVED_SECRET;
const API_PASSPHRASE = process.env.POLYMARKET_API_PASSPHRASE || process.env.POLYMARKET_DERIVED_PASSPHRASE;

const USDC = "0x3c499c542cEF5E3811e1192ce70d8cC03d5c3359";
const EXCHANGE = "0x4bFb41d5B3570DeFd03C39a9A4D8dE6Bd8B8982E";

const account = privateKeyToAccount(PRIVATE_KEY as `0x${string}`);
const walletClient = createWalletClient({ account, chain: polygon, transport: http() });

async function main() {
  const addr = account.address;
  console.log(`Signer: ${addr}`);

  // 1. Check on-chain USDC balance
  const balHex = await walletClient.request({
    method: "eth_call",
    params: [{ to: USDC, data: `0x70a08231${"0".repeat(24)}${addr.slice(2)}` }, "latest"],
  } as any) as string;
  const balance = BigInt(balHex);
  console.log(`On-chain USDC: $${formatUnits(balance, 6)}`);

  if (balance < parseUnits("7", 6)) {
    console.error("❌ Need at least $7 USDC on-chain");
    process.exit(1);
  }

  // 2. Check allowance to Exchange
  const allowHex = await walletClient.request({
    method: "eth_call",
    params: [{ to: USDC, data: `0xdd62ed3e${"0".repeat(24)}${addr.slice(2)}${"0".repeat(24)}${EXCHANGE.slice(2)}` }, "latest"],
  } as any) as string;
  const allowance = BigInt(allowHex);
  console.log(`Exchange allowance: $${formatUnits(allowance, 6)}`);

  // 3. Approve if needed
  if (allowance < balance) {
    console.log("Approving USDC for CLOB Exchange...");
    const approveHash = await walletClient.writeContract({
      address: USDC,
      abi: [{ name: "approve", type: "function", inputs: [{ name: "spender", type: "address" }, { name: "amount", type: "uint256" }], outputs: [{ name: "", type: "bool" }], stateMutability: "nonpayable" }],
      functionName: "approve",
      args: [EXCHANGE, balance],
    });
    console.log(`✅ Approve tx: ${approveHash}`);
    await new Promise(r => setTimeout(r, 8000));
  } else { console.log("Allowance sufficient ✅"); }

  // 4. Init CLOB client and call updateBalanceAllowance
  console.log("\nSyncing balance with CLOB API...");
  const client = new ClobClient({
    host: "https://clob.polymarket.com",
    chain: 137,
    signer: walletClient,
  });
  (client as any).creds = { key: API_KEY!, secret: API_SECRET!, passphrase: API_PASSPHRASE! };

  try {
    const result = await (client as any).updateBalanceAllowance({});
    console.log("✅ updateBalanceAllowance result:", JSON.stringify(result, null, 2));
  } catch (e: any) {
    console.log("updateBalanceAllowance response:", e.message || "ok (may have returned non-error)");
  }

  // 5. Check balance via CLOB API
  await new Promise(r => setTimeout(r, 3000));
  try {
    const balResp = await (client as any).getBalanceAllowance({});
    console.log("\n📊 CLOB Balance/Allowance:", JSON.stringify(balResp, null, 2));
  } catch (e: any) {
    console.error("❌ getBalanceAllowance failed:", e.message);
  }
}

main().catch(e => { console.error("Fatal:", e); process.exit(1); });
