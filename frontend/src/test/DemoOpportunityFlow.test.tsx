import { act, fireEvent, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it, vi } from 'vitest'
import { DemoTrustSandbox } from '../components/DemoTrustSandbox'
import { parseDemoResult, type ScenarioId } from '../services/demoSandbox'
import { parseOpportunity, parseRisk } from '../services/demoOpportunity'
import fixtures from './demoOpportunityFixtures.json'

const ids: ScenarioId[] = ['steady', 'thin-move', 'supported-move']
const marker = { dataset_type: 'DEMO_FIXTURE', synthetic: true, production_eligible: false }
const catalog = { ...marker, runtime_mode: 'DEMO', scenarios: ids.map(id => {
  const t = fixtures[id].trust
  return { ...marker, scenario_id: id, title: t.title, description: t.description }
}) }
const json = (value: unknown) => new Response(JSON.stringify(value), { status: 200 })
function mockScenario(id: ScenarioId) {
  const fixture = fixtures[id]
  const mock = vi.fn(async (url: string, options?: RequestInit) => {
    if (url === '/api/demo/trust/scenarios') return json(catalog)
    if (url === `/api/demo/trust/scenarios/${id}`) return json(fixture.trust)
    if (url === '/api/demo/opportunity') {
      expect(JSON.parse(options!.body as string)).toEqual({ trust_assessment_id: fixture.trust.assessment.assessment_id })
      expect(options!.method).toBe('POST')
      return json(fixture.opportunity)
    }
    if (url === '/api/demo/risk') {
      expect(JSON.parse(options!.body as string)).toEqual({ opportunity_id: fixture.opportunity.opportunity.opportunity_id })
      expect(options!.method).toBe('POST')
      return json(fixture.risk)
    }
    throw new Error('Unexpected endpoint')
  })
  vi.stubGlobal('fetch', mock)
  return mock
}
async function trustScenario(id: ScenarioId) {
  render(<DemoTrustSandbox />)
  await screen.findByRole('option', { name: 'LIKELY INFORMATION' })
  await userEvent.selectOptions(screen.getByRole('combobox'), id)
  await userEvent.click(screen.getByRole('button', { name: 'Run scenario' }))
  await screen.findByRole('button', { name: 'Analyze Opportunity' })
}
afterEach(() => { vi.unstubAllGlobals(); vi.useRealTimers() })

it.each([
  ['steady', 'NO_OPPORTUNITY', 'FAIL'], ['thin-move', 'REJECTED_BY_TRUST', 'FAIL'], ['supported-move', 'ACTIONABLE', 'PASS'],
])('demonstrates server-derived %s → %s → risk %s without execution', async (id, status, risk) => {
  const mock = mockScenario(id as ScenarioId)
  await trustScenario(id as ScenarioId)
  expect(mock).toHaveBeenCalledTimes(2)
  await userEvent.click(screen.getByRole('button', { name: 'Analyze Opportunity' }))
  expect(await screen.findByRole('heading', { name: `Opportunity: ${status}` })).toBeInTheDocument()
  expect(mock).toHaveBeenCalledTimes(3)
  await userEvent.click(screen.getByRole('button', { name: 'Analyze Risk' }))
  expect(await screen.findByRole('heading', { name: `Risk: ${risk}` })).toBeInTheDocument()
  expect(mock).toHaveBeenCalledTimes(4)
  const panel = screen.getByRole('region', { name: 'Scenario Opportunity and Risk' })
  expect(within(panel).getByText(/Illustrative data · synthetic inputs, not live market data/)).toBeInTheDocument()
  expect(within(panel).getByText(/Analytical approval only. Execution remains blocked/)).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: /execute|broadcast|submit order|buy/i })).not.toBeInTheDocument()
  expect(screen.getByText(/Production Trust and Opportunity remain blocked/)).toHaveTextContent('All live execution remains blocked')
  if (id === 'supported-move') {
    expect(within(panel).getByText('1.610784313725490196')).toBeInTheDocument()
    expect(within(panel).getByText('1.350000000000000000')).toBeInTheDocument()
    expect(within(panel).getByText(/HYPOTHETICAL/)).toBeDefined()
  }
})

it.each(['synthetic', 'production_eligible', 'broadcast', 'gate', 'trust-id', 'contract', 'classification', 'numeric', 'basis', 'fake-action', 'negative-edge', 'zero-adjustment'])('rejects invalid Opportunity contract: %s', mutation => {
  const f = structuredClone(fixtures['supported-move'])
  const v = f.opportunity
  if (mutation === 'synthetic') v.synthetic = false
  if (mutation === 'production_eligible') v.production_eligible = true
  if (mutation === 'broadcast') v.opportunity.transaction_broadcast = true
  if (mutation === 'gate') v.production_gates.OPPORTUNITY_GATE = 'PASS'
  if (mutation === 'trust-id') v.opportunity.trust_assessment_id = crypto.randomUUID()
  if (mutation === 'contract') v.opportunity.contract = '0x' + '1'.repeat(40)
  if (mutation === 'classification') v.opportunity.source_trust_classification = 'NORMAL'
  if (mutation === 'numeric') v.opportunity.economics.token_price_usd = 51 as unknown as string
  if (mutation === 'basis') v.opportunity.economics.calibrated_prediction = true
  if (mutation === 'fake-action') v.opportunity.action = 'NONE'
  if (mutation === 'negative-edge') v.opportunity.economics.net_hypothetical_edge_usd = '-1'
  if (mutation === 'zero-adjustment') v.opportunity.economics.hypothetical_adjustment_per_share_usd = '0'
  expect(() => parseOpportunity(v, parseDemoResult(f.trust, 'supported-move'))).toThrow()
})

it.each(['broadcast', 'gate', 'opportunity-id', 'check', 'approval', 'scope', 'size', 'numeric', 'missing-check', 'cap', 'zero-size', 'expired'])('rejects invalid Risk contract: %s', mutation => {
  const f = structuredClone(fixtures['supported-move'])
  const r = f.risk
  if (mutation === 'broadcast') r.risk.execution_ready = true
  if (mutation === 'gate') r.production_gates.TRUST_GATE = 'PASS'
  if (mutation === 'opportunity-id') r.risk.opportunity_id = crypto.randomUUID()
  if (mutation === 'check') r.risk.checks[0].passed = false
  if (mutation === 'approval') r.risk.approved_for_demo_analysis = false
  if (mutation === 'scope') r.risk.policy.policy_scope = 'PRODUCTION'
  if (mutation === 'size') r.risk.proposed_notional_usd = null as unknown as string
  if (mutation === 'numeric') r.risk.stress_loss_usd = 'NaN'
  if (mutation === 'missing-check') r.risk.checks.pop()
  if (mutation === 'cap') r.risk.maximum_allowed_notional_usd = '49'
  if (mutation === 'zero-size') r.risk.proposed_token_quantity = '0'
  if (mutation === 'expired') r.risk.evaluated_at = f.opportunity.opportunity.valid_until
  const o = parseOpportunity(f.opportunity, parseDemoResult(f.trust, 'supported-move'))
  expect(() => parseRisk(r, o)).toThrow()
})

it('does not substitute an Opportunity when the server request fails or returns invalid safety flags', async () => {
  const mock = mockScenario('supported-move')
  await trustScenario('supported-move')
  const bad = structuredClone(fixtures['supported-move'].opportunity)
  bad.opportunity.transaction_broadcast = true
  mock.mockResolvedValueOnce(json(bad))
  await userEvent.click(screen.getByRole('button', { name: 'Analyze Opportunity' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('No action was approved')
  expect(screen.queryByRole('button', { name: 'Analyze Risk' })).not.toBeInTheDocument()
  mock.mockRejectedValueOnce(new Error('raw secret failure'))
  await userEvent.click(screen.getByRole('button', { name: 'Analyze Opportunity' }))
  expect(await screen.findByRole('alert')).not.toHaveTextContent('raw secret failure')
})

it('reports unavailable Risk safely and keeps the calculated Opportunity separate', async () => {
  const mock = mockScenario('supported-move')
  await trustScenario('supported-move')
  await userEvent.click(screen.getByRole('button', { name: 'Analyze Opportunity' }))
  await screen.findByRole('button', { name: 'Analyze Risk' })
  mock.mockResolvedValueOnce(new Response('{}', { status: 410 }))
  await userEvent.click(screen.getByRole('button', { name: 'Analyze Risk' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('expired or invalid')
  expect(screen.queryByRole('heading', { name: 'Risk: PASS' })).not.toBeInTheDocument()
})

it.each(['opportunity', 'risk'] as const)('aborts a pending %s when scenario selection changes; no late result leaks', async stage => {
  const mock = mockScenario('supported-move')
  await trustScenario('supported-move')
  if (stage === 'risk') {
    await userEvent.click(screen.getByRole('button', { name: 'Analyze Opportunity' }))
    await screen.findByRole('button', { name: 'Analyze Risk' })
  }
  let finish: ((response: Response) => void) | undefined
  let signal: AbortSignal | undefined
  mock.mockImplementationOnce((_url, options) => {
    signal = options!.signal as AbortSignal
    return new Promise<Response>(resolve => { finish = resolve })
  })
  await userEvent.click(screen.getByRole('button', { name: stage === 'risk' ? 'Analyze Risk' : 'Analyze Opportunity' }))
  await userEvent.selectOptions(screen.getByRole('combobox'), 'steady')
  expect(signal!.aborted).toBe(true)
  await act(async () => { finish!(json(fixtures['supported-move'][stage])) })
  expect(screen.queryByRole('region', { name: 'Scenario Opportunity and Risk' })).not.toBeInTheDocument()
})

it('expires analytical authority without labeling a frozen synthetic clock as live', async () => {
  mockScenario('supported-move')
  await trustScenario('supported-move')
  vi.useFakeTimers()
  await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Analyze Opportunity' })) })
  expect(screen.getByRole('button', { name: 'Analyze Risk' })).toBeInTheDocument()
  await act(async () => { await vi.advanceTimersByTimeAsync(60_001) })
  expect(screen.getByRole('button', { name: 'Analyze Risk' })).toBeDisabled()
  expect(screen.getByRole('status')).toHaveTextContent('analytical proposal has expired')
})

it('times out an unavailable Opportunity analysis without a substituted decision', async () => {
  const mock = mockScenario('supported-move')
  await trustScenario('supported-move')
  mock.mockImplementationOnce((_url, options) => new Promise<Response>((_resolve, reject) => {
    options!.signal!.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')))
  }))
  vi.useFakeTimers()
  await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Analyze Opportunity' })) })
  await act(async () => { await vi.advanceTimersByTimeAsync(60_001) })
  expect(screen.getByRole('alert')).toHaveTextContent('No action was approved')
  expect(screen.queryByRole('heading', { name: 'Opportunity: ACTIONABLE' })).not.toBeInTheDocument()
})
