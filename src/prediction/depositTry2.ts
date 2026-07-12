import { createWalletClient, http, parseUnits } from "viem";
import { polygon } from "viem/chains";
import { privateKeyToAccount } from "viem/accounts";

const pk = process.env.POLYMARKET_PRIVATE_KEY;
if (!pk || pk.length < 64 || pk.startsWith("0x25D10")) {
  console.error("Need POLYMARKET_PRIVATE_KEY");
  process.exit(1);
}

const account = privateKeyToAccount(pk as `0x${string}`);
const client = createWalletClient({ account, chain: polygon, transport: http("https://polygon.drpc.org") });
const EXCHANGE = "0x4bFb41d5B3570DeFd03C39a9A4D8dE6Bd8B8982E";

async function main() {
  // Try single-arg deposit(uint256)
  try {
    console.log("Trying deposit(uint256) with 100 USDC...");
    const hash = await client.writeContract({
      address: EXCHANGE,
      abi: [{ name: "deposit", type: "function", inputs: [{ name: "amount", type: "uint256" }], outputs: [], stateMutability: "nonpayable" }],
      functionName: "deposit",
      args: [parseUnits("100", 6)],
    });
    console.log("✅ Deposit:", `https://polygonscan.com/tx/${hash}`);
    return;
  } catch(e: any) {
    console.log("Single-arg failed:", e.shortMessage?.slice(0, 100) || e.message?.slice(0, 100));
  }

  // Try swapDeposit
  try {
    console.log("Trying swapDeposit...");
    const hash = await client.writeContract({
      address: EXCHANGE,
      abi: [{ name: "swapDeposit", type: "function", inputs: [{ name: "amount", type: "uint256" }], outputs: [], stateMutability: "nonpayable" }],
      functionName: "swapDeposit",
      args: [parseUnits("100", 6)],
    });
    console.log("✅ swapDeposit:", `https://polygonscan.com/tx/${hash}`);
    return;
  } catch(e: any) {
    console.log("swapDeposit failed:", e.shortMessage?.slice(0, 100));
  }

  // Try mint
  try {
    console.log("Trying mint...");
    const hash = await client.writeContract({
      address: EXCHANGE,
      abi: [{ name: "mint", type: "function", inputs: [{ name: "amount", type: "uint256" }], outputs: [], stateMutability: "nonpayable" }],
      functionName: "mint",
      args: [parseUnits("100", 6)],
    });
    console.log("✅ mint:", `https://polygonscan.com/tx/${hash}`);
    return;
  } catch(e: any) {
    console.log("mint failed:", e.shortMessage?.slice(0, 100));
  }

  // Check if there's a different contract address for deposits
  const proxyAddr = "0x2796B89c32440C790b561Ae1e2Bf18Ff25348f78"; // Polymarket ERC-1155 Proxy
  try {
    console.log("Trying deposit on ERC-1155 proxy...");
    const hash = await client.writeContract({
      address: proxyAddr,
      abi: [{ name: "deposit", type: "function", inputs: [{ name: "token", type: "address" }, { name: "amount", type: "uint256" }], outputs: [], stateMutability: "nonpayable" }],
      functionName: "deposit",
      args: ["0x3c499c542cEF5E3811e1192ce70d8cC03d5c3359", parseUnits("100", 6)],
    });
    console.log("✅ Deposit on ERC-1155:", `https://polygonscan.com/tx/${hash}`);
    return;
  } catch(e: any) {
    console.log("ERC-1155 deposit failed:", e.shortMessage?.slice(0, 100));
  }

  console.log("All deposit methods failed. The user should use the Polymarket UI.");
}

main().catch(e => console.error(e));
