import * as fs from "fs";
import { createWalletClient, http } from "viem";
import { polygon } from "viem/chains";
import { privateKeyToAccount } from "viem/accounts";

async function main() {
  const creds = JSON.parse(fs.readFileSync("/Users/brain/hedge/.rumbling-hedge/credentials/polymarket.json", "utf-8"));
  const pk = process.env.POLYMARKET_PRIVATE_KEY! as `0x${string}`;
  const account = privateKeyToAccount(pk);
  const w = createWalletClient({ account, chain: polygon, transport: http() });
  const { ClobClient, Side, AssetType, OrderType } = await import("@polymarket/clob-client-v2");
  const DW = "0x25D10ACCAF13021fbE7648Cbe202C2273408199C";

  // Use builder creds from the file
  const client = new ClobClient({
    host: "https://clob.polymarket.com",
    chain: 137,
    signer: w,
    creds: { key: creds.api_key, secret: creds.api_secret, passphrase: creds.api_passphrase },
    signatureType: 3,
    funderAddress: DW,
  });

  // Step 1: update balance/allowance
  try {
    await client.updateBalanceAllowance({ asset_type: AssetType.COLLATERAL });
    console.log("1. Balance allowance updated");
  } catch(e: any) { console.log("1. Allowance error:", e.message.slice(0,100)); }

  // Step 2: Get API keys (check what address they're for)
  try {
    const keys = await client.getApiKeys();
    console.log("2. API keys:", JSON.stringify(keys).slice(0,200));
  } catch(e: any) { console.log("2. Get keys error:", e.message.slice(0,100)); }

  // Step 3: Try order with extra params from docs
  const tokenID = "25714007960293389110960044475283546872601238755063051359394740854408462452120";
  try {
    const r = await client.createAndPostOrder(
      { tokenID, price: 0.50, size: 10, side: Side.BUY },
      { tickSize: "0.01", negRisk: false },
      OrderType.GTC,
    );
    console.log("3. Order:", JSON.stringify(r).slice(0, 400));
  } catch(e: any) { console.log("3. Order error:", e.message.slice(0,100)); }
}

main();
