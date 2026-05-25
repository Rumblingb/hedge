// deposit-simple.ts — Approve + Deposit USDC into CLOB Exchange
// Uses viem walletClient directly. No CLOB SDK needed for on-chain tx.
const PRIVATE_KEY = process.env.POLYMARKET_PRIVATE_KEY;
if (!PRIVATE_KEY) { console.error("POLYMARKET_PRIVATE_KEY required"); process.exit(1); }

import { createWalletClient, http, formatUnits, parseUnits } from "viem";
import { polygon } from "viem/chains";
import { privateKeyToAccount } from "viem/accounts";

const USDC = "0x3c499c542cEF5E3811e1192ce70d8cC03d5c3359";
const EXCHANGE = "0x4bFb41d5B3570DeFd03C39a9A4D8dE6Bd8B8982E";

const account = privateKeyToAccount(PRIVATE_KEY as `0x${string}`);
const walletClient = createWalletClient({ account, chain: polygon, transport: http() });

const addr = account.address;
console.log(`Signer: ${addr}`);

// Balance
const balData = `0x70a08231${"0".repeat(24)}${addr.slice(2)}`;
const balHex = await walletClient.request({
  method: "eth_call",
  params: [{ to: USDC, data: balData }, "latest"],
} as any) as string;
const balance = BigInt(balHex);
console.log(`On-chain USDC: $${formatUnits(balance, 6)}`);

if (balance < parseUnits("7", 6)) {
  console.log("❌ Less than $7 — nothing to deposit");
  process.exit(0);
}

// Allowance
const allowData = `0xdd62ed3e${"0".repeat(24)}${addr.slice(2)}${"0".repeat(24)}${EXCHANGE.slice(2)}`;
const allowHex = await walletClient.request({
  method: "eth_call",
  params: [{ to: USDC, data: allowData }, "latest"],
} as any) as string;
const allowance = BigInt(allowHex);
console.log(`Current Exchange allowance: $${formatUnits(allowance, 6)}`);

// Keep 1 USDC for gas, deposit rest
const depositAmt = balance - parseUnits("1", 6);

// STEP 1: Approve
if (allowance < depositAmt) {
  console.log(`Approving $${formatUnits(depositAmt, 6)} USDC for Exchange...`);
  const approveHash = await walletClient.writeContract({
    address: USDC,
    abi: [{ name: "approve", type: "function", inputs: [{ name: "spender", type: "address" }, { name: "amount", type: "uint256" }], outputs: [{ name: "", type: "bool" }], stateMutability: "nonpayable" }],
    functionName: "approve",
    args: [EXCHANGE, depositAmt],
  });
  console.log(`✅ Approve tx: ${approveHash}`);
  await new Promise(r => setTimeout(r, 8000));
} else {
  console.log("Allowance sufficient ✅");
}

// STEP 2: Deposit
console.log(`Depositing $${formatUnits(depositAmt, 6)} USDC into CLOB Exchange...`);
try {
  const depositHash = await walletClient.writeContract({
    address: EXCHANGE,
    abi: [{ name: "deposit", type: "function", inputs: [{ name: "amount", type: "uint256" }], outputs: [], stateMutability: "nonpayable" }],
    functionName: "deposit",
    args: [depositAmt],
  });
  console.log(`✅ Deposit tx: ${depositHash}`);
  console.log("Waiting for confirmation...");
  await new Promise(r => setTimeout(r, 12000));
  console.log("✅ Deposit should be complete. Restart watcher to verify.");
} catch (e: any) {
  console.error(`❌ Deposit failed: ${e.message}`);
  // Try full amount minus gas
  if (e.message?.includes("insufficient")) {
    console.log("Trying with smaller deposit...");
    const smaller = balance - parseUnits("2", 6);
    console.log(`Attempting $${formatUnits(smaller, 6)} instead...`);
    const hash2 = await walletClient.writeContract({
      address: EXCHANGE,
      abi: [{ name: "deposit", type: "function", inputs: [{ name: "amount", type: "uint256" }], outputs: [], stateMutability: "nonpayable" }],
      functionName: "deposit",
      args: [smaller],
    });
    console.log(`✅ Deposit tx (retry): ${hash2}`);
    await new Promise(r => setTimeout(r, 12000));
  } else {
    process.exit(1);
  }
}
