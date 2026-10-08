import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { Terminal } from '../components/Terminal'
import { fetchTerminal, parseTerminal } from '../services/terminal'
import fixture from './terminalFixtures.json'

const clone = () => structuredClone(fixture)
function mount() {
  render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } })}><Terminal mode="DEMO" /></QueryClientProvider>)
}
function response(value = clone()) { return new Response(JSON.stringify(value), { status: 200 }) }
afterEach(() => { vi.unstubAllGlobals(); vi.useRealTimers() })

describe('backend-authoritative Terminal', () => {
  it('renders all analytical sections with exact backend values and no trade actions', async () => {
    const mock = vi.fn(async () => response())
    vi.stubGlobal('fetch', mock)
    mount()
    await screen.findByRole('heading', { name: 'Issuer spread board / normalized prices' })
    expect(screen.getByText('SIMULATED DATA — NOT LIVE MARKET DATA')).toBeInTheDocument()
    expect(screen.getAllByText('$102').length).toBeGreaterThan(0)
    expect(screen.getByText('2.00%')).toBeInTheDocument()
    for (const name of ['Trust monitor','Agent evidence','Execution analytics','Historical episodes','Portfolio / Autopilot context']) expect(screen.getByRole('heading', { name })).toBeInTheDocument()
    expect(screen.getAllByText('SYNTHETIC FIXTURE — NOT A REAL TRADE · Actual completed trade: No')).toHaveLength(2)
    expect(screen.getByText('No mode-scoped replay episodes match this filter.')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /execute|sign|trade|broadcast/i })).not.toBeInTheDocument()
    const [url, options] = mock.mock.calls[0] as unknown as [string, RequestInit]
    expect(url).toBe('/api/terminal?limit=25&offset=0')
    expect(options.method).toBe('GET'); expect(options.body).toBeUndefined()
  })

  it('shows loading without creating fake values', async () => {
    vi.stubGlobal('fetch', vi.fn(() => new Promise(() => {})))
    mount()
    expect(screen.getByRole('status')).toHaveTextContent('Loading Terminal evidence')
    expect(screen.queryByText('$102')).not.toBeInTheDocument()
  })

  it('renders missing/stale data and insufficient Trust explicitly', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => response()))
    mount()
    await screen.findByRole('heading', { name: 'Trust monitor' })
    expect(screen.getAllByText('INSUFFICIENT_EVIDENCE').length).toBeGreaterThan(0)
    expect(screen.getAllByText('STALE').length).toBeGreaterThan(0)
    expect(screen.getAllByText('Unavailable').length).toBeGreaterThan(0)
    expect(screen.getAllByText(/NO_PERSISTED_TRUST_ASSESSMENT/).length).toBeGreaterThan(0)
  })

  it('clears previously displayed values on refresh failure', async () => {
    const mock = vi.fn(async () => response())
    vi.stubGlobal('fetch', mock)
    mount()
    await screen.findByText('2.00%')
    mock.mockRejectedValue(new Error('network'))
    await userEvent.click(screen.getByRole('button', { name: 'Refresh Terminal' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('No fallback values')
    expect(screen.queryByText('2.00%')).not.toBeInTheDocument()
  })

  it('shows a valid empty state for every section', async () => {
    const empty = clone()
    for (const p of [empty.issuers, empty.trust, empty.agents, empty.executions, empty.episodes]) p.items = []
    vi.stubGlobal('fetch', vi.fn(async () => response(empty)))
    mount()
    await screen.findByText('No cached representations match this filter.')
    expect(screen.getByText('No persisted execution attempts.')).toBeInTheDocument()
    expect(screen.getByText(/No persisted agent runs/)).toBeInTheDocument()
  })

  it('filters and paginates by API request rather than financial recomputation', async () => {
    const next = clone(); next.issuers.has_more = true
    const mock = vi.fn(async () => response(next))
    vi.stubGlobal('fetch', mock)
    mount()
    await screen.findByText('2.00%')
    await userEvent.type(screen.getByLabelText('Underlying ticker'), 'nvda')
    await userEvent.click(screen.getByRole('button', { name: 'Apply filter' }))
    await waitFor(() => expect(mock).toHaveBeenLastCalledWith('/api/terminal?limit=25&offset=0&ticker=NVDA', expect.anything()))
    await userEvent.click(screen.getByRole('button', { name: 'Next records' }))
    await waitFor(() => expect(mock).toHaveBeenLastCalledWith('/api/terminal?limit=25&offset=25&ticker=NVDA', expect.anything()))
  })

  it('renders external strings as data, never HTML', async () => {
    const unsafe = clone(); unsafe.issuers.items[0].company = '<script>execute_trade()</script>'
    vi.stubGlobal('fetch', vi.fn(async () => response(unsafe)))
    mount()
    await screen.findByText('<script>execute_trade()</script>')
    expect(document.querySelector('script')).toBeNull()
  })

  it('displays structured agent conclusions with evidence and conflicts', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => response()))
    mount()
    const heading = await screen.findByRole('heading', { name: 'Agent evidence' })
    const panel = heading.closest('section')!
    expect(within(panel).getByText(/MARKET · OK · LOW/)).toBeInTheDocument()
    expect(within(panel).getByText('Evidence provenance and retrieved memory')).toBeInTheDocument()
    expect(panel.textContent).not.toContain('chain_of_thought')
  })
})

describe('Terminal response boundary', () => {
  it.each(['data_mode', 'gates', 'float', 'missing', 'secret', 'future-live'])('rejects invalid evidence: %s', variant => {
    const data = clone() as unknown as Record<string, any>
    if (variant === 'data_mode') data.data_mode = 'LIVE_READ_ONLY'
    if (variant === 'gates') data.production_gates.TRUST_GATE = 'PASS'
    if (variant === 'float') data.issuers.items[0].deviation_percent = 2.0
    if (variant === 'missing') delete data.issuers.items[0].token_to_share_ratio
    if (variant === 'secret') data.chain_of_thought = 'hidden'
    if (variant === 'future-live') data.broadcast = true
    expect(() => parseTerminal(data, 'DEMO')).toThrow('could not be verified')
  })

  it('supports the same read-only contract for production provider records', () => {
    const data = clone(); data.data_mode = 'LIVE_READ_ONLY'
    data.issuers.items = []; data.agents.items = []; data.executions.items = []
    expect(parseTerminal(data, 'LIVE_READ_ONLY').data_mode).toBe('LIVE_READ_ONLY')
  })

  it('bounds a hung backend fetch and aborts safely', async () => {
    vi.useFakeTimers()
    const mock = vi.fn((_url: string, options: RequestInit) => new Promise<Response>((_, reject) => options.signal!.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')))))
    vi.stubGlobal('fetch', mock)
    const pending = expect(fetchTerminal('DEMO', '', 0, new AbortController().signal)).rejects.toThrow('Aborted')
    await vi.advanceTimersByTimeAsync(8001)
    await pending
    expect(mock.mock.calls[0][1].signal!.aborted).toBe(true)
  })
})
