import { createWalletClient, http, parseUnits } from "viem";
import { polygon } from "viem/chains";
import { privateKeyToAccount } from "viem/accounts";

async function main() {
  const pk = process.env.POLYMARKET_PRIVATE_KEY! as `0x${string}`;
  const account = privateKeyToAccount(pk);
  const wallet = createWalletClient({ account, chain: polygon, transport: http() });
  
  const ROUTER = "0x1b02dA8Cb0d097eB8D57A175b88c7D8b47997506"; // SushiSwap
  const WMATIC = "0x0d500B1d8E8eF31E21C99d1Db9A6444d3ADf1270";
  const USDC = "0x3c499c542cEF5E3811e1192ce70d8cC03d5c3359";
  const DW = "0x25D10ACCAF13021fbE7648Cbe202C2273408199C";
  
  const amountIn = parseUnits("50", 18);
  const minOut = parseUnits("80", 6);
  
  // Approve WMATIC for router
  const appABI = [{"inputs":[{"name":"spender","type":"address"},{"name":"amount","type":"uint256"}],"name":"approve","outputs":[{"name":"","type":"bool"}],"stateMutability":"nonpayable","type":"function"}];
  const tx1 = await wallet.writeContract({ address: WMATIC, abi: appABI, functionName: "approve", args: [ROUTER, amountIn] });
  console.log("1. Approve:", tx1);
  
  // QuickSwap swapExactTokensForTokens
  const swapABI = [{"inputs":[{"name":"amountIn","type":"uint256"},{"name":"amountOutMin","type":"uint256"},{"name":"path","type":"address[]"},{"name":"to","type":"address"},{"name":"deadline","type":"uint256"}],"name":"swapExactTokensForTokens","outputs":[{"name":"","type":"uint256[]"}],"stateMutability":"nonpayable","type":"function"}];
  const deadline = BigInt(Math.floor(Date.now()/1000) + 600);
  const tx2 = await wallet.writeContract({ address: ROUTER, abi: swapABI, functionName: "swapExactTokensForTokens", args: [amountIn, minOut, [WMATIC, USDC], DW, deadline] });
  console.log("2. Swap:", tx2);
}

main();
