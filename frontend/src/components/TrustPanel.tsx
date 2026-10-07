import { useEffect, useRef, useState } from 'react'
import { fetchTrust, type TrustResult } from '../services/trust'

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
    {result && <div aria-live="polite" className="trust-results">
      <p><strong>{result.ticker ?? 'Unsupported stock'} · {result.status}</strong> · {result.data_mode}</p>
      <p>Evaluated at: <time>{result.evaluated_at}</time></p>
      <p>Market regime: {result.regime?.state ?? 'UNAVAILABLE'} · {result.regime?.baseline_bucket ?? 'No verified schedule'}</p>
      {result.regime && <p>Previous actual regular close: {result.regime.previous_regular_close}</p>}
      {result.representations.map(row => <article className="trust-representation" key={`${row.issuer}:${row.contract}`}>
        <h3>{row.symbol} · {row.issuer}</h3>
        <p><strong>{row.classification}</strong> · Evidence: {row.evidence_quality} · Confidence: {row.confidence ?? 'UNAVAILABLE'}</p>
        <dl className="trust-facts">
          <div><dt>Token USD / token</dt><dd>{row.token_price_usd ?? 'UNAVAILABLE'}</dd></div>
          <div><dt>Shares / token</dt><dd>{row.token_to_share_ratio}</dd></div>
          <div><dt>Token timestamp</dt><dd>{row.token_timestamp ?? 'UNAVAILABLE'}</dd></div>
          <div><dt>Independent equity</dt><dd>{row.reference.status} · {row.reference.observation?.source ?? 'No source'} · {row.reference.observation?.data_quality ?? 'MISSING'} · {row.reference.observation?.price ?? 'No price'}</dd></div>
          <div><dt>Reference as of</dt><dd>{row.reference.reference_asof ?? 'UNAVAILABLE'}</dd></div>
          <div><dt>Timestamp skew / seconds</dt><dd>{row.reference.timestamp_skew_seconds ?? 'UNAVAILABLE'}</dd></div>
          <div><dt>Token age / seconds</dt><dd>{row.reference.token_age_seconds ?? 'UNAVAILABLE'}</dd></div>
          <div><dt>Effective USD / share</dt><dd>{row.economic_comparison?.effective_price_per_share_usd ?? 'UNAVAILABLE'}</dd></div>
          <div><dt>Comparable USD / token</dt><dd>{row.economic_comparison?.comparable_token_value_usd ?? 'UNAVAILABLE'}</dd></div>
          <div><dt>Deviation / fraction</dt><dd>{row.economic_comparison?.deviation ?? 'UNAVAILABLE'}</dd></div>
          <div><dt>Baseline episodes</dt><dd>{row.baseline.sample_count} / {row.baseline.minimum_sample_count} · {row.baseline.status}</dd></div>
          <div><dt>Liquidity / USD</dt><dd>{row.liquidity.liquidity_usd ?? 'UNAVAILABLE'} · {row.liquidity.status}</dd></div>
          <div><dt>News</dt><dd>{row.news.state} · {row.news.coverage} · {row.news.article_ids.length} articles</dd></div>
          <div><dt>Analogues</dt><dd>{row.analogues.retrieved_sample_count} of {row.analogues.eligible_sample_count} · {row.analogues.status}</dd></div>
        </dl>
        <p>Reasons: {row.reason_codes.join(' · ')}</p>
        {row.missing_evidence.length > 0 && <p>Missing evidence: {row.missing_evidence.join(' · ')}</p>}
      </article>)}
      <p>Limitations: {result.limitations.join(' · ')}</p>
      <p>{result.no_broadcast_statement}</p>
    </div>}
  </section>
}
