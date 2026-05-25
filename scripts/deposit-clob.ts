// deposit-clob.ts — Deposit USDC into Polymarket CLOB Exchange
import { ClobClient } from "@polymarket/clob-client-v2";
import { createWalletClient, http } from "viem";
import { polygon } from "viem/chains";
import { privateKeyToAccount } from "viem/accounts";

// Map DERIVED vars → API vars (env file uses DERIVED naming)
const PRIVATE_KEY = process.env.POLYMARKET_PRIVATE_KEY;
const API_KEY = process.env.POLYMARKET_API_KEY || process.env.POLYMARKET_DERIVED_KEY;
const API_SECRET = process.env.POLYMARKET_API_SECRET || process.env.POLYMARKET_DERIVED_SECRET;
const API_PASSPHRASE = process.env.POLYMARKET_API_PASSPHRASE || process.env.POLYMARKET_DERIVED_PASSPHRASE;

if (!PRIVATE_KEY) { console.error("POLYMARKET_PRIVATE_KEY required"); process.exit(1); }
if (!API_KEY) { console.log("No API key — will derive fresh ones"); }

async function main() {
  const account = privateKeyToAccount(PRIVATE_KEY as `0x${string}`);
  const walletClient = createWalletClient({ account, chain: polygon, transport: http() });

  const client = new ClobClient({
    host: "https://clob.polymarket.com",
    chain: 137,
    signer: walletClient,
  });

  // Set API creds if available
  if (API_KEY) {
    (client as any).creds = {
      key: API_KEY,
      secret: API_SECRET ?? "",
      passphrase: API_PASSPHRASE ?? "",
    };
  } else {
    const creds = await client.deriveApiKey();
    (client as any).creds = creds;
    console.log("Derived fresh API creds");
  }

  const addr = await (client as any).getAddress();
  const addr2 = addr ?? (await walletClient.getAddresses())[0];
  console.log(`Signer: ${addr2}`);

  // Check on-chain USDC balance
  const usdc = "0x3c499c542cEF5E3811e1192ce70d8cC03d5c3359";
  const exchange = "0x4bFb41d5B3570DeFd03C39a9A4D8dE6Bd8B8982E";

  // Use viem to check balance directly
  const balHex = await walletClient.request({
    method: "eth_call",
    params: [{
      to: usdc,
      data: "0x70a08231" + "000000000000000000000000" + addr2.slice(2),
    }, "latest"],
  }) as string;
  const onChainWei = BigInt(balHex);
  const onChain = Number(onChainWei) / 1e6;
  console.log(`On-chain USDC: $${onChain.toFixed(2)}`);

  if (onChain < 7) {
    console.log("❌ Less than $7 on-chain — nothing to deposit");
    return;
  }

  // Check existing allowance
  const allowHex = await walletClient.request({
    method: "eth_call",
    params: [{
      to: usdc,
      data: "0xdd62ed3e" +
        "000000000000000000000000" + addr2.slice(2) +
        "000000000000000000000000" + exchange.slice(2),
    }, "latest"],
  }) as string;
  const allowance = Number(BigInt(allowHex)) / 1e6;
  console.log(`Exchange allowance: $${allowance.toFixed(2)}`);

  const depositAmount = BigInt(Math.floor(onChain * 0.99 * 1e6).toString());

  // STEP 1: Approve if needed
  if (allowance < onChain * 0.99) {
    console.log(`Approving Exchange to spend $${(Number(depositAmount) / 1e6).toFixed(2)} USDC...`);
    const approveTx = await walletClient.writeContract({
      address: usdc as `0x${string}`,
      abi: [{
        name: "approve",
        type: "function",
        inputs: [
          { name: "spender", type: "address" },
          { name: "amount", type: "uint256" },
        ],
        outputs: [{ name: "", type: "bool" }],
        stateMutability: "nonpayable",
      }],
      functionName: "approve",
      args: [exchange as `0x${string}`, depositAmount],
    });
    console.log(`✅ Approve tx: ${approveTx}`);
    // Wait for confirmation
    await new Promise(r => setTimeout(r, 5000));
  } else {
    console.log("Allowance already sufficient ✅");
  }

  // STEP 2: Deposit into Exchange
  console.log(`Depositing $${(Number(depositAmount) / 1e6).toFixed(2)} USDC into CLOB Exchange...`);

  // Try using Exchange.deposit()
  try {
    const depositTx = await walletClient.writeContract({
      address: exchange as `0x${string}`,
      abi: [{
        name: "deposit",
        type: "function",
        inputs: [{ name: "amount", type: "uint256" }],
        outputs: [],
        stateMutability: "nonpayable",
      }],
      functionName: "deposit",
      args: [depositAmount],
    });
    console.log(`✅ Deposit tx: ${depositTx}`);
  } catch (e: any) {
    console.error("❌ Deposit failed:", e.message);
    console.log("Trying CLOB client methods instead...");
    
    // Try CLOB SDK deposit
    try {
      const result = await (client as any).approveAndDeposit?.({
        asset: usdc,
        amountWei: depositAmount.toString(),
      });
      console.log("✅ CLOB deposit result:", JSON.stringify(result));
    } catch (e2: any) {
      console.error("❌ CLOB deposit also failed:", e2.message);
      process.exit(1);
    }
  }

  // Wait and check balance
  await new Promise(r => setTimeout(r, 8000));
  
  // Check CLOB balance
  try {
    const balResponse = await (client as any).getBalanceAllowance?.();
    console.log("\nFinal CLOB Balance:", JSON.stringify(balResponse, null, 2));
  } catch (e: any) {
    console.error("Could not check CLOB balance:", e.message);
  }
}

main().catch((e) => { console.error("Fatal:", e); process.exit(1); });
