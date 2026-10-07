import { useEffect, useRef, useState } from 'react'
import type { DemoResult } from '../services/demoSandbox'
import type { OpportunityResult, RiskResult } from '../services/demoOpportunity'
import { fetchPreparation, fetchQuote, fetchSimulation, type PreparationResult, type QuoteResult, type SimulationResult } from '../services/demoPreparation'

export function DemoPreparationFlow({ trust, opportunity, risk, opportunityExpired }: {
  trust: DemoResult; opportunity: OpportunityResult; risk: RiskResult; opportunityExpired: boolean
}) {
  const [quote, setQuote] = useState<QuoteResult | null>(null)
  const [prepared, setPrepared] = useState<PreparationResult | null>(null)
  const [simulation, setSimulation] = useState<SimulationResult | null>(null)
  const [busy, setBusy] = useState<'quote' | 'prepare' | 'simulate' | null>(null)
  const [expired, setExpired] = useState(false)
  const [error, setError] = useState('')
  const pending = useRef<AbortController | null>(null)
  useEffect(() => () => { pending.current?.abort(); pending.current = null }, [])
  useEffect(() => {
    setExpired(false)
    if (!quote?.quote) return
    const timer = setTimeout(() => setExpired(true), Date.parse(quote.quote.valid_until) - Date.parse(quote.quote.quoted_at))
    return () => clearTimeout(timer)
  }, [quote])
  async function run(stage: 'quote' | 'prepare' | 'simulate') {
    pending.current?.abort()
    const controller = new AbortController(); pending.current = controller
    setBusy(stage); setError(''); setSimulation(null)
    if (stage !== 'simulate') setPrepared(null)
    if (stage === 'quote') setQuote(null)
    const timer = setTimeout(() => controller.abort(), 60_000)
    try {
      if (stage === 'quote') {
        const response = await fetchQuote(trust, opportunity, risk, controller.signal)
        if (pending.current === controller && !controller.signal.aborted) setQuote(response)
      } else if (stage === 'prepare' && quote) {
        const response = await fetchPreparation(quote, opportunity, controller.signal)
        if (pending.current === controller && !controller.signal.aborted) setPrepared(response)
      } else if (stage === 'simulate' && quote && prepared) {
        const response = await fetchSimulation(quote, prepared, opportunity, controller.signal)
        if (pending.current === controller && !controller.signal.aborted) setSimulation(response)
      }
    } catch {
      if (pending.current === controller) setError('DEMO downstream result unavailable, expired or invalid. No execution occurred. Refresh the analysis/quote before retrying.')
    } finally {
      clearTimeout(timer)
      if (pending.current === controller) setBusy(null)
    }
  }
  const q = quote?.quote, transaction = prepared?.transaction, s = simulation?.simulation
  const disabled = busy !== null || expired || opportunityExpired
  return <section aria-label="Demo Quote Preparation and Simulation" className="demo-preparation-flow">
    <h4>Quote → Risk revalidation → Transaction Preparation → Simulation</h4>
    <p><strong>DEMO SANDBOX</strong><br /><span>SIMULATED DATA</span> — <span>NOT LIVE MARKET DATA</span></p>
    <p>Unsigned synthetic request only. No wallet, order, broadcast or moved funds.</p>
    <button className="refresh-button" disabled={busy !== null || opportunityExpired} onClick={() => { void run('quote') }}>
      {busy === 'quote' ? 'Generating DEMO quote…' : 'Generate DEMO Quote'}
    </button>
    {error && <p role="alert">{error}</p>}
    {quote && <>
      <h4>Quote: <strong>{quote.status}</strong>{expired || opportunityExpired ? ' (expired)' : ''}</h4>
      <p>Quote reasons: {quote.reason_codes.join(' · ')}</p>
      <p>Risk before quote: {quote.risk_before_quote.status} · Risk after quoted economics: {quote.risk_revalidation?.status ?? 'NOT_RUN'}</p>
      {q && <>
        <p>Source: DEMO · Synthetic economic quote · {q.ticker} / {q.symbol} · BUY · Issuer: {q.issuer}</p>
        <p>Quote ID: <code>{q.quote_id}</code></p>
        <dl className="trust-facts">
          <div><dt>Synthetic execution price / USD per token</dt><dd>{q.execution_price_usd}</dd></div>
          <div><dt>Output token quantity</dt><dd>{q.output_token_quantity}</dd></div>
          <div><dt>Share exposure</dt><dd>{q.share_exposure}</dd></div>
          <div><dt>Input / DEMO USD</dt><dd>{q.input_amount_usd}</dd></div>
          <div><dt>Fees / USD</dt><dd>{q.fees_usd}</dd></div>
          <div><dt>Gas / USD</dt><dd>{q.gas_usd}</dd></div>
          <div><dt>Slippage assumption / bps</dt><dd>{q.slippage_bps}</dd></div>
          <div><dt>Slippage embedded in price / USD</dt><dd>{q.estimated_slippage_usd}</dd></div>
          <div><dt>Execution reserve / USD</dt><dd>{q.execution_buffer_usd}</dd></div>
          <div><dt>Total cash required including reserve / USD</dt><dd>{q.total_cash_required_usd}</dd></div>
          <div><dt>Quoted net hypothetical edge / USD</dt><dd>{q.net_hypothetical_edge_usd}</dd></div>
        </dl>
        <p>Synthetic quote time: {q.quoted_at} · Expiry: {q.valid_until}</p>
        <p>Underlying synthetic observation: {q.market_observed_at} / {q.market_observation_kind}. No live market refresh is claimed.</p>
      </>}
      {(expired || opportunityExpired) && <p role="status">DEMO quote or Opportunity expired. Re-run analysis and obtain a fresh quote.</p>}
      {quote.status === 'QUOTED' && <button className="refresh-button" disabled={disabled} onClick={() => { void run('prepare') }}>
        {busy === 'prepare' ? 'Preparing DEMO request…' : 'Prepare DEMO Transaction'}
      </button>}
    </>}
    {prepared && <>
      <h4>Transaction: <strong>{prepared.status}</strong></h4>
      <p>Preparation reasons: {prepared.reason_codes.join(' · ')} · Revalidated Risk: {prepared.risk_revalidation.status}</p>
      {transaction && <>
        <p>Request ID: <code>{transaction.transaction_id}</code></p>
        <p>DEMO_BUY_REQUEST · CANONICAL_JSON_DEMO_REQUEST · Not signed · Not executed · Not broadcastable</p>
        <details><summary>Prepared DEMO request parameters</summary><pre>{JSON.stringify(transaction.parameters, null, 2)}</pre></details>
        <p>Request fingerprint: <code>{transaction.fingerprint}</code></p>
        <button className="refresh-button" disabled={disabled} onClick={() => { void run('simulate') }}>
          {busy === 'simulate' ? 'Evaluating DEMO constraints…' : 'Run DEMO Simulation'}
        </button>
      </>}
    </>}
    {s && <>
      <h4>Simulation: <strong>{s.status}</strong>{expired || opportunityExpired ? ' (expired)' : ''}</h4>
      <p>LOCAL DEMO CONSTRAINT EVALUATION — NOT A CHAIN SIMULATION</p>
      <p>Simulation reasons: {s.reason_codes.join(' · ')}</p>
      <ul>{s.checks.map(check => <li key={check.code}>{check.passed ? 'PASS' : 'FAIL'} · {check.code}: {check.detail}</li>)}</ul>
      <p>No real transaction was broadcast. No money moved. Execution remains blocked.</p>
    </>}
    {quote && <details><summary>Quote / Preparation / Simulation audit contracts</summary><pre>{JSON.stringify({ quote, prepared, simulation }, null, 2)}</pre></details>}
  </section>
}
