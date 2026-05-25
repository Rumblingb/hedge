// swap-and-fund.ts - Convert USDC -> USDC.e -> pUSD and fund deposit wallet
import { createWalletClient, http, parseUnits, encodeFunctionData, maxUint256, createPublicClient } from 'viem';
import { privateKeyToAccount } from 'viem/accounts';
import { polygon } from 'viem/chains';

const PK = '0xdbab414025de26c1534b5d89bd2c836dd3ed26996f7a7ea6402dfbd423316f6a';
const RELAYER_HOST = 'https://relayer-v2.polymarket.com';
const RELAYER_KEY = '019e066d-ae62-7f13-a0d6-e8d6c415ce7c';
const EOA = '0x3ee8801f4Dbd1A3564383864435040E5b99dAC0D';
const DEPOSIT = '0x192b14904a07D458DDBF5b06D54Bd643B6EE068F';
const USDC = '0x3c499c542cEF5E3811e1192ce70d8cC03d5c3359';
const USDCE = '0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174';
const pUSD = '0xC011a7E12a19f7B1f670d46F03B03f3342E82DFB';
const ONRAMP = '0x93070a847efEf7F70739046A929D47a521F5B8ee';
const QUICKSWAP_ROUTER = '0xa5E0829CaCEd8fFDD4De3c43696c57F7D7A678ff';
const FACTORY = '0x00000000000Fb5C9ADea0298D729A0CB3823Cc07';

const account = privateKeyToAccount(PK);
const wc = createWalletClient({ account, chain: polygon, transport: http() });
const pubClient = createPublicClient({ chain: polygon, transport: http() });

const AMOUNT = parseUnits('138', 6);
const DEADLINE = Math.floor(Date.now() / 1000 + 1800).toString();

async function submitWallBatch(calls) {
  const resp = await fetch(RELAYER_HOST + '/nonce?address=' + EOA + '&type=WALLET',
    { headers: { 'RELAYER_API_KEY': RELAYER_KEY, 'RELAYER_API_KEY_ADDRESS': EOA } });
  const { nonce } = await resp.json();
  
  const deadline = Math.floor(Date.now() / 1000 + 600).toString();
  const signature = await wc.signTypedData({
    account,
    domain: { name: 'DepositWallet', version: '1', chainId: 137, verifyingContract: DEPOSIT },
    types: {
      Call: [{ name: 'target', type: 'address' }, { name: 'value', type: 'uint256' }, { name: 'data', type: 'bytes' }],
      Batch: [{ name: 'wallet', type: 'address' }, { name: 'nonce', type: 'uint256' }, { name: 'deadline', type: 'uint256' }, { name: 'calls', type: 'Call[]' }],
    },
    primaryType: 'Batch',
    message: { wallet: DEPOSIT, nonce: BigInt(nonce), deadline: BigInt(deadline), calls },
  });
  
  const body = {
    type: 'WALLET', from: EOA, to: FACTORY, nonce: String(nonce),
    signature,
    depositWalletParams: {
      depositWallet: DEPOSIT, deadline,
      calls: calls.map(c => ({ target: c.target, value: c.value, data: c.data })),
    },
  };
  
  const resp2 = await fetch(RELAYER_HOST + '/submit', {
    method: 'POST',
    headers: { 'RELAYER_API_KEY': RELAYER_KEY, 'RELAYER_API_KEY_ADDRESS': EOA, 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  return resp2.json();
}

// UNISWAP V3 exactInputSingle params encoding
// function exactInputSingle((tokenIn, tokenOut, fee, recipient, amountIn, amountOutMinimum, sqrtPriceLimitX96))
const exactInputSingleCall = (tokenIn, tokenOut, fee, recipient, amountIn, amountOutMin) => {
  return '0x414bf389' +
    '000000000000000000000000' + tokenIn.slice(2) +
    '000000000000000000000000' + tokenOut.slice(2) +
    '0000000000000000000000000000000000000000000000000000000000000' + fee.toString(16) +
    '000000000000000000000000' + recipient.slice(2) +
    '0000000000000000000000000000000000000000000000000000000000000000' + amountIn.slice(2).padStart(24, '0') +
    '0000000000000000000000000000000000000000000000000000000000000000' + amountOutMin.slice(2).padStart(24, '0') +
    '0000000000000000000000000000000000000000000000000000000000000000';
};

async function main() {
  console.log('=== EOA BALANCE ===');
  const eoaUsdc = await pubClient.readContract({
    address: USDC, abi: [{ name: 'balanceOf', type: 'function', inputs: [{ type: 'address' }], outputs: [{ type: 'uint256' }] }],
    functionName: 'balanceOf', args: [EOA],
  });
  console.log('EOA USDC:', Number(eoaUsdc)/1e6);

  // APPROACH: QuickSwap V2 swapExactTokensForTokens
  // First approve QuickSwap router to spend USDC
  console.log('\n=== Step 1: Approve QuickSwap router ===');
  const approveHash = await wc.writeContract({
    address: USDC, 
    abi: [{ name: 'approve', type: 'function', inputs: [{ type: 'address' }, { type: 'uint256' }], outputs: [{ type: 'bool' }] }],
    functionName: 'approve',
    args: [QUICKSWAP_ROUTER, AMOUNT],
  });
  console.log('Approve:', approveHash);
  await pubClient.waitForTransactionReceipt({ hash: approveHash });
  console.log('Approved ✅');
  
  // Step 2: Swap USDC -> USDC.e on QuickSwap V2
  console.log('\n=== Step 2: Swap USDC -> USDC.e ===');
  const swapHash = await wc.writeContract({
    address: QUICKSWAP_ROUTER,
    abi: [{ name: 'swapExactTokensForTokens', type: 'function', inputs: [
      { type: 'uint256' }, { type: 'uint256' }, { type: 'address[]' }, { type: 'address' }, { type: 'uint256' }
    ], outputs: [{ type: 'uint256[]' }] }],
    functionName: 'swapExactTokensForTokens',
    args: [AMOUNT, BigInt(0), [USDC, USDCE], EOA, BigInt(DEADLINE)],
  });
  console.log('Swap:', swapHash);
  await pubClient.waitForTransactionReceipt({ hash: swapHash });
  console.log('Swap confirmed ✅');
  
  // Check USDC.e balance
  const usdceBal = await pubClient.readContract({
    address: USDCE, abi: [{ name: 'balanceOf', type: 'function', inputs: [{ type: 'address' }], outputs: [{ type: 'uint256' }] }],
    functionName: 'balanceOf', args: [EOA],
  });
  console.log('EOA USDC.e:', Number(usdceBal)/1e6);
  
  // Step 3: Wrap USDC.e -> pUSD via onramp
  if (Number(usdceBal) > 0) {
    console.log('\n=== Step 3: Approve onramp + Wrap USDC.e -> pUSD ===');
    const approve2Hash = await wc.writeContract({
      address: USDCE,
      abi: [{ name: 'approve', type: 'function', inputs: [{ type: 'address' }, { type: 'uint256' }], outputs: [{ type: 'bool' }] }],
      functionName: 'approve',
      args: [ONRAMP, usdceBal],
    });
    console.log('Approve onramp:', approve2Hash);
    await pubClient.waitForTransactionReceipt({ hash: approve2Hash });
    
    const wrapHash = await wc.writeContract({
      address: ONRAMP,
      abi: [{ name: 'wrap', type: 'function', inputs: [{ type: 'address' }, { type: 'address' }, { type: 'uint256' }], outputs: [] }],
      functionName: 'wrap',
      args: [USDCE, pUSD, usdceBal],
    });
    console.log('Wrap tx:', wrapHash);
    await pubClient.waitForTransactionReceipt({ hash: wrapHash });
    console.log('Wrap confirmed ✅');
    
    // Check pUSD balance
    const pBal = await pubClient.readContract({
      address: pUSD, abi: [{ name: 'balanceOf', type: 'function', inputs: [{ type: 'address' }], outputs: [{ type: 'uint256' }] }],
      functionName: 'balanceOf', args: [EOA],
    });
    console.log('EOA pUSD:', Number(pBal)/1e6);
    
    // Step 4: Transfer pUSD to deposit wallet
    if (Number(pBal) > 0) {
      console.log('\n=== Step 4: Transfer pUSD to deposit wallet ===');
      const transferHash = await wc.writeContract({
        address: pUSD,
        abi: [{ name: 'transfer', type: 'function', inputs: [{ type: 'address' }, { type: 'uint256' }], outputs: [{ type: 'bool' }] }],
        functionName: 'transfer',
        args: [DEPOSIT, pBal],
      });
      console.log('Transfer:', transferHash);
      await pubClient.waitForTransactionReceipt({ hash: transferHash });
      console.log('Transfer confirmed ✅');
    }
    
    // Step 5: Sync CLOB + trade
    console.log('\n=== Step 5: Complete! Ready to sync CLOB ===');
    console.log('pUSD in deposit wallet. Next: approve + sync + trade');
  }
}
main().catch(e => console.error('FATAL:', e));
