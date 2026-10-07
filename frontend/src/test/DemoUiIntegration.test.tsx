import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { App } from '../App'
import { demoStages } from '../components/DemoPipeline'
import type { ScenarioId } from '../services/demoSandbox'
import { healthFixture, systemFixture } from './fixtures'
import fixtures from './demoUiFixtures.json'

const json = (value: unknown) => new Response(JSON.stringify(value), { status: 200 })
const hero = fixtures.scenarios['supported-move']
function setup(runtime: 'DEMO' | 'LIVE' = 'DEMO') {
  let selected: ScenarioId = 'steady'
  const fetchMock = vi.fn(async (url: string, options?: RequestInit) => {
    if (url === '/api/health') return json(healthFixture)
    if (url === '/api/system-status') return json({ ...systemFixture, ...(runtime === 'DEMO' ? { runtime_mode: 'DEMO' } : {}), gates: { ...systemFixture.gates, DRY_RUN_GATE: 'PASS' } })
    if (url === '/api/demo/trust/scenarios') return json(fixtures.catalog)
    if (url.startsWith('/api/demo/trust/scenarios/')) {
      selected = url.split('/').at(-1) as ScenarioId
      return json(fixtures.scenarios[selected].trust)
    }
    const row = fixtures.scenarios[selected]
    if (url === '/api/demo/opportunity') {
      expect(options?.method).toBe('POST')
      expect(JSON.parse(options!.body as string)).toEqual({ trust_assessment_id: row.trust.assessment.assessment_id })
      return json(row.opportunity)
    }
    if (url === '/api/demo/risk') {
      expect(JSON.parse(options!.body as string)).toEqual({ opportunity_id: row.opportunity.opportunity.opportunity_id })
      return json(row.risk)
    }
    if (url === '/api/demo/quote') return json(hero.quote)
    if (url === '/api/demo/prepare') return json(hero.prepared)
    if (url === '/api/demo/simulate') return json(hero.simulation)
    if (url === '/api/demo/paper/fills') return json(hero.filled)
    if (url.endsWith('/monitor')) return json(hero.monitored)
    if (url.endsWith('/exit')) return json(hero.exited)
    if (url.endsWith('/scorecard')) return json(hero.scorecard)
    if (url === '/api/assets/NVDA/trust') return json({ ...fixtures.canonical_trust, evaluated_at: new Date().toISOString() })
    throw new Error('Unexpected API')
  })
  vi.stubGlobal('fetch', fetchMock)
  const query = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } })
  render(<QueryClientProvider client={query}><App /></QueryClientProvider>)
  return fetchMock
}
function progress(stage: string) {
  return Array.from(screen.getByRole('region', { name: 'Demo pipeline status' }).querySelectorAll('li')).find(row => row.dataset.stage === stage)!
}
async function openSandbox() {
  await screen.findByText('Backend connected')
  await userEvent.click(screen.getByRole('link', { name: 'Open DEMO SANDBOX' }))
  await screen.findByRole('option', { name: 'LIKELY INFORMATION' })
}
async function runScenario(label: string) {
  await userEvent.click(screen.getByRole('button', { name: label }))
  await userEvent.click(screen.getByRole('button', { name: 'Run demo scenario' }))
  await screen.findByRole('button', { name: 'Analyze Opportunity' })
  await userEvent.click(screen.getByRole('button', { name: 'Analyze Opportunity' }))
}
function assertDemoOnly(mock: ReturnType<typeof setup>) {
  for (const [url, options] of mock.mock.calls) {
    expect(['/api/health', '/api/system-status'].includes(url) || url.startsWith('/api/demo/')).toBe(true)
    expect(url).not.toMatch(/\/api\/assets\//)
    expect(url).not.toMatch(/wallet|rfq|swap|broadcast|execute/)
    if (options?.method === 'POST') expect(url.startsWith('/api/demo/')).toBe(true)
  }
}
beforeEach(() => window.history.replaceState(null, '', '#overview'))
afterEach(() => { vi.unstubAllGlobals(); window.history.replaceState(null, '', '/'); vi.useRealTimers() })

it('opens the dedicated labeled sandbox with every stage pending and no automatic assessment', async () => {
  const mock = setup()
  await openSandbox()
  expect(window.location.hash).toBe('#demo-sandbox')
  expect(screen.getByRole('heading', { name: 'DEMO SANDBOX', level: 1 })).toBeInTheDocument()
  expect(screen.getByRole('region', { name: 'Synthetic sandbox mode' })).toHaveTextContent('SIMULATED DATA — NOT LIVE MARKET DATA')
  expect(screen.getAllByText('NO REAL FUNDS WILL MOVE').length).toBeGreaterThan(0)
  for (const stage of demoStages) expect(progress(stage)).toHaveAttribute('data-status', 'pending')
  expect(mock.mock.calls.map(([url]) => url)).toEqual(expect.arrayContaining(['/api/health', '/api/system-status', '/api/demo/trust/scenarios']))
  expect(mock.mock.calls).toHaveLength(3)
  expect(screen.getByRole('button', { name: 'Opportunity' })).toBeDisabled()
  await userEvent.click(screen.getByRole('link', { name: 'Skip to main content' }))
  expect(window.location.hash).toBe('#demo-sandbox')
  expect(document.getElementById('main-content')).toHaveFocus()
  assertDemoOnly(mock)
})

it.each([['NORMAL', 'steady', 'NO_OPPORTUNITY'], ['LIKELY NOISE', 'thin-move', 'REJECTED_BY_TRUST']])('shows the %s stand-down path from backend evidence', async (label, id, status) => {
  const mock = setup(); await openSandbox(); await runScenario(label)
  await screen.findByRole('heading', { name: `Opportunity: ${status}` })
  expect(progress('TRUST')).toHaveAttribute('data-status', 'pass')
  expect(progress('OPPORTUNITY')).toHaveAttribute('data-status', 'rejected')
  expect(progress('OPPORTUNITY')).toHaveTextContent(fixtures.scenarios[id as ScenarioId].opportunity.opportunity.reason_codes[0])
  expect(progress('ROUTING')).toHaveAttribute('data-status', 'rejected')
  expect(screen.getByText(/Pipeline stopped at OPPORTUNITY/)).toBeInTheDocument()
  await userEvent.click(screen.getByRole('button', { name: 'Analyze Risk' }))
  await screen.findByRole('heading', { name: 'Risk: FAIL' })
  expect(progress('RISK')).toHaveAttribute('data-status', 'rejected')
  for (const stage of ['QUOTE', 'PREPARATION', 'SIMULATION', 'PAPER EXECUTION', 'POSITION', 'SCORECARD']) expect(progress(stage)).toHaveAttribute('data-status', 'pending')
  expect(screen.queryByRole('button', { name: 'Create Paper Fill' })).not.toBeInTheDocument()
  assertDemoOnly(mock)
})

it('runs LIKELY_INFORMATION through routing, quote, simulation, paper exit and server-calculated P&L/scorecard', async () => {
  const mock = setup(); await openSandbox(); await runScenario('LIKELY INFORMATION')
  await screen.findByRole('heading', { name: 'Opportunity: ACTIONABLE' })
  expect(progress('ROUTING')).toHaveAttribute('data-status', 'pass')
  for (const [button, heading] of [
    ['Analyze Risk', 'Risk: PASS'], ['Generate DEMO Quote', 'Quote: QUOTED'],
    ['Prepare DEMO Transaction', 'Transaction: PREPARED'], ['Run DEMO Simulation', 'Simulation: SIMULATION_PASS'],
    ['Create Paper Fill', 'Position: OPEN'], ['Monitor Synthetic Opening Observation', 'Monitor: explicit synthetic observation'],
    ['Exit Paper Position', 'Position: EXITED'], ['View Paper Scorecard', 'Scorecard: EXITED'],
  ]) {
    await userEvent.click(screen.getByRole('button', { name: button }))
    await screen.findByRole('heading', { name: heading })
  }
  for (const stage of demoStages) expect(progress(stage)).toHaveAttribute('data-status', 'pass')
  expect(progress('P&L')).toHaveTextContent(hero.exited.pnl!.net_pnl_usd)
  expect(screen.getByRole('region', { name: 'Demo Paper Position and Scorecard' })).toHaveTextContent(`Net PAPER P&L: ${hero.scorecard.pnl.net_pnl_usd} USD`)
  expect(screen.getByRole('button', { name: 'Opportunity' })).toBeDisabled()
  assertDemoOnly(mock)
})

it('reports running/failed requests and safely clears downstream status when retrying', async () => {
  const mock = setup(); await openSandbox()
  await userEvent.click(screen.getByRole('button', { name: 'Run demo scenario' }))
  await screen.findByRole('button', { name: 'Analyze Opportunity' })
  let reject!: (error: Error) => void
  mock.mockImplementationOnce(() => new Promise<Response>((_resolve, r) => { reject = r }))
  await userEvent.click(screen.getByRole('button', { name: 'Analyze Opportunity' }))
  expect(progress('OPPORTUNITY')).toHaveAttribute('data-status', 'running')
  await act(async () => reject(new Error('private upstream error')))
  expect(progress('OPPORTUNITY')).toHaveAttribute('data-status', 'failed')
  expect(screen.queryByText('private upstream error')).not.toBeInTheDocument()
  await userEvent.click(screen.getByRole('button', { name: 'Analyze Opportunity' }))
  await screen.findByRole('heading', { name: 'Opportunity: NO_OPPORTUNITY' })
  expect(progress('OPPORTUNITY')).toHaveAttribute('data-status', 'rejected')
  assertDemoOnly(mock)
})

it('resets all status and cancels a late scenario response on scenario selection', async () => {
  const mock = setup(); await openSandbox()
  let resolve!: (response: Response) => void
  mock.mockImplementationOnce(() => new Promise<Response>(r => { resolve = r }))
  await userEvent.click(screen.getByRole('button', { name: 'Run demo scenario' }))
  expect(progress('TRUST')).toHaveAttribute('data-status', 'running')
  const options = mock.mock.calls.at(-1)![1]!
  await userEvent.click(screen.getByRole('button', { name: 'LIKELY INFORMATION' }))
  expect(options.signal!.aborted).toBe(true)
  await act(async () => resolve(json(fixtures.scenarios.steady.trust)))
  for (const stage of demoStages) expect(progress(stage)).toHaveAttribute('data-status', 'pending')
  expect(screen.queryByRole('button', { name: 'Analyze Opportunity' })).not.toBeInTheDocument()
})

it('keeps canonical Overview Assess trust unchanged and makes sandbox availability explicit in the ordinary runtime', async () => {
  const mock = setup('LIVE')
  await screen.findByText('Backend connected')
  expect(mock.mock.calls).toHaveLength(2)
  await userEvent.click(screen.getByRole('button', { name: 'Assess trust' }))
  const panel = screen.getByRole('region', { name: 'Trust Layer' })
  expect(await within(panel).findByText('INSUFFICIENT_EVIDENCE')).toBeInTheDocument()
  expect(mock.mock.calls.at(-1)![0]).toBe('/api/assets/NVDA/trust')
  await userEvent.click(screen.getByRole('link', { name: 'Open DEMO SANDBOX' }))
  await screen.findByText('The connected backend has the sandbox disabled.')
  expect(mock.mock.calls).toHaveLength(3)
  expect(screen.queryByRole('button', { name: 'Run demo scenario' })).not.toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Opportunity' })).toBeDisabled()
  await userEvent.click(screen.getByRole('link', { name: 'Return to Overview' }))
  await screen.findByRole('button', { name: 'Assess trust' })
  expect(mock.mock.calls.some(([url]) => url.startsWith('/api/demo/'))).toBe(false)
})

it('supports a sandbox deep link and aborts analysis when returning to Overview', async () => {
  window.history.replaceState(null, '', '#demo-sandbox')
  const mock = setup()
  await screen.findByRole('option', { name: 'NORMAL' })
  mock.mockImplementationOnce(() => new Promise<Response>(() => {}))
  await userEvent.click(screen.getByRole('button', { name: 'Run demo scenario' }))
  const signal = mock.mock.calls.at(-1)![1]!.signal!
  await userEvent.click(screen.getByRole('link', { name: 'Return to Overview' }))
  await waitFor(() => expect(screen.getByRole('button', { name: 'Assess trust' })).toBeInTheDocument())
  expect(signal.aborted).toBe(true)
  expect(screen.queryByRole('region', { name: 'Demo pipeline status' })).not.toBeInTheDocument()
})
