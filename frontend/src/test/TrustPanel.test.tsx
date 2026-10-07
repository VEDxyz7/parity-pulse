import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it, vi } from 'vitest'
import { TrustPanel } from '../components/TrustPanel'
import { parseTrust } from '../services/trust'

const fixture = () => ({
  assessment_id: 'synthetic-trust', ticker: 'NVDA', data_mode: 'DEMO', status: 'ASSESSED',
  evaluated_at: new Date().toISOString(), trust_gate: 'BLOCKED',
  regime: { state: 'REGULAR', baseline_bucket: 'REGULAR', previous_regular_close: '2026-10-05T20:00:00Z', schedule_version: 'SYNTHETIC' },
  representations: [{ ticker: 'NVDA', issuer: 'synthetic', symbol: 'DEMO-NVDA', contract: 'demo:NVDA',
    token_price_usd: '55', token_to_share_ratio: '0.5', token_timestamp: new Date().toISOString(),
    classification: 'INSUFFICIENT_EVIDENCE', confidence: null, evidence_quality: 'INSUFFICIENT',
    reference: { status: 'UNAVAILABLE', reference_asof: null, observation: null,
      timestamp_skew_seconds: null, token_age_seconds: '1', reason_codes: ['INDEPENDENT_REFERENCE_UNAVAILABLE'] },
    economic_comparison: null, baseline: { status: 'INSUFFICIENT', sample_count: 0, minimum_sample_count: 30 },
    liquidity: { status: 'UNAVAILABLE', volume_24h_usd: null, liquidity_usd: null },
    news: { state: 'PARTIAL', coverage: 'PARTIAL', article_ids: [], provider_llm_sentiment_used: false },
    analogues: { status: 'INSUFFICIENT', retrieved_sample_count: 0, eligible_sample_count: 0 },
    reason_codes: ['BASELINE_INSUFFICIENT'], missing_evidence: ['INDEPENDENT_REFERENCE_UNAVAILABLE'],
  }], limitations: ['UNCALIBRATED_ENGINEERING_RULES'],
  execution_mode: 'DRY_RUN', approval_mode: 'PROPOSE_ONLY', require_simulation: true,
  live_trading_enabled: false, execution_ready: false, transaction_broadcast: false, llm_authoritative: false,
  no_broadcast_statement: 'No real transaction was broadcast.',
})
afterEach(() => { vi.unstubAllGlobals(); vi.useRealTimers() })

it('requests only on demand with GET and renders backend evidence and missing inputs', async () => {
  const mock = vi.fn(async () => new Response(JSON.stringify(fixture()), { status: 200 }))
  vi.stubGlobal('fetch', mock)
  render(<TrustPanel mode="DEMO" />)
  expect(mock).not.toHaveBeenCalled()
  await userEvent.click(screen.getByRole('button', { name: 'Assess trust' }))
  expect(await screen.findByText('INSUFFICIENT_EVIDENCE')).toBeInTheDocument()
  expect(screen.getByText('55')).toBeInTheDocument()
  expect(screen.getByText('0.5')).toBeInTheDocument()
  expect(screen.getByText(/Missing evidence/)).toHaveTextContent('INDEPENDENT_REFERENCE_UNAVAILABLE')
  expect(screen.getByText('No real transaction was broadcast.')).toBeInTheDocument()
  expect((mock.mock.calls[0] as unknown as [string, RequestInit])[0]).toBe('/api/assets/NVDA/trust')
  expect((mock.mock.calls[0] as unknown as [string, RequestInit])[1].method).toBe('GET')
  expect(screen.queryByRole('button', { name: /execute|confirm|buy now/i })).not.toBeInTheDocument()
})

it.each([
  { data_mode: 'LIVE' }, { transaction_broadcast: true }, { execution_ready: true },
  { live_trading_enabled: true }, { require_simulation: false }, { llm_authoritative: true },
  { trust_gate: 'PASS' }, { execution_mode: 'LIVE' }, { approval_mode: 'AUTO' },
])('rejects unsafe or cross-mode trust response %j', override => {
  expect(() => parseTrust({ ...fixture(), ...override }, 'DEMO')).toThrow('could not be verified')
})

it('rejects numerical finance and unsupported positive classification', () => {
  const row = fixture().representations[0]
  for (const override of [{ token_price_usd: 55 }, { token_to_share_ratio: null },
    { classification: 'NORMAL', confidence: 'HIGH', missing_evidence: [] },
    { reference: { ...row.reference, observation: { source: 'BINANCE_RWA', price: '100', data_quality: 'LIVE', kind: 'QUOTE' } } }]) {
    expect(() => parseTrust({ ...fixture(), representations: [{ ...row, ...override }] }, 'DEMO')).toThrow()
  }
})

it('reports unsupported stock and clears a previous result on failed retry', async () => {
  const mock = vi.fn(async () => new Response(JSON.stringify({ ...fixture(), status: 'UNAVAILABLE', ticker: null, representations: [] }), { status: 200 }))
  vi.stubGlobal('fetch', mock)
  render(<TrustPanel mode="DEMO" />)
  await userEvent.click(screen.getByRole('button', { name: 'Assess trust' }))
  expect(await screen.findByText(/Unsupported stock/)).toBeInTheDocument()
  mock.mockRejectedValue(new Error('raw secret error'))
  await userEvent.click(screen.getByRole('button', { name: 'Assess trust' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('No classification was substituted')
  expect(screen.queryByText(/Unsupported stock/)).not.toBeInTheDocument()
  expect(screen.queryByText('raw secret error')).not.toBeInTheDocument()
})

it('expires timestamped evidence without recomputing trust', async () => {
  vi.useFakeTimers()
  vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify(fixture()), { status: 200 })))
  render(<TrustPanel mode="DEMO" />)
  await act(async () => { fireEvent.submit(screen.getByRole('button', { name: 'Assess trust' }).closest('form')!) })
  expect(screen.getByText('INSUFFICIENT_EVIDENCE')).toBeInTheDocument()
  await act(async () => { await vi.advanceTimersByTimeAsync(120_001) })
  expect(screen.getByRole('alert')).toHaveTextContent('Assessment expired')
  expect(screen.queryByText('INSUFFICIENT_EVIDENCE')).not.toBeInTheDocument()
})

it('bounds slow requests and aborts on unmount', async () => {
  vi.useFakeTimers()
  let signal: AbortSignal | undefined
  const mock = vi.fn((_url: string, options: RequestInit) => new Promise<Response>((_resolve, reject) => {
    signal = options.signal as AbortSignal
    signal.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')), { once: true })
  }))
  vi.stubGlobal('fetch', mock)
  const view = render(<TrustPanel mode="DEMO" />)
  fireEvent.submit(screen.getByRole('button', { name: 'Assess trust' }).closest('form')!)
  await act(async () => { await vi.advanceTimersByTimeAsync(60_001) })
  expect(signal!.aborted).toBe(true)
  expect(screen.getByRole('alert')).toHaveTextContent('Trust unavailable')
  fireEvent.submit(screen.getByRole('button', { name: 'Assess trust' }).closest('form')!)
  await act(async () => { view.unmount() })
  expect(signal!.aborted).toBe(true)
})
