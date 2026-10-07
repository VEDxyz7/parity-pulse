import assert from 'node:assert/strict'

// Against running localhost services. DEMO makes no external calls; explicit proposals persist only estimates.
const base = 'http://127.0.0.1:5173'
const correlationId = crypto.randomUUID()
const page = await fetch(base)
assert.equal(page.status, 200)
assert.match(await page.text(), /Parity Pulse/)
const statuses = []
for (const endpoint of ['/api/health', '/api/system-status']) {
  const response = await fetch(base + endpoint, { headers: { 'X-Correlation-ID': correlationId } })
  assert.equal(response.status, 200)
  assert.equal(response.headers.get('x-correlation-id'), correlationId)
  assert.match(response.headers.get('x-request-id'), /^[0-9a-f-]{36}$/)
  statuses.push(await response.json())
}
assert.equal(statuses[0].status, 'ok')
assert.equal(statuses[0].run_id, statuses[1].run_id)
assert.equal(statuses[1].execution_mode, 'DRY_RUN')
assert.equal(statuses[1].live_trading_enabled, false)
assert.equal(statuses[1].gates.RFQ_LIVE_GATE, 'BLOCKED')
assert.equal(statuses[1].gates.DRY_RUN_GATE, 'PASS')
console.log('PASS: frontend startup, Vite proxy, backend health/status and request correlation.')

assert.equal(statuses[1].require_simulation, true)
assert.equal(statuses[1].approval_mode, 'PROPOSE_ONLY')
assert.equal(statuses[1].gates.SWAP_LIVE_GATE, 'BLOCKED')
assert.equal(statuses[1].gates.AGENTIC_WALLET_LIVE_GATE, 'BLOCKED')
// An explicit proposal POST persists an estimate; it cannot trade.
const proposalResponse = await fetch(base + '/api/exposure/quote', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ text: 'I have $50 of Nvidia' }) })
assert.equal(proposalResponse.status, 200)
const proposal = await proposalResponse.json()
assert.equal(proposal.transaction_broadcast, false)
assert.equal(proposal.execution_ready, false)
assert.equal(proposal.simulation_status, 'UNAVAILABLE')
assert.equal(proposal.require_simulation, true)
if (statuses[1].data_mode === 'DEMO') {
  assert.equal(proposal.status, 'DRY_RUN')
  assert.equal(proposal.ticker, 'NVDA')
  assert.equal(proposal.data_mode, 'DEMO')
  assert.equal(proposal.selected.price_quality, 'DEMO')
}
const stored = await fetch(base + '/api/exposure/proposals/' + proposal.proposal_id)
assert.equal(stored.status, 200)
assert.equal((await stored.json()).transaction_broadcast, false)
console.log('PASS: Ask Flow, persisted proposal, separated DEMO and blocked execution.')

const trustResponse = await fetch(base + '/api/assets/NVDA/trust', { headers: { 'X-Correlation-ID': correlationId } })
assert.equal(trustResponse.status, 200)
const trust = await trustResponse.json()
assert.equal(trust.request_id, trustResponse.headers.get('x-request-id'))
assert.equal(trust.correlation_id, correlationId)
assert.equal(trust.trust_gate, 'BLOCKED')
assert.equal(trust.transaction_broadcast, false)
assert.equal(trust.execution_ready, false)
assert.equal(trust.llm_authoritative, false)
assert.equal(trust.require_simulation, true)
if (statuses[1].data_mode === 'DEMO') {
  assert.equal(trust.data_mode, 'DEMO')
  assert.equal(trust.ticker, 'NVDA')
  assert(trust.representations.every(row => row.classification === 'INSUFFICIENT_EVIDENCE'))
}
console.log('PASS: analytical Trust endpoint, request correlation, insufficient-data safety and no execution authority.')
