// Test multiple Tradovate API endpoints
const login = process.env.RH_LUCID_1_LOGIN || '';
const password = process.env.RH_LUCID_1_PASSWORD || '';

const endpoints = [
  { url: 'https://live.tradovateapi.com/v1/auth/accesstoken', label: 'live-tradoapi' },
  { url: 'https://demo.tradovateapi.com/v1/auth/accesstoken', label: 'demo-tradoapi' },
  { url: 'https://api.tradovate.com/v1/auth/accesstoken', label: 'api-tradovate' },
  { url: 'https://md.tradovateapi.com/v1/auth/accesstoken', label: 'md-tradoapi' },
];

async function tryEndpoint(url, label) {
  try {
    const res = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        name: login,
        password: password,
        appId: 'HermesQuant', 
        appVersion: '1.0.0',
      }),
    });
    const text = await res.text();
    return { label, status: res.status, body: text.slice(0, 200) };
  } catch (e) {
    return { label, error: e.message };
  }
}

async function main() {
  const results = await Promise.all(endpoints.map(e => tryEndpoint(e.url, e.label)));
  results.forEach(r => console.log(`${r.label}: ${r.status || 'ERR'} | ${r.body || r.error || ''}`));
}

main().catch(console.error);
