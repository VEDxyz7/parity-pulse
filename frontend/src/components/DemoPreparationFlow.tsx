import { Button } from '../ui/Button'
import { RouteComparison } from './RouteComparison'
import { useDemoPipeline } from './DemoPipeline'
import { DemoPaperFlow } from './DemoPaperFlow'
import { useEffect, useRef, useState } from 'react'
import type { DemoResult } from '../services/demoSandbox'
import type { OpportunityResult, RiskResult } from '../services/demoOpportunity'
import { fetchPreparation, fetchQuote, fetchSimulation, type PreparationResult, type QuoteResult, type SimulationResult } from '../services/demoPreparation'

export function DemoPreparationFlow({ trust, opportunity, risk, opportunityExpired }: {
  trust: DemoResult; opportunity: OpportunityResult; risk: RiskResult; opportunityExpired: boolean
}) {
  const pipeline = useDemoPipeline()
  const [paperFilled, setPaperFilled] = useState(false)
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
    const label = stage === 'quote' ? 'QUOTE' : stage === 'prepare' ? 'PREPARATION' : 'SIMULATION'
    pipeline.resetFrom(label); pipeline.report(label, 'running', 'Calling the isolated scenario service')
    if (stage !== 'simulate') setPrepared(null)
    if (stage === 'quote') setQuote(null)
    const timer = setTimeout(() => controller.abort(), 60_000)
    try {
      if (stage === 'quote') {
        const response = await fetchQuote(trust, opportunity, risk, controller.signal)
        if (pending.current === controller && !controller.signal.aborted) {
          setQuote(response)
          pipeline.report('QUOTE', response.status === 'QUOTED' ? 'pass' : 'rejected', `${response.status}: ${response.reason_codes.join(' · ')}`)
          if (response.route_decision) pipeline.report('ROUTING', response.route_decision.status === 'ROUTE_SELECTED' ? 'pass' : 'rejected', `${response.route_decision.status}: ${response.route_decision.explanation}`)
        }
      } else if (stage === 'prepare' && quote) {
        const response = await fetchPreparation(quote, opportunity, controller.signal)
        if (pending.current === controller && !controller.signal.aborted) {
          setPrepared(response)
          pipeline.report('PREPARATION', response.status === 'PREPARED' ? 'pass' : 'rejected', `${response.status}: ${response.reason_codes.join(' · ')}`)
        }
      } else if (stage === 'simulate' && quote && prepared) {
        const response = await fetchSimulation(quote, prepared, opportunity, controller.signal)
        if (pending.current === controller && !controller.signal.aborted) {
          setSimulation(response)
          pipeline.report('SIMULATION', response.simulation.status === 'SIMULATION_PASS' ? 'pass' : 'rejected', `${response.simulation.status}: ${response.simulation.reason_codes.join(' · ')}`)
        }
      }
    } catch {
      if (pending.current === controller) {
        setError('Scenario result unavailable, expired or invalid. No execution occurred. Refresh the analysis/quote before retrying.')
        pipeline.report(label, 'failed', 'API result unavailable, expired or invalid; no execution occurred')
      }
    } finally {
      clearTimeout(timer)
      if (pending.current === controller) setBusy(null)
    }
  }
  const q = quote?.quote, transaction = prepared?.transaction, s = simulation?.simulation
  const disabled = busy !== null || expired || opportunityExpired || paperFilled
  return <section aria-label="Illustrative Quote Preparation and Simulation" className="demo-preparation-flow">
    <h4>Quote → Risk revalidation → Transaction Preparation → Simulation</h4>
    <p>Illustrative data · synthetic quote and unsigned request. Not live market data.</p>
    <p>Unsigned synthetic request only. No wallet, order, broadcast or moved funds.</p>
    <Button className="refresh-button" disabled={busy !== null || opportunityExpired || paperFilled} onClick={() => { void run('quote') }}>
      {busy === 'quote' ? 'Generating illustrative quote…' : 'Generate Illustrative Quote'}
    </Button>
    {error && <p role="alert">{error}</p>}
    {quote && <>
      <h4>Quote: <strong>{quote.status}</strong>{expired || opportunityExpired ? ' (expired)' : ''}</h4>
      {quote.route_decision && <RouteComparison route={quote.route_decision} expired={expired || opportunityExpired} />}
      <p>Quote reasons: {quote.reason_codes.join(' · ')}</p>
      <p>Risk before quote: {quote.risk_before_quote.status} · Risk after quoted economics: {quote.risk_revalidation?.status ?? 'NOT_RUN'}</p>
      {q && <>
        <p>Source: synthetic scenario · Illustrative economic quote · {q.ticker} / {q.symbol} · BUY · Issuer: {q.issuer}</p>
        <p>Quote ID: <code>{q.quote_id}</code></p>
        <dl className="trust-facts">
          <div><dt>Synthetic execution price / USD per token</dt><dd>{q.execution_price_usd}</dd></div>
          <div><dt>Output token quantity</dt><dd>{q.output_token_quantity}</dd></div>
          <div><dt>Share exposure</dt><dd>{q.share_exposure}</dd></div>
          <div><dt>Input / illustrative USD</dt><dd>{q.input_amount_usd}</dd></div>
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
      {(expired || opportunityExpired) && <p role="status">Illustrative quote or Opportunity expired. Re-run analysis and obtain a fresh quote.</p>}
      {quote.status === 'QUOTED' && <Button className="refresh-button" disabled={disabled} onClick={() => { void run('prepare') }}>
        {busy === 'prepare' ? 'Preparing unsigned request…' : 'Prepare Unsigned Request'}
      </Button>}
    </>}
    {prepared && <>
      <h4>Transaction: <strong>{prepared.status}</strong></h4>
      <p>Preparation reasons: {prepared.reason_codes.join(' · ')} · Revalidated Risk: {prepared.risk_revalidation.status}</p>
      {transaction && <>
        <p>Request ID: <code>{transaction.transaction_id}</code></p>
        <p>UNSIGNED SYNTHETIC REQUEST · NOT BROADCAST</p>
        <p>Synthetic request representation · Not signed · Not executed · Not broadcastable</p>
        <details><summary>Prepared request parameters and provenance</summary><pre>{JSON.stringify(transaction.parameters, null, 2)}</pre></details>
        <p>Request fingerprint: <code>{transaction.fingerprint}</code></p>
        <Button className="refresh-button" disabled={disabled} onClick={() => { void run('simulate') }}>
          {busy === 'simulate' ? 'Evaluating local constraints…' : 'Run Local Simulation'}
        </Button>
      </>}
    </>}
    {s && <>
      <h4>Simulation: <strong>{s.status}</strong>{expired || opportunityExpired ? ' (expired)' : ''}</h4>
      <p>LOCAL CONSTRAINT CHECK · NOT ON-CHAIN EXECUTION</p>
      <p>Illustrative constraint evaluation — not a chain simulation</p>
      <p>Simulation reasons: {s.reason_codes.join(' · ')}</p>
      <ul>{s.checks.map(check => <li key={check.code}>{check.passed ? 'PASS' : 'FAIL'} · {check.code}: {check.detail}</li>)}</ul>
      <p>No real transaction was broadcast. No money moved. Execution remains blocked.</p>
    </>}
    {simulation && s?.status === 'SIMULATION_PASS' && quote && prepared && <DemoPaperFlow
      key={s.simulation_id} quote={quote} prepared={prepared} simulation={simulation} origin={opportunity}
      expired={expired || opportunityExpired} onFilled={() => setPaperFilled(true)} />}
    {quote && <details><summary>Quote / Preparation / Simulation audit contracts</summary><pre>{JSON.stringify({ quote, prepared, simulation }, null, 2)}</pre></details>}
  </section>
}
