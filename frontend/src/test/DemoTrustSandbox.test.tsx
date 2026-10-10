import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it, vi } from 'vitest'
import { App } from '../App'
import { DemoTrustSandbox } from '../components/DemoTrustSandbox'
import { parseDemoCatalog, parseDemoResult } from '../services/demoSandbox'
import { parseSystemStatus } from '../services/system'
import { systemFixture, healthFixture } from './fixtures'

const marker = { dataset_type: 'DEMO_FIXTURE', synthetic: true, production_eligible: false }
const scenarios = [
  { ...marker, scenario_id: 'steady', title: 'NORMAL', description: 'Synthetic steady evidence' },
  { ...marker, scenario_id: 'thin-move', title: 'LIKELY NOISE', description: 'Synthetic thin evidence' },
  { ...marker, scenario_id: 'supported-move', title: 'LIKELY INFORMATION', description: 'Synthetic supported evidence' },
]
const catalog = { ...marker, runtime_mode: 'DEMO', scenarios }
function response(classification = 'NORMAL', index = 0) {
  return { ...scenarios[index], runtime_mode: 'DEMO', fixture_version: 'demo-trust-1', fixture_sha256: 'a'.repeat(64),
    fixture_episode_count: 30, fixture_preceding_sample_count: 15, news_inputs: [],
    production_gates: { DATA_GATE: 'PASS', DRY_RUN_GATE: 'PASS', TRUST_GATE: 'BLOCKED', OPPORTUNITY_GATE: 'BLOCKED_BY_TRUST',
      SWAP_LIVE_GATE: 'BLOCKED', RFQ_LIVE_GATE: 'BLOCKED', AGENTIC_WALLET_LIVE_GATE: 'BLOCKED' },
    assessment: { assessment_id: 'synthetic-assessment', ticker: 'NVDA', data_mode: 'DEMO', status: 'ASSESSED',
      evaluated_at: '2026-10-06T16:00:00Z', trust_gate: 'BLOCKED', regime: null, limitations: ['SYNTHETIC_TEST'],
      execution_mode: 'DRY_RUN', approval_mode: 'PROPOSE_ONLY', live_trading_enabled: false, require_simulation: true,
      execution_ready: false, transaction_broadcast: false, llm_authoritative: false,
      no_broadcast_statement: 'No real transaction was broadcast.',
      representations: [{ ticker: 'NVDA', issuer: 'synthetic-issuer', contract: 'demo:NVDA', symbol: 'DEMO-NVDA',
        token_price_usd: '51', token_to_share_ratio: '0.5', token_timestamp: '2026-10-06T16:00:00Z',
        classification, confidence: 'LOW', evidence_quality: 'SYNTHETIC_DEMO',
        reference: { status: 'AVAILABLE', reference_asof: '2026-10-06T16:00:00Z', timestamp_skew_seconds: '0',
          token_age_seconds: '0', reason_codes: [], observation: { source: 'DEMO_EQUITY', kind: 'QUOTE', data_quality: 'DEMO', price: '100' } },
        baseline: { status: 'SUFFICIENT', sample_count: 30, minimum_sample_count: 30 },
        analogues: { status: 'SUFFICIENT', retrieved_sample_count: 3, eligible_sample_count: 30 },
        liquidity: { status: 'AVAILABLE', volume_24h_usd: '3000', liquidity_usd: '5000' },
        news: { state: 'CORROBORATING', coverage: 'COMPLETE_REQUESTED_WINDOW', article_ids: ['synthetic-news'], provider_llm_sentiment_used: false },
        economic_comparison: { effective_price_per_share_usd: '102', comparable_token_value_usd: '50', deviation: '0.02' },
        features: { volume_24h_usd: '3000', liquidity_usd: '5000', persistence_seconds: '900', time_to_open_seconds: '77400',
          starting_deviation: '0.02', ending_deviation: '0.02', absolute_deviation: '0.02', news_state: 'CORROBORATING',
          asof: '2026-10-06T16:00:00Z', available_at: '2026-10-06T16:00:00Z' },
        missing_evidence: [], reason_codes: ['BACKEND_CLASSIFIER_OUTPUT'] }],
    },
  }
}
const json = (value: unknown) => new Response(JSON.stringify(value), { status: 200 })
afterEach(() => { vi.unstubAllGlobals(); vi.useRealTimers(); window.history.replaceState(null, '', '/') })

it.each([
  ['steady', 'NORMAL', 0], ['thin-move', 'LIKELY_NOISE', 1], ['supported-move', 'LIKELY_INFORMATION', 2],
])('selects %s and displays the server classification %s with evidence and provenance', async (id, classification, index) => {
  const mock = vi.fn(async (url: string) => json(url.endsWith('/scenarios') ? catalog : response(classification, index as number)))
  vi.stubGlobal('fetch', mock)
  render(<DemoTrustSandbox />)
  const select = await screen.findByRole('combobox', { name: 'Scenario' })
  await screen.findByRole('option', { name: 'LIKELY INFORMATION' })
  expect(mock).toHaveBeenCalledTimes(1)
  await userEvent.selectOptions(select, id as string)
  await userEvent.click(screen.getByRole('button', { name: 'Run scenario' }))
  expect(await screen.findByText(classification as string, { selector: 'strong' })).toBeInTheDocument()
  expect(screen.getByText('Illustrative data · synthetic scenarios, not live market data')).toBeInTheDocument()
  expect(screen.getByText(/Production eligible: false/)).toBeInTheDocument()
  expect(screen.getByText('900')).toBeInTheDocument()
  expect(screen.getByText(/Fixed synthetic clock/)).toHaveTextContent('2026-10-06T16:00:00Z')
  expect(screen.getByText(/Production Trust and Opportunity remain blocked/)).toHaveTextContent('All live execution remains blocked')
  expect(screen.getByText('No real transaction was broadcast.')).toBeInTheDocument()
  expect(mock.mock.calls[1][0]).toBe(`/api/demo/trust/scenarios/${id}`)
  expect(screen.queryByRole('button', { name: /execute|buy|broadcast/i })).not.toBeInTheDocument()
})

it('displays the backend classification even when it differs from the selected scenario label', async () => {
  vi.stubGlobal('fetch', vi.fn(async (url: string) => json(url.endsWith('/scenarios') ? catalog : response('LIKELY_INFORMATION'))))
  render(<DemoTrustSandbox />)
  await screen.findByRole('option', { name: 'NORMAL' })
  await userEvent.click(screen.getByRole('button', { name: 'Run scenario' }))
  expect(await screen.findByText('LIKELY_INFORMATION', { selector: 'strong' })).toBeInTheDocument()
  expect(screen.getByRole('combobox')).toHaveValue('steady')
})

it('clears old evidence on selection and failed replacement with no LIVE fallback', async () => {
  const mock = vi.fn(async (url: string) => json(url.endsWith('/scenarios') ? catalog : response()))
  vi.stubGlobal('fetch', mock)
  render(<DemoTrustSandbox />)
  await screen.findByRole('option', { name: 'NORMAL' })
  await userEvent.click(screen.getByRole('button', { name: 'Run scenario' }))
  await screen.findByText('NORMAL', { selector: 'strong' })
  await userEvent.selectOptions(screen.getByRole('combobox'), 'thin-move')
  expect(screen.queryByText('NORMAL', { selector: 'strong' })).not.toBeInTheDocument()
  mock.mockRejectedValue(new Error('raw secret error'))
  await userEvent.click(screen.getByRole('button', { name: 'Run scenario' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('No classification was substituted')
  expect(screen.queryByText('raw secret error')).not.toBeInTheDocument()
  expect(mock.mock.calls.every(([url]) => url.startsWith('/api/demo/trust/'))).toBe(true)
})

it('keeps frozen synthetic evidence visible without treating its clock as a current quote', async () => {
  vi.stubGlobal('fetch', vi.fn(async (url: string) => json(url.endsWith('/scenarios') ? catalog : response())))
  render(<DemoTrustSandbox />)
  await screen.findByRole('option', { name: 'NORMAL' })
  await userEvent.click(screen.getByRole('button', { name: 'Run scenario' }))
  await screen.findByText('NORMAL', { selector: 'strong' })
  vi.useFakeTimers()
  await act(async () => { await vi.advanceTimersByTimeAsync(120_001) })
  expect(screen.getByText('NORMAL', { selector: 'strong' })).toBeInTheDocument()
  expect(screen.getByText(/not historical replay/)).toBeInTheDocument()
})

it.each([
  { synthetic: false }, { production_eligible: true }, { dataset_type: 'LIVE' }, { runtime_mode: 'LIVE' },
  { scenario_id: 'thin-move' }, { fixture_sha256: 'invalid' }, { fixture_episode_count: -1 },
  { production_gates: { ...response().production_gates, TRUST_GATE: 'PASS' } },
  { assessment: { ...response().assessment, data_mode: 'LIVE' } },
])('rejects unsafe, mislabeled or mismatched sandbox response %j', override => {
  expect(() => parseDemoResult({ ...response(), ...override }, 'steady')).toThrow()
})

it('rejects unmarked or duplicate catalog entries and invalid numerical features', () => {
  expect(() => parseDemoCatalog({ ...catalog, synthetic: false })).toThrow()
  expect(() => parseDemoCatalog({ ...catalog, scenarios: [scenarios[0], scenarios[0], scenarios[2]] })).toThrow()
  expect(() => parseDemoCatalog({ ...catalog, scenarios: [{ ...scenarios[0], production_eligible: true }, ...scenarios.slice(1)] })).toThrow()
  const result = response()
  result.assessment.representations[0].features.persistence_seconds = 900 as unknown as string
  expect(() => parseDemoResult(result, 'steady')).toThrow()
})

it('aborts a pending scenario when selection changes and suppresses its late result', async () => {
  let finish: ((value: Response) => void) | undefined
  let signal: AbortSignal | undefined
  vi.stubGlobal('fetch', vi.fn((url: string, options: RequestInit) => {
    if (url.endsWith('/scenarios')) return Promise.resolve(json(catalog))
    signal = options.signal as AbortSignal
    return new Promise<Response>(resolve => { finish = resolve })
  }))
  render(<DemoTrustSandbox />)
  await screen.findByRole('option', { name: 'NORMAL' })
  await userEvent.click(screen.getByRole('button', { name: 'Run scenario' }))
  await userEvent.selectOptions(screen.getByRole('combobox'), 'thin-move')
  expect(signal!.aborted).toBe(true)
  await act(async () => { finish!(json(response())) })
  expect(screen.queryByText('NORMAL', { selector: 'strong' })).not.toBeInTheDocument()
})

it('bounds unavailable catalogue reads and reports the failure', async () => {
  vi.useFakeTimers()
  vi.stubGlobal('fetch', vi.fn((_url: string, options: RequestInit) => new Promise<Response>((_resolve, reject) => {
    options.signal!.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')))
  })))
  render(<DemoTrustSandbox />)
  await act(async () => { await vi.advanceTimersByTimeAsync(60_001) })
  expect(screen.getByRole('alert')).toHaveTextContent('No live data was substituted')
  expect(screen.getByRole('button', { name: 'Run scenario' })).toBeDisabled()
})

it('shows the explicit sandbox shell only for verified DEMO runtime and never requests LIVE Trust', async () => {
  window.history.replaceState(null, '', '#demo-sandbox')
  const mock = vi.fn(async (url: string) => json(url === '/api/health' ? healthFixture :
    url === '/api/system-status' ? { ...systemFixture, runtime_mode: 'DEMO', gates: { ...systemFixture.gates, DRY_RUN_GATE: 'PASS' } } : catalog))
  vi.stubGlobal('fetch', mock)
  const query = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } })
  render(<QueryClientProvider client={query}><App /></QueryClientProvider>)
  expect(await screen.findByRole('region', { name: 'Research Lab' })).toHaveTextContent('Research Lab')
  expect(await screen.findByRole('option', { name: 'NORMAL' })).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Assess trust' })).not.toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Opportunity' })).toBeDisabled()
  expect(mock.mock.calls.every(([url]) => ['/api/health', '/api/system-status', '/api/demo/trust/scenarios'].includes(url))).toBe(true)
  expect(() => parseSystemStatus({ ...systemFixture, runtime_mode: 'DEMO', data_mode: 'LIVE_READ_ONLY', demo_fixture: null })).toThrow()
  expect(() => parseSystemStatus({ ...systemFixture, runtime_mode: 'UNKNOWN' })).toThrow()
})
