import { createWalletClient, http } from "viem";
import { polygon } from "viem/chains";
import { privateKeyToAccount } from "viem/accounts";

async function main() {
  const pk = process.env.POLYMARKET_PRIVATE_KEY!;
  const account = privateKeyToAccount(pk as `0x${string}`);
  const walletClient = createWalletClient({ account, chain: polygon, transport: http() });
  const { ClobClient, Side } = await import("@polymarket/clob-client-v2");

  const client = new ClobClient({
    host: "https://clob.polymarket.com", chain: 137, signer: walletClient,
    signatureType: 3, funderAddress: "0x25D10ACCAF13021fbE7648Cbe202C2273408199C",
  });
  
  const creds = await client.deriveApiKey();
  console.log("API key OK");
  client.creds = creds;

  // Test with the known-good token from earlier
  const knownToken = "16847593058940518048889285945530347937431097253131100068695613442897188563427";
  console.log("\n1. Testing known token...");
  try {
    const r1 = await client.createAndPostOrder({ tokenID: knownToken, price: 0.75, size: 7, side: Side.BUY });
    console.log("  Result:", JSON.stringify(r1).slice(0, 200));
  } catch(e: any) {
    console.log("  Error:", e.message, e.stack?.split("\n").slice(0,3).join(" | "));
  }

  // Test with the CURRENT signal's token
  const currentToken = "75416247641556001048";
  console.log("\n2. Testing current signal token...");
  try {
    const r2 = await client.createAndPostOrder({ tokenID: currentToken, price: 0.76, size: 7, side: Side.BUY });
    console.log("  Result:", JSON.stringify(r2).slice(0, 200));
  } catch(e: any) {
    console.log("  Error:", e.message, e.stack?.split("\n").slice(0,3).join(" | "));
  }

  // Test with token from signal #21 earlier
  const token21 = "103494352077727633519794462225909715016674098090427134398149275081386135978024";
  console.log("\n3. Testing signal #21 token...");
  try {
    const r3 = await client.createAndPostOrder({ tokenID: token21, price: 0.515, size: 7, side: Side.BUY });
    console.log("  Result:", JSON.stringify(r3).slice(0, 200));
  } catch(e: any) {
    console.log("  Error:", e.message, e.stack?.split("\n").slice(0,3).join(" | "));
  }
}

main().catch(e => console.error("FATAL:", e.stack?.split("\n").slice(0,5).join(" | ")));
