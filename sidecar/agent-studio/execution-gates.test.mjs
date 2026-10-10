import { test } from 'node:test';
import assert from 'node:assert/strict';
import { LIVE_GATES, requireLiveCapabilities } from './execution-gates.mjs';
import { startSidecar } from './server.mjs';
import { grantSession } from './grant-session.mjs';

test('all independent sidecar capabilities are frozen and blocked', () => {
  assert.deepEqual(LIVE_GATES, { SWAP_LIVE_GATE: 'BLOCKED', RFQ_LIVE_GATE: 'BLOCKED', AGENTIC_WALLET_LIVE_GATE: 'BLOCKED' });
  assert.throws(() => { LIVE_GATES.SWAP_LIVE_GATE = 'PASS'; }, TypeError);
  assert.throws(requireLiveCapabilities, /AGENTIC_WALLET_LIVE_GATE_BLOCKED/);
});
test('no SDK import, session read, signing, paid transfer or listening socket with blocked gates', async () => {
  // Deliberately invalid credentials/location prove gate evaluation precedes reads/parsing.
  const keys = ['ALTANA_SESSION_FILE', 'ALTANA_OWNER_PRIVATE_KEY', 'X402_FACILITATOR_KEY', 'SIDECAR_TOKEN', 'LIVE_TRADING_ENABLED'];
  const saved = keys.map(key => process.env[key]);
  try {
    keys.forEach(key => { process.env[key] = 'not-a-real-credential-or-file'; });
    await assert.rejects(startSidecar(), /AGENTIC_WALLET_LIVE_GATE_BLOCKED/);
    await assert.rejects(grantSession(), /AGENTIC_WALLET_LIVE_GATE_BLOCKED/);
  } finally {
    keys.forEach((key, i) => { if (saved[i] === undefined) delete process.env[key]; else process.env[key] = saved[i]; });
  }
});
