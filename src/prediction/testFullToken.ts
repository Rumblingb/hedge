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

  // Full token ID from the current signal
  const currentToken = "75416247641556001048495566007900612387007219053658779459724161515153083478993";
  console.log("\nTesting full token ID...");
  try {
    const r = await client.createAndPostOrder({ tokenID: currentToken, price: 0.76, size: 7, side: Side.BUY });
    console.log("Result:", JSON.stringify(r).slice(0, 300));
  } catch(e: any) {
    console.log("Error:", e.message);
    if (e.response) {
      try { const t = await e.response.text(); console.log("Body:", t.slice(0,300)); } catch {}
    }
  }
}

main().catch(e => console.error("FATAL:", e.message));
