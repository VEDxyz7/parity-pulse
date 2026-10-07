import { fireEvent, render, screen, waitFor, act } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it, vi } from 'vitest'
import { AskFlow } from '../components/AskFlow'
import { parseProposal } from '../services/exposure'
import { parseSystemStatus } from '../services/system'
import { systemFixture } from './fixtures'

const selected = {
  issuer: 'synthetic-issuer', chain_id: 'DEMO', contract: 'demo:test', token_symbol: 'DEMO-NVDA',
  token_to_share_ratio: '2', token_price_usd: '250', effective_cost_per_share_usd: '125',
  estimated_token_quantity: '0.2', estimated_real_share_exposure: '0.4', estimated_token_cost_usd: '50',
  unallocated_budget_usd: '0', estimate_eligible: true, exclusion_reasons: [], market_state: 'regular',
  price_source: 'DEMO', price_timestamp: '2026-10-06T11:00:00Z', price_quality: 'DEMO', data_mode: 'DEMO',
}
const fixture = () => ({
  schema_version: 'ask-1', proposal_id: 'synthetic-proposal', status: 'DRY_RUN', data_mode: 'DEMO',
  ticker: 'NVDA', company_name: 'Nvidia', requested_budget_usd: '50', selected, representations: [selected],
  route_selection_reason: 'Indicative comparison; fees and execution unavailable.',
  broadcast_statement: 'No real transaction was broadcast.', valid_until: new Date(Date.now() + 30_000).toISOString(),
  execution_blockers: ['SIMULATION_UNAVAILABLE'], limitations: {}, independent_equity: { status: 'UNAVAILABLE', price_usd_per_share: null, source: null },
  execution_mode: 'DRY_RUN', approval_mode: 'PROPOSE_ONLY', require_simulation: true,
  live_trading_enabled: false, execution_ready: false, transaction_broadcast: false,
  simulation_status: 'UNAVAILABLE', provider_quote_id: null, fee_status: 'UNKNOWN', quote_status: 'INDICATIVE_ONLY',
})
afterEach(() => { vi.unstubAllGlobals(); vi.useRealTimers() })

it('posts only an explicit user request and displays backend financial strings', async () => {
  const mock = vi.fn(async () => new Response(JSON.stringify(fixture()), { status: 200 }))
  vi.stubGlobal('fetch', mock)
  render(<AskFlow mode="DEMO" />)
  expect(mock).not.toHaveBeenCalled()
  await userEvent.click(screen.getByRole('button', { name: 'Create dry-run proposal' }))
  expect(await screen.findByText('No real transaction was broadcast.')).toBeInTheDocument()
  expect(screen.getByText('0.2')).toBeInTheDocument()
  expect(screen.getByText('0.4')).toBeInTheDocument()
  expect(screen.getByText(/Fees, gas, funding conversion/)).toHaveTextContent('unknown')
  expect(screen.getByText(/Simulation: UNAVAILABLE/)).toHaveTextContent('Execution readiness: BLOCKED')
  expect(mock).toHaveBeenCalledTimes(1)
  const [path, options] = mock.mock.calls[0] as unknown as [string, RequestInit]
  expect(path).toBe('/api/exposure/quote')
  expect(options.method).toBe('POST')
  expect(JSON.parse(options.body as string)).toEqual({ text: 'I have $50 of Nvidia' })
  expect(screen.queryByRole('button', { name: /execute|buy now|confirm trade/i })).not.toBeInTheDocument()
})

it('renders unsupported stock safely and clears earlier results on retry', async () => {
  const mock = vi.fn(async () => new Response(JSON.stringify({ ...fixture(), status: 'NO_PROPOSAL', ticker: null,
    company_name: null, selected: null, representations: [], quote_status: 'UNAVAILABLE', route_selection_reason: 'NO_VERIFIED_MATCH' }), { status: 200 }))
  vi.stubGlobal('fetch', mock)
  render(<AskFlow mode="DEMO" />)
  await userEvent.click(screen.getByRole('button', { name: 'Create dry-run proposal' }))
  expect(await screen.findByText('NO_PROPOSAL')).toBeInTheDocument()
  expect(screen.getByText('NO_VERIFIED_MATCH')).toBeInTheDocument()
  mock.mockRejectedValue(new Error('unsafe raw provider secret'))
  await userEvent.click(screen.getByRole('button', { name: 'Create dry-run proposal' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('Proposal unavailable or invalid')
  expect(screen.queryByText('NO_PROPOSAL')).not.toBeInTheDocument()
  expect(screen.queryByText('unsafe raw provider secret')).not.toBeInTheDocument()
})

it.each([
  { transaction_broadcast: true }, { simulation_status: 'PASS' }, { execution_ready: true },
  { live_trading_enabled: true }, { require_simulation: false }, { execution_mode: 'LIVE' },
  { selected: { ...selected, estimated_token_quantity: 0.2 } }, { data_mode: 'LIVE' },
  { selected: { ...selected, data_mode: 'LIVE' } }, { provider_quote_id: 'invented' },
  { selected: null }, { valid_until: 'nonsense' },
])('rejects unsafe, malformed or cross-mode proposal %j', override => {
  expect(() => parseProposal({ ...fixture(), ...override }, 'DEMO')).toThrow('could not be verified')
})

it('accepts DRY_RUN PASS without granting any live gate', () => {
  const status = { ...systemFixture, gates: { ...systemFixture.gates, DRY_RUN_GATE: 'PASS' } }
  expect(parseSystemStatus(status).gates.DRY_RUN_GATE).toBe('PASS')
  expect(() => parseSystemStatus({ ...status, gates: { ...status.gates, SWAP_LIVE_GATE: 'PASS' } })).toThrow()
})

it('expires estimates and hides the previously selected quantity', async () => {
  vi.useFakeTimers()
  vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify(fixture()), { status: 200 })))
  render(<AskFlow mode="DEMO" />)
  await act(async () => { fireEvent.submit(screen.getByRole('button', { name: 'Create dry-run proposal' }).closest('form')!) })
  expect(screen.getByText('0.2')).toBeInTheDocument()
  await act(async () => { await vi.advanceTimersByTimeAsync(30_001) })
  expect(screen.getByText('EXPIRED — request a fresh estimate')).toBeInTheDocument()
  expect(screen.queryByText('0.2')).not.toBeInTheDocument()
})

it('bounds hung proposal requests and reports failure without a result', async () => {
  vi.useFakeTimers()
  const mock = vi.fn((_url: string, options: RequestInit) => new Promise<Response>((_resolve, reject) => {
    options.signal!.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')), { once: true })
  }))
  vi.stubGlobal('fetch', mock)
  render(<AskFlow mode="DEMO" />)
  fireEvent.submit(screen.getByRole('button', { name: 'Create dry-run proposal' }).closest('form')!)
  await act(async () => { await vi.advanceTimersByTimeAsync(60_001) })
  expect(screen.getByRole('alert')).toHaveTextContent('Proposal unavailable')
  expect(mock.mock.calls[0][1].signal!.aborted).toBe(true)
  expect(screen.queryByText('No real transaction was broadcast.')).not.toBeInTheDocument()
})

it('cancels work when an Ask workspace is unmounted', async () => {
  let signal: AbortSignal | undefined
  vi.stubGlobal('fetch', vi.fn((_url: string, options: RequestInit) => {
    signal = options.signal as AbortSignal
    return new Promise<Response>(() => {})
  }))
  const view = render(<AskFlow mode="DEMO" />)
  fireEvent.submit(screen.getByRole('button', { name: 'Create dry-run proposal' }).closest('form')!)
  await waitFor(() => expect(signal).toBeDefined())
  view.unmount()
  expect(signal!.aborted).toBe(true)
})
