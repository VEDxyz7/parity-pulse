import { ProposalReview } from './ProposalReview'
import { RouteComparison } from './RouteComparison'
import { useEffect, useRef, useState } from 'react'
import { requestProposal, type Proposal } from '../services/exposure'

export function AskFlow({ mode }: { mode: 'DEMO' | 'LIVE_READ_ONLY' }) {
  const [text, setText] = useState('I have $50 of Nvidia')
  const [result, setResult] = useState<Proposal | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [pending, setPending] = useState(false)
  const [expired, setExpired] = useState(false)
  const controller = useRef<AbortController | null>(null)
  useEffect(() => () => controller.current?.abort(), [])
  useEffect(() => {
    if (!result) return
    const remaining = Date.parse(result.valid_until) - Date.now()
    const timer = setTimeout(() => setExpired(true), Math.max(0, Math.min(remaining, 60_000)))
    return () => clearTimeout(timer)
  }, [result])
  async function submit(event: React.SubmitEvent<HTMLFormElement>) {
    event.preventDefault()
    controller.current?.abort()
    const aborter = new AbortController()
    controller.current = aborter
    setResult(null); setError(null); setPending(true); setExpired(false)
    const timer = setTimeout(() => aborter.abort(), 60_000)
    try {
      const proposal = await requestProposal(text, mode, aborter.signal)
      if (!aborter.signal.aborted) setResult(proposal)
    } catch {
      if (controller.current === aborter) setError('Proposal unavailable or invalid. Check your stock and USD budget, then retry.')
    } finally {
      clearTimeout(timer)
      if (controller.current === aborter) setPending(false)
    }
  }
  const selected = !expired ? result?.selected : null
  return <section className="panel ask-panel" id="ask" aria-label="Working Ask Flow">
    <div className="panel-heading"><div><h2>Ask for stock exposure</h2><p>Compare an indicative exposure estimate. No funds move.</p></div><span className="banner-tag">{mode === 'DEMO' ? 'Synthetic demo' : 'Real read-only data'}</span></div>
    <form onSubmit={event => { void submit(event) }} className="ask-form">
      <label htmlFor="stock-request">Stock request</label>
      <input id="stock-request" value={text} onChange={event => setText(event.target.value)} maxLength={240} required disabled={pending} autoComplete="off" />
      <button className="refresh-button" type="submit" disabled={pending}>{pending ? 'Preparing estimate' : 'Create dry-run proposal'}</button>
      <small>Use “Buy $50 Apple” or “I have $50 of Nvidia”. Budget is USD notional before unavailable fees.</small>
    </form>
    {error && <p role="alert" className="connection-alert">{error}</p>}
    {result && <div className="ask-result" aria-live="polite">
      <h3>{result.company_name ?? 'Request needs attention'} {result.ticker && `(${result.ticker})`}</h3>
      <p><strong>{expired ? 'EXPIRED — request a fresh estimate' : result.status}</strong> · {result.data_mode === 'DEMO' ? 'Synthetic DEMO values; not current market prices' : 'LIVE read-only observations'}</p>
      <p>{result.broadcast_statement}</p>
      <p>{result.route_selection_reason}</p>
      {result.route_decision && <RouteComparison route={result.route_decision} expired={expired} />}
      {selected && <dl className="ask-details">
        <dt>Selected issuer / token</dt><dd>{selected.issuer} / {selected.token_symbol}</dd>
        <dt>Shares per token</dt><dd>{selected.token_to_share_ratio}</dd>
        <dt>Token price (USD)</dt><dd>{selected.token_price_usd}</dd>
        <dt>Effective cost per real share (USD)</dt><dd>{selected.effective_cost_per_share_usd}</dd>
        <dt>Requested budget (USD)</dt><dd>{result.requested_budget_usd}</dd>
        <dt>Estimated token quantity</dt><dd>{selected.estimated_token_quantity}</dd>
        <dt>Estimated real-share exposure</dt><dd>{selected.estimated_real_share_exposure}</dd>
        <dt>Estimated token cost (USD)</dt><dd>{selected.estimated_token_cost_usd}</dd>
        <dt>Unallocated notional (USD)</dt><dd>{selected.unallocated_budget_usd}</dd>
        <dt>Issuer market state</dt><dd>{selected.market_state}</dd>
        <dt>Price source / quality / time</dt><dd>{selected.price_source} / {selected.price_quality} / {selected.price_timestamp ?? 'Unavailable'}</dd>
        <dt>Chain / representation</dt><dd>{selected.chain_id} / {selected.contract}</dd>
      </dl>}
      {!expired && result.representations.length > 0 && <div className="comparison-scroll"><table><caption>Discovered representation comparison — indicative prices only</caption><thead><tr><th>Issuer</th><th>Shares/token</th><th>USD/share</th><th>Estimate eligibility</th></tr></thead><tbody>{result.representations.map(row => <tr key={`${row.chain_id}:${row.contract}`}><td>{row.issuer}</td><td>{row.token_to_share_ratio}</td><td>{row.effective_cost_per_share_usd ?? 'Unavailable'}</td><td>{row.estimate_eligible ? 'Eligible for estimate only' : row.exclusion_reasons.join(', ')}</td></tr>)}</tbody></table></div>}
      <p>Fees, gas, funding conversion, slippage and liquidity: unknown. Independent current equity: {result.independent_equity.status}{result.independent_equity.price_usd_per_share ? ` / ${result.independent_equity.price_usd_per_share} USD/share (${result.independent_equity.source})` : ' / unavailable'}.</p>
      <p>Simulation: UNAVAILABLE. Execution readiness: BLOCKED. Trust integration: NOT ASSESSED for this proposal.</p>
      <details><summary>Execution blockers and data limitations</summary><ul>{result.execution_blockers.map(reason => <li key={reason}>{reason}</li>)}{Object.entries(result.limitations).map(([key, value]) => <li key={key}>{key}: {value}</li>)}</ul></details>
      <ProposalReview key={result.proposal_id} proposal={result} mode={mode} expired={expired} />
      <small>Proposal {result.proposal_id} · valid until {result.valid_until}. An estimate is not a vendor quote, simulated transaction, order or position.</small>
    </div>}
  </section>
}
