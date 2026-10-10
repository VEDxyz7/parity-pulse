import { act, fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it, vi } from 'vitest'
import { DemoPaperFlow } from '../components/DemoPaperFlow'
import { DemoPreparationFlow } from '../components/DemoPreparationFlow'
import { parseDemoResult } from '../services/demoSandbox'
import { parseOpportunity, parseRisk } from '../services/demoOpportunity'
import { parsePreparation, parseQuote, parseSimulation } from '../services/demoPreparation'
import { parseLifecycle, parseScorecard } from '../services/demoPaper'
import f from './demoPaperFixtures.json'

const trust = parseDemoResult(f.trust, 'supported-move')
const origin = parseOpportunity(f.opportunity, trust)
const risk = parseRisk(f.risk, origin)
const quote = parseQuote(f.quote, trust, origin, risk)
const prepared = parsePreparation(f.prepared, quote, origin)
const simulation = parseSimulation(f.simulation, quote, prepared, origin)
const parse = (v: unknown) => parseLifecycle(v, quote, prepared, simulation, origin)
const json = (v: unknown, status = 200) => new Response(JSON.stringify(v), { status })
function setup(expired = false) {
  const onFilled = vi.fn()
  const fetch = vi.fn(async (url: string, init: RequestInit) => {
    const base = '/api/demo/paper/positions/' + f.filled.position.position_id
    if (url === '/api/demo/paper/fills') {
      expect(JSON.parse(init.body as string)).toEqual({ transaction_id: prepared.transaction!.transaction_id, simulation_id: simulation.simulation.simulation_id })
      return json(f.filled)
    }
    if (url === base + '/monitor') return json(f.monitored)
    if (url === base + '/exit') {
      expect(JSON.parse(init.body as string)).toEqual({ observation_id: f.monitored.observation!.observation_id }); return json(f.exited)
    }
    if (url === base + '/scorecard') { expect(init.method).toBe('GET'); return json(f.scorecard) }
    throw new Error('Unexpected paper API')
  })
  vi.stubGlobal('fetch', fetch)
  const view = render(<DemoPaperFlow quote={quote} prepared={prepared} simulation={simulation} origin={origin} expired={expired} onFilled={onFilled} />)
  return { fetch, onFilled, ...view }
}
afterEach(() => { vi.unstubAllGlobals(); vi.useRealTimers() })

it('completes manual fill, monitor, exit and actual ledger scorecard without real execution', async () => {
  const { fetch, onFilled } = setup()
  expect(fetch).not.toHaveBeenCalled()
  expect(screen.getByText('SIMULATED DATA — NOT LIVE TRADING')).toBeInTheDocument()
  await userEvent.click(screen.getByRole('button', { name: 'Create Paper Fill' }))
  expect(await screen.findByRole('heading', { name: 'Position: OPEN' })).toBeInTheDocument()
  expect(screen.getByText(/Entry synthetic time/)).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Exit Paper Position' })).not.toBeInTheDocument()
  await userEvent.click(screen.getByRole('button', { name: 'Monitor Synthetic Opening Observation' }))
  expect(await screen.findByText('52.894')).toBeInTheDocument()
  await userEvent.click(screen.getByRole('button', { name: 'Exit Paper Position' }))
  expect(await screen.findByRole('heading', { name: 'Position: EXITED' })).toBeInTheDocument()
  expect(screen.getByText('1.45335603303197526425600')).toBeInTheDocument()
  expect(screen.getByText('2.898018012027866929')).toBeInTheDocument()
  await userEvent.click(screen.getByRole('button', { name: 'View Paper Scorecard' }))
  expect(await screen.findByRole('heading', { name: 'Scorecard: EXITED' })).toBeInTheDocument()
  expect(screen.getByText(/Production Trust and Opportunity remain blocked/)).toBeInTheDocument()
  expect(fetch).toHaveBeenCalledTimes(4); expect(onFilled).toHaveBeenCalledTimes(3)
  expect(screen.queryByRole('button', { name: 'Exit Paper Position' })).not.toBeInTheDocument()
})

it('retries the same fill with the same server IDs instead of introducing an order payload', async () => {
  const { fetch } = setup()
  await userEvent.click(screen.getByRole('button', { name: 'Create Paper Fill' }))
  await screen.findByRole('heading', { name: 'Position: OPEN' })
  await userEvent.click(screen.getByRole('button', { name: 'Retrieve Paper Fill' }))
  expect(fetch).toHaveBeenCalledTimes(2)
  expect(fetch.mock.calls[0][1].body).toBe(fetch.mock.calls[1][1].body)
})

it('blocks creating a fill after expiry but allows managing an existing paper position', async () => {
  const { fetch, rerender } = setup(true)
  expect(screen.getByRole('button', { name: 'Create Paper Fill' })).toBeDisabled()
  expect(fetch).not.toHaveBeenCalled()
  rerender(<DemoPaperFlow quote={quote} prepared={prepared} simulation={simulation} origin={origin} expired={false} onFilled={() => {}} />)
  await userEvent.click(screen.getByRole('button', { name: 'Create Paper Fill' })); await screen.findByRole('heading', { name: 'Position: OPEN' })
  rerender(<DemoPaperFlow quote={quote} prepared={prepared} simulation={simulation} origin={origin} expired={true} onFilled={() => {}} />)
  expect(screen.getByRole('button', { name: 'Monitor Synthetic Opening Observation' })).toBeEnabled()
})

it('fails closed on API rejection and permits a safe retry', async () => {
  const { fetch } = setup()
  fetch.mockResolvedValueOnce(json({ error: 'rejected' }, 409))
  await userEvent.click(screen.getByRole('button', { name: 'Create Paper Fill' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('No real funds moved')
  expect(screen.queryByRole('heading', { name: 'Position: OPEN' })).not.toBeInTheDocument()
  await userEvent.click(screen.getByRole('button', { name: 'Create Paper Fill' }))
  expect(await screen.findByRole('heading', { name: 'Position: OPEN' })).toBeInTheDocument()
})

it('ignores an aborted response after unmount', async () => {
  const { fetch, unmount, onFilled } = setup()
  let resolve!: (response: Response) => void
  fetch.mockImplementationOnce(() => new Promise<Response>(r => { resolve = r }))
  fireEvent.click(screen.getByRole('button', { name: 'Create Paper Fill' }))
  const signal = fetch.mock.calls[0][1].signal!
  unmount(); expect(signal.aborted).toBe(true)
  await act(async () => { resolve(json(f.filled)) })
  expect(onFilled).not.toHaveBeenCalled()
})

it('only mounts paper flow after SIMULATION_PASS and locks upstream artifacts after a fill', async () => {
  vi.stubGlobal('fetch', vi.fn(async (url: string) => json(url.endsWith('/quote') ? f.quote : url.endsWith('/prepare') ? f.prepared : url.endsWith('/simulate') ? f.simulation : f.filled)))
  render(<DemoPreparationFlow trust={trust} opportunity={origin} risk={risk} opportunityExpired={false} />)
  expect(screen.queryByRole('button', { name: 'Create Paper Fill' })).not.toBeInTheDocument()
  await userEvent.click(screen.getByRole('button', { name: 'Generate Illustrative Quote' })); await screen.findByRole('heading', { name: 'Quote: QUOTED' })
  await userEvent.click(screen.getByRole('button', { name: 'Prepare Unsigned Request' })); await screen.findByRole('heading', { name: 'Transaction: PREPARED' })
  await userEvent.click(screen.getByRole('button', { name: 'Run Local Simulation' })); await screen.findByRole('heading', { name: 'Simulation: SIMULATION_PASS' })
  await userEvent.click(screen.getByRole('button', { name: 'Create Paper Fill' })); await screen.findByRole('heading', { name: 'Position: OPEN' })
  expect(screen.getByRole('button', { name: 'Generate Illustrative Quote' })).toBeDisabled()
  expect(screen.getByRole('button', { name: 'Run Local Simulation' })).toBeDisabled()
})

it.each([
  ['LIVE source', (v: typeof f.filled) => { v.source = 'LIVE' as 'DEMO' }],
  ['real funds', (v: typeof f.filled) => { v.fill.funds_moved = true as false }],
  ['wrong quantity', (v: typeof f.filled) => { v.fill.quantity = '2' }],
  ['wrong quote', (v: typeof f.filled) => { v.order.quote_id = crypto.randomUUID() }],
  ['wrong simulation', (v: typeof f.filled) => { v.order.simulation_id = crypto.randomUUID() }],
  ['production gate', (v: typeof f.filled) => { v.production_gates.TRUST_GATE = 'PASS' }],
  ['missing event', (v: typeof f.filled) => { v.events = [] }],
  ['wrong event reference', (v: typeof f.filled) => { v.events[0].reference_id = crypto.randomUUID() }],
  ['invalid state', (v: typeof f.filled) => { v.position.state = 'EXITED' }],
  ['failed risk', (v: typeof f.filled) => { v.risk.status = 'FAIL' }],
  ['failed local revalidation', (v: typeof f.filled) => { v.fill_revalidation.status = 'SIMULATION_FAIL' }],
])('rejects malformed or unsafe lifecycle: %s', (_name, mutate) => {
  const v = structuredClone(f.filled); mutate(v); expect(() => parse(v)).toThrow()
})

it('rejects malformed observation/exit/P&L and scorecards detached from actual records', () => {
  const row = parse(f.exited)
  expect(parseScorecard(f.scorecard, row, origin).pnl).toEqual(row.pnl)
  const badObservation = structuredClone(f.monitored); badObservation.observation!.clock_mode = 'LIVE' as 'EXPLICIT_SYNTHETIC_TIME_ADVANCE'
  expect(() => parse(badObservation)).toThrow()
  const badExit = structuredClone(f.exited); badExit.exit!.price_usd = '60'
  expect(() => parse(badExit)).toThrow()
  const badPnl = structuredClone(f.exited); badPnl.pnl!.net_pnl_usd = 'NaN'
  expect(() => parse(badPnl)).toThrow()
  const badScore = structuredClone(f.scorecard); badScore.pnl.net_pnl_usd = '999'
  expect(() => parseScorecard(badScore, row, origin)).toThrow()
  expect(() => parseScorecard(f.scorecard, parse(f.filled), origin)).toThrow()
})
