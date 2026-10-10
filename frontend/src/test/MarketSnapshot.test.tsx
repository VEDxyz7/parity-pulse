import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it, vi } from 'vitest'
import { MarketSnapshot } from '../components/MarketSnapshot'
import { App } from '../App'
import fixture from './terminalFixtures.json'
import { healthFixture, systemFixture } from './fixtures'
const json = (value: unknown) => new Response(JSON.stringify(value), { status: 200 })
function mount(component = <MarketSnapshot mode="DEMO" />) {
  render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } })}>{component}</QueryClientProvider>)
}
afterEach(() => { vi.unstubAllGlobals(); window.history.replaceState(null, '', '/') })

it('renders exact backend economics, distinct timestamps, stale status and contextual synthetic disclosure', async () => {
  const data = structuredClone(fixture)
  data.issuers.items[0].observations[0].available_at = '2026-10-06T11:00:03Z'
  const mock = vi.fn(async () => json(data)); vi.stubGlobal('fetch', mock); mount()
  const table = await screen.findByRole('region', { name: 'Tokenized equity comparison' })
  expect(within(table).getByText('$200.1234567890123456789')).toBeInTheDocument()
  expect(within(table).getByText('1.000000000000000001 shares/token')).toBeInTheDocument()
  expect(within(table).getAllByText('stale').length).toBeGreaterThan(0)
  expect(table.textContent).toContain('Observed 2026-10-06T11:00:00Z')
  expect(table.textContent).toContain('Available 2026-10-06T11:00:03Z')
  expect(screen.getByText(/Synthetic inputs, not live market data/)).toBeInTheDocument()
  expect(screen.getByText(/News and event context are not exposed/)).toBeInTheDocument()
  expect(table).toHaveAttribute('tabindex', '0')
  const coverage = screen.getByText('Stored assessment IDs in this snapshot').closest('article')!
  expect(coverage.querySelector('strong')).toHaveTextContent(String(data.trust.items.filter(row => row.assessment_id !== null).length))
  expect(mock).toHaveBeenCalledWith('/api/terminal?limit=25&offset=0', expect.objectContaining({ method: 'GET' }))
  expect(screen.queryByRole('button', { name: /execute|broadcast|trade/i })).not.toBeInTheDocument()
})
it('does not replace an unavailable independent reference with a token or stale reference price', async () => {
  vi.stubGlobal('fetch', vi.fn(async () => json(fixture))); mount()
  const table = await screen.findByRole('table')
  const apple = within(table).getByText('AAPL').closest('tr')!
  expect(apple.children[3]).toHaveTextContent('Unavailable')
  expect(apple.children[4]).toHaveTextContent('Deviation unavailable')
  expect(apple.children[3]).not.toHaveTextContent('199.1234567890123456789')
  expect(apple.children[5]).toHaveTextContent('insufficient evidence')
})
it('shows bounded snapshot coverage rather than claiming global market coverage', async () => {
  const data = structuredClone(fixture); data.issuers.has_more = true
  vi.stubGlobal('fetch', vi.fn(async () => json(data))); mount()
  expect(await screen.findByText('In this snapshot · more records available in Markets')).toBeInTheDocument()
  expect(screen.getByRole('link', { name: 'Explore Markets' })).toHaveAttribute('href', '#terminal')
})
it('handles an empty provider snapshot without claiming real-time data or a market session', async () => {
  const data = structuredClone(fixture); data.data_mode = 'LIVE_READ_ONLY'
  for (const page of [data.issuers, data.trust, data.agents, data.executions, data.episodes]) page.items = []
  vi.stubGlobal('fetch', vi.fn(async () => json(data))); mount(<MarketSnapshot mode="LIVE_READ_ONLY" />)
  expect(await screen.findByRole('heading', { name: 'No cached representations' })).toBeInTheDocument()
  expect(screen.getByText(/Provider observations · read only/)).toBeInTheDocument()
  expect(screen.getByText(/Cached observations; inspect source timestamps/)).toBeInTheDocument()
  expect(screen.queryByText(/Synthetic inputs/)).not.toBeInTheDocument()
  expect(screen.getByText('Unavailable', { selector: '.metric-word' })).toBeInTheDocument()
})
it('shows a bounded loading state, with no placeholder financial values', () => {
  vi.stubGlobal('fetch', vi.fn(() => new Promise(() => {}))); mount()
  expect(screen.getByRole('status')).toHaveTextContent('Reading market evidence')
  expect(screen.queryByRole('table')).not.toBeInTheDocument()
})
it('clears prices while refreshing and after failure; does not expose raw upstream errors', async () => {
  const mock = vi.fn(async () => json(fixture)); vi.stubGlobal('fetch', mock); mount()
  await screen.findByText('$200.1234567890123456789')
  let reject!: (reason: Error) => void
  mock.mockImplementationOnce(() => new Promise<Response>((_, r) => { reject = r }))
  await userEvent.click(screen.getByRole('button', { name: 'Refresh observations' }))
  expect(screen.queryByRole('table')).not.toBeInTheDocument()
  await act(async () => reject(new Error('private provider details')))
  expect(await screen.findByRole('alert')).toHaveTextContent('No prior prices or substitute references')
  expect(screen.queryByText('private provider details')).not.toBeInTheDocument()
})
it('fails closed on a mode mismatch instead of rendering synthetic data as provider observations', async () => {
  vi.stubGlobal('fetch', vi.fn(async () => json(fixture))); mount(<MarketSnapshot mode="LIVE_READ_ONLY" />)
  await screen.findByRole('alert')
  expect(screen.queryByRole('table')).not.toBeInTheDocument()
})
it('opens the overview by default and only makes bounded read-only snapshot requests automatically', async () => {
  const mock = vi.fn(async (url: string) => json(url === '/api/health' ? healthFixture : url === '/api/system-status' ? { ...systemFixture, runtime_mode: 'DEMO', gates: { ...systemFixture.gates, DRY_RUN_GATE: 'PASS' } } : fixture))
  vi.stubGlobal('fetch', mock); mount(<App />)
  expect(await screen.findByRole('heading', { name: 'Markets move. Evidence matters.' })).toBeInTheDocument()
  await screen.findByRole('table')
  expect(screen.queryByRole('button', { name: 'Run scenario' })).not.toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Opportunity' })).toBeDisabled()
  for (const [url, options] of mock.mock.calls as unknown as [string, RequestInit][]) {
    expect(['/api/health', '/api/system-status', '/api/terminal?limit=25&offset=0']).toContain(url)
    expect(options.method).toBe('GET'); expect(options.body).toBeUndefined()
  }
})
it('exposes a keyboard-operable menu with expanded state and retains all existing routes', async () => {
  vi.stubGlobal('fetch', vi.fn(async (url: string) => json(url === '/api/health' ? healthFixture : systemFixture)))
  mount(<App />)
  const menu = screen.getByRole('button', { name: 'Menu' })
  expect(menu).toHaveAttribute('aria-expanded', 'false')
  await userEvent.click(menu)
  expect(menu).toHaveAttribute('aria-expanded', 'true')
  expect(menu).toHaveAttribute('aria-controls', 'primary-navigation workspace-tools')
  for (const href of ['#overview','#terminal','#trust','#opportunity','#portfolio','#demo-sandbox','#ask','#agent-api','#settings','#autopilot','#audit']) expect(document.querySelector(`a[href="${href}"]`)).not.toBeNull()
  await userEvent.click(screen.getByRole('link', { name: 'Research Lab' }))
  expect(await screen.findByRole('heading', { name: 'Research Lab' })).toBeInTheDocument()
  expect(menu).toHaveAttribute('aria-expanded', 'false')
})

it('keeps the redesigned desk available without a verified mode and never requests market data', () => {
  const mock = vi.fn(); vi.stubGlobal('fetch', mock)
  mount(<MarketSnapshot />)
  expect(screen.getByRole('heading', { name: /Recent Market Observations/ })).toBeInTheDocument()
  expect(screen.getByRole('heading', { name: /Deviation Trend/ })).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Refresh observations' })).toBeDisabled()
  expect(screen.queryByRole('table')).not.toBeInTheDocument()
  expect(mock).not.toHaveBeenCalled()
})

it('counts unique snapshot tickers and only backend-eligible observations without claiming verified aggregate prices', async () => {
  const data = structuredClone(fixture)
  const duplicate = structuredClone(data.issuers.items[0]); duplicate.contract = 'demo:second-representation'
  duplicate.eligibility = 'ANALYTICAL_ONLY'
  data.issuers.items.push(duplicate)
  vi.stubGlobal('fetch', vi.fn(async () => json(data))); mount()
  await screen.findByRole('table')
  const metric = (name: string) => screen.getByText(name).closest('article')!
  expect(metric('Tracked Assets').querySelector('strong')).toHaveTextContent(String(new Set(data.issuers.items.map(row => row.ticker)).size))
  expect(metric('Eligible Observations').querySelector('strong')).toHaveTextContent(String(data.issuers.items.filter(row => row.eligibility === 'ANALYTICAL_ONLY').length))
  expect(metric('Largest Verified Deviation')).toHaveTextContent('Unavailable')
  expect(metric('Eligible Observations')).toHaveTextContent('no execution authority')
})

it('does not reinterpret point-in-time or replay evidence as an aligned deviation trend', async () => {
  vi.stubGlobal('fetch', vi.fn(async () => json(fixture))); mount()
  await screen.findByRole('table')
  const trend = screen.getByRole('region', { name: /Deviation Trend/ })
  expect(trend).toHaveTextContent('does not supply an aligned token/equity historical series')
  expect(trend).toHaveTextContent('No series plotted · no asset pair selected')
  expect(within(trend).queryByRole('combobox')).not.toBeInTheDocument()
  expect(within(trend).queryByRole('img')).not.toBeInTheDocument()
  expect(within(trend).getByRole('link')).toHaveAttribute('href', '#trust')
  expect(screen.getByRole('link', { name: 'View all' })).toHaveAttribute('href', '#terminal')
})
