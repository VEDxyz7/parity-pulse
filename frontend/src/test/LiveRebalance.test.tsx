import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import { App } from '../App'
import { LiveRebalance } from '../components/LiveRebalance'
import { healthFixture, systemFixture } from './fixtures'

const calls: [string, RequestInit][] = []
function mock(response: unknown = [], status = 200) {
  calls.length = 0
  vi.stubGlobal('fetch', vi.fn(async (path: string, options: RequestInit) => {
    calls.push([path, options])
    return new Response(JSON.stringify(path === '/api/health' ? healthFixture : path === '/api/system-status' ? systemFixture : response), { status: path.startsWith('/api/live') ? status : 200 })
  }))
}
afterEach(() => { vi.unstubAllGlobals(); window.location.hash = '' })
function readonly() {
  expect(calls.length).toBeGreaterThan(0)
  for (const [path, options] of calls) {
    expect(['/api/health', '/api/system-status', '/api/live/fills']).toContain(path)
    expect(options.method).toBe('GET')
    expect(options.body).toBeUndefined()
    expect(new Headers(options.headers).has('x-execution-worker-token')).toBe(false)
  }
}
it('keeps the newer dashboard navigation and exposes only read-only execution status', async () => {
  window.location.hash = '#live'
  mock()
  render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><App /></QueryClientProvider>)
  expect(await screen.findByRole('heading', { name: 'Execution status' })).toBeInTheDocument()
  await screen.findByText('No recorded live legs.')
  expect(screen.getByRole('navigation', { name: 'Main navigation' })).toHaveClass('primary-navigation')
  expect(screen.getByRole('button', { name: 'Live rebalance unavailable' })).toBeDisabled()
  expect(screen.getByRole('button', { name: 'Opportunity' })).toBeDisabled()
  expect(screen.getByRole('button', { name: 'Autopilot' })).toBeDisabled()
  readonly()
})
it('handles an unconfigured worker without proposing execution or substituting data', async () => {
  mock({}, 404)
  render(<LiveRebalance gates={systemFixture.gates} />)
  expect(await screen.findByRole('status')).toHaveTextContent('Execution worker diagnostics are not configured')
  readonly()
})
it.each([{}, [{ action_id: 'invalid' }]])('rejects malformed journal payloads', async value => {
  mock(value)
  render(<LiveRebalance gates={systemFixture.gates} />)
  await screen.findByText('Journal unavailable or invalid. No fallback evidence was substituted.')
  readonly()
})
it('shows only allowlisted journal fields and safe transaction links', async () => {
  mock([{ action_id: 'action', plan_id: 'plan', asset: 'NVDA', side: 'BUY', status: 'SUBMISSION_UNKNOWN', notional_usd: '10', approve_tx: null, swap_tx: '0x' + 'a'.repeat(64), reasons: ['RECONCILE_FIRST'], created_at: '2026-10-11T00:00:00Z', updated_at: '2026-10-11T00:00:01Z', signature: 'synthetic-private-sentinel' }])
  render(<LiveRebalance gates={systemFixture.gates} />)
  await screen.findByText('SUBMISSION_UNKNOWN')
  expect(screen.getByRole('link', { name: /0xaaaa/ })).toHaveAttribute('href', 'https://bscscan.com/tx/0x' + 'a'.repeat(64))
  expect(document.body).not.toHaveTextContent('synthetic-private-sentinel')
  readonly()
})
