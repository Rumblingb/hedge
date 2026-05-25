// fund-and-trade.ts - Complete deposit wallet funding + trading
import { createWalletClient, http, parseUnits, encodeFunctionData, maxUint256 } from 'viem';
import { privateKeyToAccount } from 'viem/accounts';
import { polygon } from 'viem/chains';
import { ClobClient, Side, OrderType, AssetType } from '@polymarket/clob-client-v2';

const PK = process.env.POLYMARKET_PRIVATE_KEY!;
const RELAYER_HOST = 'https://relayer-v2.polymarket.com';
const RELAYER_KEY = '019e066d-ae62-7f13-a0d6-e8d6c415ce7c';
const EOA = '0x3ee8801f4Dbd1A3564383864435040E5b99dAC0D';
const DEPOSIT = '0x192b14904a07D458DDBF5b06D54Bd643B6EE068F';
const USDC = '0x3c499c542cEF5E3811e1192ce70d8cC03d5c3359';
const pUSD = '0xC011a7E12a19f7B1f670d46F03B03f3342E82DFB';
const ONRAMP = '0x93070a847efEf7F70739046A929D47a521F5B8ee';
const FACTORY = '0x00000000000Fb5C9ADea0298D729A0CB3823Cc07';
const AMOUNT = parseUnits('138', 6); // Keep $2 in deposit wallet for buffer

const account = privateKeyToAccount(PK);
const wc = createWalletClient({ account, chain: polygon, transport: http() });

async function getNonce() {
  const resp = await fetch(`${RELAYER_HOST}/nonce?address=${EOA}&type=WALLET`,
    { headers: { 'RELAYER_API_KEY': RELAYER_KEY, 'RELAYER_API_KEY_ADDRESS': EOA } });
  const data = await resp.json() as any;
  return data.nonce;
}

async function main() {
  // Step 1: Get WALLET nonce
  const nonce = await getNonce();
  console.log('WALLET nonce:', nonce);
  
  // Step 2: Build WALLET batch calls
  const approveCall = {
    target: USDC,
    value: '0',
    data: encodeFunctionData({
      abi: [{ name: 'approve', type: 'function', inputs: [{ type: 'address' }, { type: 'uint256' }], outputs: [{ type: 'bool' }] }],
      functionName: 'approve',
      args: [ONRAMP, AMOUNT],
    }),
  };
  
  const wrapCall = {
    target: ONRAMP,
    value: '0',
    data: encodeFunctionData({
      abi: [{ name: 'wrap', type: 'function', inputs: [{ type: 'address' }, { type: 'address' }, { type: 'uint256' }], outputs: [] }],
      functionName: 'wrap',
      args: [USDC, pUSD, AMOUNT],
    }),
  };
  
  // Actually, let me just do approve first, then wrap
  // Hmm, the batch can include both calls atomically
  // Let me try it
  
  const deadline = Math.floor(Date.now() / 1000 + 600).toString(); // 10 min
  
  // EIP-712 typed data
  const types = {
    Call: [
      { name: 'target', type: 'address' },
      { name: 'value', type: 'uint256' },
      { name: 'data', type: 'bytes' },
    ],
    Batch: [
      { name: 'wallet', type: 'address' },
      { name: 'nonce', type: 'uint256' },
      { name: 'deadline', type: 'uint256' },
      { name: 'calls', type: 'Call[]' },
    ],
  };
  
  const domain = {
    name: 'DepositWallet',
    version: '1',
    chainId: 137,
    verifyingContract: DEPOSIT as `0x${string}`,
  };
  
  const message = {
    wallet: DEPOSIT as `0x${string}`,
    nonce: BigInt(nonce),
    deadline: BigInt(deadline),
    calls: [approveCall, wrapCall],
  };
  
  const signature = await wc.signTypedData({
    account: account,
    domain,
    types,
    primaryType: 'Batch',
    message,
  });
  
  console.log('Signature:', signature);
  
  // Submit to relayer
  const submitBody = {
    type: 'WALLET',
    from: EOA,
    to: FACTORY,
    nonce: nonce,
    signature: signature,
    depositWalletParams: {
      depositWallet: DEPOSIT,
      deadline: deadline,
      calls: [approveCall, wrapCall].map(c => ({
        target: c.target,
        value: c.value,
        data: c.data,
      })),
    },
  };
  
  console.log('\nSubmitting WALLET batch...');
  const resp = await fetch(`${RELAYER_HOST}/submit`, {
    method: 'POST',
    headers: {
      'RELAYER_API_KEY': RELAYER_KEY,
      'RELAYER_API_KEY_ADDRESS': EOA,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(submitBody),
  });
  
  const result = await resp.json() as any;
  console.log('Submit result:', JSON.stringify(result, null, 2));
  
  if (result.transactionID) {
    console.log('\nWaiting for confirmation...');
    // Poll for confirmation
    for (let i = 0; i < 30; i++) {
      await new Promise(r => setTimeout(r, 3000));
      const txResp = await fetch(`${RELAYER_HOST}/transactions?id=${result.transactionID}`,
        { headers: { 'RELAYER_API_KEY': RELAYER_KEY, 'RELAYER_API_KEY_ADDRESS': EOA } });
      const txData = await txResp.json() as any[];
      if (txData?.[0]) {
        const state = txData[0].state;
        console.log(`Poll ${i+1}: ${state}`);
        if (state === 'STATE_CONFIRMED' || state === 'STATE_MINED') {
          console.log('✅ WALLET batch confirmed!');
          break;
        }
        if (state === 'STATE_FAILED') {
          console.log('❌ WALLET batch failed:', JSON.stringify(txData[0], null, 2));
          break;
        }
      }
    }
  }
}
main().catch(e => console.error('FATAL:', e));
