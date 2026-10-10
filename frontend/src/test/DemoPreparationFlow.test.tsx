import { act, fireEvent, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it, vi } from 'vitest'
import { DemoPreparationFlow } from '../components/DemoPreparationFlow'
import { DemoTrustSandbox } from '../components/DemoTrustSandbox'
import { parseDemoResult, type ScenarioId } from '../services/demoSandbox'
import { parseOpportunity, parseRisk } from '../services/demoOpportunity'
import { parsePreparation, parseQuote, parseSimulation } from '../services/demoPreparation'
import f from './demoPreparationFixtures.json'
import scenarios from './demoOpportunityFixtures.json'

const trust = parseDemoResult(f.trust, 'supported-move')
const opportunity = parseOpportunity(f.opportunity, trust)
const risk = parseRisk(f.risk, opportunity)
const quote = parseQuote(f.quote, trust, opportunity, risk)
const prepared = parsePreparation(f.prepared, quote, opportunity)
const json = (v: unknown) => new Response(JSON.stringify(v), { status: 200 })
function setup(simulation: unknown = f.simulation) {
  const fetch = vi.fn(async (url: string, init: RequestInit) => {
    expect(init.method).toBe('POST')
    const body = JSON.parse(init.body as string)
    if (url === '/api/demo/quote') { expect(body).toEqual({ risk_id: risk.risk.risk_id }); return json(f.quote) }
    if (url === '/api/demo/prepare') { expect(body).toEqual({ quote_id: quote.quote!.quote_id }); return json(f.prepared) }
    if (url === '/api/demo/simulate') { expect(body).toEqual({ transaction_id: prepared.transaction!.transaction_id }); return json(simulation) }
    throw new Error('Unexpected endpoint')
  })
  vi.stubGlobal('fetch', fetch)
  render(<DemoPreparationFlow trust={trust} opportunity={opportunity} risk={risk} opportunityExpired={false} />)
  return fetch
}
afterEach(() => { vi.unstubAllGlobals(); vi.useRealTimers() })

it('performs the three manual stages with quoted costs, unsigned parameters and actual simulation checks', async () => {
  const fetch = setup()
  expect(fetch).not.toHaveBeenCalled()
  await userEvent.click(screen.getByRole('button', { name: 'Generate Illustrative Quote' }))
  expect(await screen.findByRole('heading', { name: 'Quote: QUOTED' })).toBeInTheDocument()
  expect(screen.getByText('51.10200')).toBeInTheDocument()
  expect(screen.getByText('0.978435286290164768')).toBeInTheDocument()
  expect(screen.getByText('1.607070173378732729')).toBeInTheDocument()
  expect(screen.getByText(/Risk after quoted economics: PASS/)).toBeInTheDocument()
  await userEvent.click(screen.getByRole('button', { name: 'Prepare Unsigned Request' }))
  expect(await screen.findByRole('heading', { name: 'Transaction: PREPARED' })).toBeInTheDocument()
  expect(screen.getByText(/Not signed · Not executed · Not broadcastable/)).toBeInTheDocument()
  await userEvent.click(screen.getByRole('button', { name: 'Run Local Simulation' }))
  expect(await screen.findByRole('heading', { name: 'Simulation: SIMULATION_PASS' })).toBeInTheDocument()
  expect(screen.getByText('Illustrative constraint evaluation — not a chain simulation')).toBeInTheDocument()
  expect(screen.getByText(/No money moved/)).toBeInTheDocument()
  expect(screen.getByText(/Illustrative data · synthetic quote and unsigned request/)).toBeInTheDocument()
  expect(fetch).toHaveBeenCalledTimes(3)
  expect(screen.queryByRole('button', { name: /broadcast|execute|submit order|wallet/i })).not.toBeInTheDocument()
})

it('shows actual SIMULATION_FAIL and failed expiry checks without substituting PASS', async () => {
  setup(f.expired_simulation)
  await userEvent.click(screen.getByRole('button', { name: 'Generate Illustrative Quote' }))
  await userEvent.click(await screen.findByRole('button', { name: 'Prepare Unsigned Request' }))
  await userEvent.click(await screen.findByRole('button', { name: 'Run Local Simulation' }))
  expect(await screen.findByRole('heading', { name: 'Simulation: SIMULATION_FAIL' })).toBeInTheDocument()
  expect(screen.getByText(/FAIL · QUOTE_VALID/)).toBeInTheDocument()
})

it.each(['signed', 'funds', 'gate', 'risk-id', 'representation', 'numeric', 'provider', 'missing-risk'])('rejects unsafe Quote contract: %s', mutation => {
  const q = structuredClone(f.quote)
  if (mutation === 'signed') q.quote!.signed = true
  if (mutation === 'funds') q.funds_moved = true
  if (mutation === 'gate') q.production_gates.OPPORTUNITY_GATE = 'PASS'
  if (mutation === 'risk-id') q.quote!.source_risk_id = crypto.randomUUID()
  if (mutation === 'representation') q.quote!.contract = 'demo:OTHER'
  if (mutation === 'numeric') q.quote!.execution_price_usd = 51.102 as unknown as string
  if (mutation === 'provider') q.quote!.provider_quote_id = 'real-id' as unknown as null
  if (mutation === 'missing-risk') q.risk_revalidation = null as unknown as typeof q.risk_revalidation
  expect(() => parseQuote(q, trust, opportunity, risk)).toThrow()
})

it.each(['quantity', 'signature', 'calldata', 'binding', 'contract', 'risk', 'cash'])('rejects mismatched prepared request: %s', mutation => {
  const p = structuredClone(f.prepared)
  if (mutation === 'quantity') p.transaction.parameters.quantity = '2'
  if (mutation === 'signature') p.transaction.signature = 'fake' as unknown as null
  if (mutation === 'calldata') p.transaction.calldata = '0x1234' as unknown as null
  if (mutation === 'binding') p.transaction.quote_id = crypto.randomUUID()
  if (mutation === 'contract') p.transaction.parameters.target_token = 'demo:OTHER'
  if (mutation === 'risk') p.risk_revalidation.approved_for_demo_analysis = false
  if (mutation === 'cash') p.transaction.parameters.total_cash_required_usd = '1'
  expect(() => parsePreparation(p, quote, opportunity)).toThrow()
})

it.each(['check', 'missing-check', 'binding', 'broadcast', 'method', 'chain', 'expiry'])('rejects fabricated simulation success: %s', mutation => {
  const s = structuredClone(f.simulation)
  if (mutation === 'check') s.simulation.checks[0].passed = false
  if (mutation === 'missing-check') s.simulation.checks.pop()
  if (mutation === 'binding') s.simulation.transaction_fingerprint = 'a'.repeat(64)
  if (mutation === 'broadcast') s.simulation.transaction_broadcast = true
  if (mutation === 'method') s.simulation.method = 'BINANCE_RPC'
  if (mutation === 'chain') s.simulation.chain_simulation = true
  if (mutation === 'expiry') s.simulation.evaluated_at = s.simulation.valid_until
  expect(() => parseSimulation(s, quote, prepared, opportunity)).toThrow()
})

it('expires the quote UI after 30 seconds without enabling stale preparation', async () => {
  setup()
  vi.useFakeTimers()
  await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Generate Illustrative Quote' })) })
  expect(screen.getByRole('button', { name: 'Prepare Unsigned Request' })).not.toBeDisabled()
  await act(async () => { await vi.advanceTimersByTimeAsync(30_001) })
  expect(screen.getByRole('button', { name: 'Prepare Unsigned Request' })).toBeDisabled()
  expect(screen.getByRole('status')).toHaveTextContent('expired')
})

it('reports unavailable stages without stale preparation/simulation success', async () => {
  const fetch = setup()
  await userEvent.click(screen.getByRole('button', { name: 'Generate Illustrative Quote' }))
  await screen.findByRole('button', { name: 'Prepare Unsigned Request' })
  fetch.mockRejectedValueOnce(new Error('raw secret error'))
  await userEvent.click(screen.getByRole('button', { name: 'Prepare Unsigned Request' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('No execution occurred')
  expect(screen.getByRole('alert')).not.toHaveTextContent('raw secret error')
  expect(screen.queryByRole('button', { name: 'Run Local Simulation' })).not.toBeInTheDocument()
})

it('aborts in-flight quoting on unmount and suppresses a late response', async () => {
  let finish: ((r: Response) => void) | undefined, signal: AbortSignal | undefined
  vi.stubGlobal('fetch', vi.fn((_url, init: RequestInit) => {
    signal = init.signal as AbortSignal
    return new Promise<Response>(resolve => { finish = resolve })
  }))
  const view = render(<DemoPreparationFlow trust={trust} opportunity={opportunity} risk={risk} opportunityExpired={false} />)
  await userEvent.click(screen.getByRole('button', { name: 'Generate Illustrative Quote' }))
  view.unmount()
  expect(signal!.aborted).toBe(true)
  await act(async () => { finish!(json(f.quote)) })
  expect(screen.queryByRole('heading', { name: 'Quote: QUOTED' })).not.toBeInTheDocument()
})

it.each(['steady', 'thin-move'] as ScenarioId[])('never exposes quoting or automatically calls downstream services for %s', async id => {
  const records = scenarios[id]
  const catalog = { dataset_type: 'DEMO_FIXTURE', synthetic: true, production_eligible: false, runtime_mode: 'DEMO',
    scenarios: Object.values(scenarios).map(row => ({ dataset_type: 'DEMO_FIXTURE', synthetic: true, production_eligible: false,
      scenario_id: row.trust.scenario_id, title: row.trust.title, description: row.trust.description })) }
  const fetch = vi.fn(async (url: string) => json(url.endsWith('/scenarios') ? catalog :
    url.includes('/scenarios/') ? records.trust : url === '/api/demo/opportunity' ? records.opportunity : records.risk))
  vi.stubGlobal('fetch', fetch)
  render(<DemoTrustSandbox />)
  await screen.findByRole('option', { name: 'LIKELY INFORMATION' })
  await userEvent.selectOptions(screen.getByRole('combobox'), id)
  await userEvent.click(screen.getByRole('button', { name: 'Run scenario' }))
  await userEvent.click(await screen.findByRole('button', { name: 'Analyze Opportunity' }))
  await userEvent.click(await screen.findByRole('button', { name: 'Analyze Risk' }))
  const panel = await screen.findByRole('region', { name: 'Scenario Opportunity and Risk' })
  expect(await within(panel).findByText(/Quote, transaction and simulation not run/)).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Generate Illustrative Quote' })).not.toBeInTheDocument()
  expect(fetch).toHaveBeenCalledTimes(4)
})
