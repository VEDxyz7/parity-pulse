import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ScorecardAudit } from '../components/ScorecardAudit'
import { Terminal } from '../components/Terminal'
import { fetchEvaluation, parseEvaluation } from '../services/scorecard'
import type { Scorecards, Trace } from '../services/scorecard'
import fixtures from './scorecardFixtures.json'
import terminalFixture from './terminalFixtures.json'

const clone = () => structuredClone(fixtures)
function mount(terminal = false) {
  render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } })}>{terminal ? <Terminal mode="DEMO" /> : <ScorecardAudit mode="DEMO" />}</QueryClientProvider>)
}
const response = (body: unknown) => new Response(JSON.stringify(body), { status: 200 })
function api() {
  const data = clone()
  const mock = vi.fn(async (url: string, _options?: RequestInit) => response(url.startsWith('/api/terminal') ? terminalFixture : url.startsWith('/api/audit/') ? data.trace : data.cards))
  vi.stubGlobal('fetch', mock)
  return { data, mock }
}
afterEach(() => { vi.unstubAllGlobals(); vi.useRealTimers() })

describe('Phase 13 backend-authoritative presentation', () => {
  it('renders simulation and safe abstention, never a fake real outcome', async () => {
    const { mock } = api(); mount()
    await screen.findAllByText(/No execution evidence/)
    expect(screen.getAllByText('REJECTED')).toHaveLength(2)
    expect(screen.getByText(/NO REAL FUNDS WILL MOVE/)).toBeInTheDocument()
    expect(screen.getAllByText(/CORRECT_ABSTENTION/).length).toBeGreaterThan(0)
    expect(screen.getAllByText(/No execution evidence/)).toHaveLength(2)
    expect(screen.getAllByText(/SYNTHETIC EVALUATION/)).toHaveLength(2)
    expect(screen.queryByText(/Actual completed trade: Yes/)).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /execute|sign|trade|broadcast/i })).not.toBeInTheDocument()
    expect(mock.mock.calls.every(([url]) => url.startsWith('/api/scorecard'))).toBe(true)
  })
  it('renders actual structured trace with unavailable stages, no hidden reasoning', async () => {
    const { data, mock } = api(); mount()
    await screen.findAllByText(/No execution evidence/)
    await userEvent.click(screen.getByRole('button', { name: `Trace decision ${data.trace.decision_id}` }))
    await screen.findByRole('heading', { name: 'Decision audit trace' })
    await screen.findByText(/Complete for recorded scope: Yes/)
    expect(screen.getAllByText('UNAVAILABLE_OR_NOT_APPLICABLE').length).toBeGreaterThan(0)
    expect(screen.getByText('SIMULATION')).toBeInTheDocument()
    expect(screen.getByText(/SIMULATION_PASS/)).toBeInTheDocument()
    expect(screen.getByText(/Source projections reference original journal records/)).toBeInTheDocument()
    expect(document.body.textContent).not.toContain('chain_of_thought')
    expect(mock.mock.calls.some(([url]) => url.startsWith('/api/audit/decisions/'))).toBe(true)
  })
  it('shows exact route estimates and unknown actual costs', async () => {
    api(); mount(); await screen.findAllByText(/No execution evidence/)
    expect(screen.getAllByText(/Actual total USD cost Unavailable/)).toHaveLength(2)
    expect(screen.getAllByText(/Classification correctness unavailable/)).toHaveLength(2)
    expect(screen.getAllByText(/Composite score unavailable/)).toHaveLength(2)
    expect(screen.getByText(/Direction samples 0/)).toBeInTheDocument()
  })
  it('filters by type/ticker/outcome using GET only', async () => {
    const { mock } = api(); mount(); await screen.findAllByText(/No execution evidence/)
    await userEvent.selectOptions(screen.getByLabelText('Evaluation type'), 'OPPORTUNITY')
    await userEvent.type(screen.getByLabelText('Scorecard ticker'), 'nvda')
    await userEvent.selectOptions(screen.getByLabelText('Outcome'), 'SIMULATED')
    await userEvent.click(screen.getByRole('button', { name: 'Filter evaluations' }))
    await waitFor(() => expect(mock).toHaveBeenLastCalledWith('/api/scorecard?scorecard_type=OPPORTUNITY&ticker=NVDA&outcome=SIMULATED&limit=25&offset=0', expect.objectContaining({ method: 'GET' })))
    expect(mock.mock.calls.every(([,options]) => !(options as RequestInit | undefined)?.body)).toBe(true)
  })
  it('paginates without recalculating financial values', async () => {
    const { data, mock } = api(); data.cards.page.has_more = true
    mount(); await screen.findAllByText(/No execution evidence/)
    await userEvent.click(screen.getByRole('button', { name: 'Next evaluations' }))
    await waitFor(() => expect(mock).toHaveBeenLastCalledWith('/api/scorecard?limit=25&offset=25', expect.anything()))
  })
  it('hides previous evaluations when refresh fails', async () => {
    const { mock } = api(); mount(); await screen.findAllByText(/No execution evidence/)
    mock.mockRejectedValue(new Error('offline'))
    await userEvent.click(screen.getByRole('button', { name: 'Refresh evaluations' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('No fallback or cached outcome')
    expect(screen.queryByText(/SYNTHETIC EVALUATION/)).not.toBeInTheDocument()
  })
  it('has an honest empty state', async () => {
    const { data } = api(); data.cards.page.items = []; mount()
    await screen.findByText('No completed decision records match this filter.')
    expect(screen.queryByRole('button', { name: /Trace decision/ })).not.toBeInTheDocument()
  })
  it('shows loading without synthetic placeholders', () => {
    vi.stubGlobal('fetch', vi.fn(() => new Promise(() => {}))); mount()
    expect(screen.getByRole('status')).toHaveTextContent('Loading scorecards')
    expect(screen.queryByText(/SYNTHETIC EVALUATION/)).not.toBeInTheDocument()
  })
  it('clears previous trace when a new trace fails', async () => {
    const { data, mock } = api(); mount(); await screen.findAllByText(/No execution evidence/)
    await userEvent.click(screen.getByRole('button', { name: `Trace decision ${data.trace.decision_id}` }))
    await screen.findByText(/Complete for recorded scope/)
    mock.mockRejectedValue(new Error('offline'))
    await userEvent.click(screen.getByRole('button', { name: `Trace decision ${data.trace.decision_id}` }))
    expect(await screen.findByRole('alert')).toHaveTextContent('No prior trace')
    expect(screen.queryByText(/Complete for recorded scope/)).not.toBeInTheDocument()
  })
  it('adds an explicit Terminal entry without modifying existing overview queries', async () => {
    const { mock } = api(); mount(true)
    await screen.findByRole('heading', { name: 'Execution analytics' })
    expect(mock).toHaveBeenCalledTimes(1)
    await userEvent.click(screen.getByRole('button', { name: 'Scorecard & audit' }))
    await screen.findAllByText(/No execution evidence/)
    expect(mock.mock.calls.every(([url]) => url.startsWith('/api/terminal') || url.startsWith('/api/scorecard'))).toBe(true)
  })
})

describe('Phase 13 response validation', () => {
  it.each(['float','mode','gate','broadcast','reasoning','signature','bad-date','false-label','score'])('rejects unsafe or unsupported response: %s', v => {
    const data: Record<string, any> = clone().cards
    if(v === 'float') data.page.items[0].route.selected_cost_per_share_usd = 1.1
    if(v === 'mode') data.data_mode = 'LIVE_READ_ONLY'
    if(v === 'gate') data.production_gates.TRUST_GATE = 'PASS'
    if(v === 'broadcast') data.broadcast = true
    if(v === 'reasoning') data.hidden_reasoning = 'internal'
    if(v === 'signature') data.page.items[0].route.typedDataToSign = {}
    if(v === 'bad-date') data.page.items[0].decision_at = 'yesterday'
    if(v === 'false-label') data.page.items[0].prediction.classification_correct = true
    if(v === 'score') data.page.items[0].score = '100'
    expect(() => parseEvaluation<Scorecards>(data, 'DEMO')).toThrow('could not be verified')
  })
  it('validates trace association, ordering inputs and mode isolation', () => {
    const data = clone().trace
    expect(parseEvaluation<Trace>(data, 'DEMO', true).complete_for_recorded_scope).toBe(true)
    data.events[0].decision_id = 'wrong-decision'
    expect(() => parseEvaluation<Trace>(data, 'DEMO', true)).toThrow('could not be verified')
  })
  it('supports an empty LIVE_READ_ONLY view without injecting DEMO', () => {
    const data = clone().cards; data.data_mode = 'LIVE_READ_ONLY'; data.page.items = []
    expect(parseEvaluation<Scorecards>(data, 'LIVE_READ_ONLY').page.items).toEqual([])
    data.page.items = clone().cards.page.items
    expect(() => parseEvaluation(data, 'LIVE_READ_ONLY')).toThrow()
  })
  it('bounds a hung read with an abort', async () => {
    vi.useFakeTimers()
    vi.stubGlobal('fetch', vi.fn((_url: string, o: RequestInit) => new Promise<Response>((_, reject) => o.signal!.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError'))))))
    const pending = expect(fetchEvaluation('DEMO', new URLSearchParams(), new AbortController().signal)).rejects.toThrow('Aborted')
    await vi.advanceTimersByTimeAsync(8001); await pending
  })
})
