// CommonJS bounded paper-routing stub
const fs = require('fs');
const path = require('path');

const configPath = path.resolve(__dirname, '../.rumbling-hedge/research/track-policy.json');
let cfg;
try {
  cfg = JSON.parse(fs.readFileSync(configPath, 'utf8'));
} catch (e) {
  console.error('Failed to load track-policy.json:', e.message);
  process.exit(1);
}

function boundedPaperRoute({ stake, venues } = {}) {
  stake = stake || 100;
  venues = venues || ['polymarket','kalshi','manifold'];
  if (!cfg.gates || !cfg.gates.prediction || cfg.gates.prediction.allowed !== true) {
    return { ok: false, reason: 'gate_closed' };
  }
  if (!Array.isArray(venues) || venues.length < 2) {
    return { ok: false, reason: 'insufficient_venues' };
  }
  console.log('[bounded-paper] stake=' + stake + ' venues=' + venues.join(',') + ' per=' + (stake / venues.length));
  return { ok: true, staged: true };
}

var args = process.argv.slice(2);
if (args[0] === '--stake') {
  var out = boundedPaperRoute({ stake: Number(args[1]) });
  console.log(JSON.stringify(out, null, 2));
} else {
  console.log(JSON.stringify(boundedPaperRoute(), null, 2));
}
