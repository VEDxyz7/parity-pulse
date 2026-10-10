import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { App } from '../App'
import { parseSystemStatus, fetchFoundationStatus } from '../services/system'
import { healthFixture, systemFixture } from './fixtures'

function successfulFetch() {
  return vi.fn(async (url: string) => new Response(
    JSON.stringify(url === '/api/health' ? healthFixture : systemFixture),
    { status: 200, headers: { 'Content-Type': 'application/json' } },
  ))
}

function mount() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } })
  render(<QueryClientProvider client={client}><App /></QueryClientProvider>)
}

afterEach(() => {
  vi.unstubAllGlobals()
  vi.useRealTimers()
})

describe('foundation shell', () => {
  it('loads backend health and safe configuration, with deferred product navigation', async () => {
    const fetchMock = successfulFetch()
    vi.stubGlobal('fetch', fetchMock)
    mount()
    expect(await screen.findByText('Backend connected')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Markets move. Evidence matters.' })).toBeInTheDocument()
    expect(screen.getByText('Disabled · proposals only')).toBeInTheDocument()
    expect(screen.getByText('Illustrative data')).toBeInTheDocument()
    for (const name of ['Direct Exposure', 'Opportunity', 'Autopilot']) {
      expect(screen.getByRole('button', { name })).toBeDisabled()
    }
    expect(screen.getAllByText('blocked')).toHaveLength(3)
    expect(screen.getByText('Not yet tested')).toBeInTheDocument()
    expect(fetchMock).toHaveBeenCalledTimes(2)
  })

  it('shows unavailable/unknown instead of retaining stale healthy data, then recovers', async () => {
    const fetchMock = successfulFetch()
    vi.stubGlobal('fetch', fetchMock)
    mount()
    await screen.findByText('Backend connected')
    fetchMock.mockRejectedValue(new Error('network failed'))
    await userEvent.click(screen.getByRole('button', { name: 'Refresh status' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('couldn’t reach a healthy backend')
    expect(screen.queryByText('Backend connected')).not.toBeInTheDocument()
    expect(screen.queryByText('Illustrative data')).not.toBeInTheDocument()
    expect(screen.getAllByText('Unknown').length).toBeGreaterThan(0)
    fetchMock.mockImplementation(successfulFetch())
    await userEvent.click(screen.getByRole('button', { name: 'Refresh status' }))
    await screen.findByText('Backend connected')
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('does not make any state-changing API request', async () => {
    const fetchMock = successfulFetch()
    vi.stubGlobal('fetch', fetchMock)
    mount()
    await screen.findByText('Backend connected')
    await userEvent.click(screen.getByRole('button', { name: 'Refresh status' }))
    await waitFor(() => expect(fetchMock.mock.calls.length).toBeGreaterThanOrEqual(4))
    for (const [url, options] of fetchMock.mock.calls as unknown as [string, RequestInit][]) {
      expect(['/api/health', '/api/system-status']).toContain(url)
      expect(options.method).toBe('GET')
      expect(options.body).toBeUndefined()
    }
  })
})

describe('status boundary', () => {
  it('accepts Phase 2 and renders its data-layer status with all live gates blocked', async () => {
    const phaseTwo = { ...systemFixture, phase: 2 }
    expect(parseSystemStatus(phaseTwo).phase).toBe(2)
    vi.stubGlobal('fetch', vi.fn(async (url: string) => new Response(JSON.stringify(
      url === '/api/health' ? healthFixture : phaseTwo,
    ), { status: 200 })))
    mount()
    await screen.findByText('Backend connected')
    expect(screen.getByText('Illustrative data')).toBeInTheDocument()
    expect(screen.queryByText(/Phase 2/)).not.toBeInTheDocument()
    expect(screen.getAllByText('blocked')).toHaveLength(3)
  })

  it.each([
    { execution_mode: 'LIVE' }, { live_trading_enabled: true }, { require_simulation: false },
    { approval_mode: 'AUTONOMOUS' }, { gates: { ...systemFixture.gates, RFQ_LIVE_GATE: 'PASS' } },
    { demo_fixture: { ...systemFixture.demo_fixture, execution_allowed: true } },
    { data_mode: 'LIVE_READ_ONLY' }, { demo_fixture: null },
  ])('rejects an unsafe or unsupported status %j', override => {
    expect(() => parseSystemStatus({ ...systemFixture, ...override })).toThrow('could not be verified')
  })

  it('rejects degraded backend and inconsistent application runs', async () => {
    vi.stubGlobal('fetch', vi.fn(async (url: string) => new Response(JSON.stringify(
      url === '/api/health' ? { ...healthFixture, run_id: 'different-run' } : systemFixture,
    ), { status: 200 })))
    await expect(fetchFoundationStatus(new AbortController().signal)).rejects.toThrow('could not be verified')
  })

  it('rejects malformed non-JSON responses', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response('<html>unavailable</html>', { status: 200 })))
    await expect(fetchFoundationStatus(new AbortController().signal)).rejects.toThrow()
  })

  it('bounds a hung backend read and cancels both pending requests', async () => {
    vi.useFakeTimers()
    const fetchMock = vi.fn((_url: string, options: RequestInit) => new Promise<Response>((_resolve, reject) => {
      options.signal!.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')), { once: true })
    }))
    vi.stubGlobal('fetch', fetchMock)
    const pending = expect(fetchFoundationStatus(new AbortController().signal)).rejects.toThrow('Aborted')
    await vi.advanceTimersByTimeAsync(5_001)
    await pending
    expect(fetchMock).toHaveBeenCalledTimes(2)
    expect(fetchMock.mock.calls.every(([, options]) => options.signal!.aborted)).toBe(true)
  })
})
