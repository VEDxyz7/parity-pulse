import { useEffect, useRef, useState } from 'react'
import { fetchTrust, type TrustResult } from '../services/trust'
import { TrustEvidence } from './TrustEvidence'

export function TrustPanel({ mode }: { mode: 'DEMO' | 'LIVE_READ_ONLY' }) {
  const [ticker, setTicker] = useState('NVDA')
  const [result, setResult] = useState<TrustResult | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const pending = useRef<AbortController | null>(null)
  useEffect(() => () => { pending.current?.abort() }, [])
  useEffect(() => {
    if (!result) return
    const timeout = setTimeout(() => { setResult(null); setError('Assessment expired. Request fresh evidence.') },
      Math.max(0, Date.parse(result.evaluated_at) + 120_000 - Date.now()))
    return () => clearTimeout(timeout)
  }, [result])
  async function assess(event: React.FormEvent) {
    event.preventDefault()
    pending.current?.abort()
    const controller = new AbortController()
    pending.current = controller
    setResult(null); setError(''); setBusy(true)
    const timeout = setTimeout(() => controller.abort(), 60_000)
    try {
      const response = await fetchTrust(ticker.trim().toUpperCase(), mode, controller.signal)
      if (pending.current === controller && !controller.signal.aborted) setResult(response)
    } catch {
      if (pending.current === controller) setError('Trust unavailable or invalid. No classification was substituted.')
    } finally {
      clearTimeout(timeout)
      if (pending.current === controller) setBusy(false)
    }
  }
  return <section className="panel trust-panel" aria-label="Trust Layer" id="trust">
    <div className="panel-heading"><div><h2>Trust Layer</h2><p>Canonical Phase 2 · analytical only · TRUST_GATE blocked</p></div></div>
    <form onSubmit={event => { void assess(event) }} className="trust-form">
      <label htmlFor="trust-ticker">Stock ticker</label>
      <input id="trust-ticker" value={ticker} maxLength={15} onChange={event => setTicker(event.target.value)} required />
      <button type="submit" className="refresh-button" disabled={busy}>{busy ? 'Assessing evidence…' : 'Assess trust'}</button>
    </form>
    <p className="trust-note">{mode === 'DEMO' ? 'Synthetic DEMO inputs stay separate from real provider data.' : 'Read-only provider evidence; unavailable current equity data fails closed.'} Confidence is an uncalibrated heuristic. This assessment does not authorize execution or alter an Ask proposal.</p>
    {error && <p role="alert">{error}</p>}
    {result && <TrustEvidence result={result} />}
  </section>
}
