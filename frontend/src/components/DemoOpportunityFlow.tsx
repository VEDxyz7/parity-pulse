import { RouteComparison } from './RouteComparison'
import { useEffect, useRef, useState } from 'react'
import type { DemoResult } from '../services/demoSandbox'
import { fetchOpportunity, fetchRisk, type OpportunityResult, type RiskResult } from '../services/demoOpportunity'
import { DemoPreparationFlow } from './DemoPreparationFlow'

export function DemoOpportunityFlow({ trust }: { trust: DemoResult }) {
  const [opportunity, setOpportunity] = useState<OpportunityResult | null>(null)
  const [risk, setRisk] = useState<RiskResult | null>(null)
  const [busy, setBusy] = useState<'opportunity' | 'risk' | null>(null)
  const [expired, setExpired] = useState(false)
  const [error, setError] = useState('')
  const pending = useRef<AbortController | null>(null)
  useEffect(() => () => { pending.current?.abort(); pending.current = null }, [])
  useEffect(() => {
    setExpired(false)
    if (!opportunity) return
    const lifetime = Date.parse(opportunity.opportunity.valid_until) - Date.parse(opportunity.opportunity.evaluated_at)
    const timer = setTimeout(() => setExpired(true), lifetime)
    return () => clearTimeout(timer)
  }, [opportunity])
  async function analyze(stage: 'opportunity' | 'risk') {
    pending.current?.abort()
    const controller = new AbortController()
    pending.current = controller
    setBusy(stage); setError(''); setRisk(null)
    if (stage === 'opportunity') setOpportunity(null)
    const timer = setTimeout(() => controller.abort(), 60_000)
    try {
      if (stage === 'opportunity') {
        const response = await fetchOpportunity(trust, controller.signal)
        if (pending.current === controller && !controller.signal.aborted) setOpportunity(response)
      } else if (opportunity) {
        const response = await fetchRisk(opportunity, controller.signal)
        if (pending.current === controller && !controller.signal.aborted) setRisk(response)
      }
    } catch {
      if (pending.current === controller) setError('Demo analysis unavailable, expired or invalid. No action was approved. Run the scenario again if needed.')
    } finally {
      clearTimeout(timer)
      if (pending.current === controller) setBusy(null)
    }
  }
  const decision = opportunity?.opportunity
  const economics = decision?.economics
  return <section className="demo-opportunity-flow" aria-label="Demo Opportunity and Risk">
    <h3>Trust → Opportunity → Risk</h3>
    <p>DEMO SANDBOX · SIMULATED DATA — NOT LIVE MARKET DATA</p>
    <p>Economic targets, costs and risk limits are explicitly synthetic assumptions. Trust confidence remains uncalibrated. DEMO quotes, unsigned requests and local constraint checks grant no execution authority.</p>
    <button className="refresh-button" disabled={busy !== null} onClick={() => { void analyze('opportunity') }}>
      {busy === 'opportunity' ? 'Analyzing opportunity…' : 'Analyze Opportunity'}
    </button>
    {error && <p role="alert">{error}</p>}
    {decision && <>
      <h4>Opportunity: <strong>{decision.status}</strong></h4>
      <p>Action: {decision.action} · {decision.ticker} / {decision.symbol} · Issuer: {decision.issuer}</p>
      <p>Source Trust: {decision.source_trust_classification} · Confidence: {decision.confidence ?? 'UNAVAILABLE'} (uncalibrated)</p>
      <p>Decision reasons: {decision.reason_codes.join(' · ')}</p>
  {opportunity?.route_decision && <RouteComparison route={opportunity.route_decision} expired={expired} />}
      {economics && <dl className="trust-facts">
        <div><dt>Token price / USD</dt><dd>{economics.token_price_usd}</dd></div>
        <div><dt>Shares per token</dt><dd>{economics.token_to_share_ratio}</dd></div>
        <div><dt>Independent reference / USD per share</dt><dd>{economics.independent_share_price_usd}</dd></div>
        <div><dt>Effective price / USD per share</dt><dd>{economics.effective_price_per_share_usd}</dd></div>
        <div><dt>Reference deviation (not predicted return)</dt><dd>{economics.reference_deviation}</dd></div>
        <div><dt>Hypothetical target / USD per share</dt><dd>{economics.hypothetical_target_share_price_usd}</dd></div>
        <div><dt>Hypothetical adjustment / USD per share</dt><dd>{economics.hypothetical_adjustment_per_share_usd}</dd></div>
        <div><dt>Requested notional / USD</dt><dd>{economics.requested_notional_usd}</dd></div>
        <div><dt>Gross hypothetical edge / USD</dt><dd>{economics.gross_hypothetical_edge_usd}</dd></div>
        <div><dt>Fees / USD</dt><dd>{economics.fees_usd}</dd></div>
        <div><dt>Gas / USD</dt><dd>{economics.gas_usd}</dd></div>
        <div><dt>Estimated slippage / USD</dt><dd>{economics.estimated_slippage_usd}</dd></div>
        <div><dt>Execution buffer / USD</dt><dd>{economics.execution_buffer_usd}</dd></div>
        <div><dt>Net hypothetical edge / USD</dt><dd>{economics.net_hypothetical_edge_usd}</dd></div>
      </dl>}
      <p>Synthetic-clock validity: {decision.evaluated_at} → {decision.valid_until}</p>
      {expired && <p role="status">This analytical proposal has expired. Run the scenario again.</p>}
      <button className="refresh-button" disabled={busy !== null || expired} onClick={() => { void analyze('risk') }}>
        {busy === 'risk' ? 'Checking risk…' : 'Analyze Risk'}
      </button>
    </>}
    {risk && <>
      <h4>Risk: <strong>{risk.risk.status}</strong>{expired ? ' (expired analytical result)' : ''}</h4>
      <p>Analytical approval only. Execution remains blocked.</p>
      <p>Risk reasons: {risk.risk.reason_codes.join(' · ')}</p>
      <dl className="trust-facts">
        <div><dt>Maximum allowed notional / USD</dt><dd>{risk.risk.maximum_allowed_notional_usd}</dd></div>
        <div><dt>Proposed synthetic notional / USD</dt><dd>{risk.risk.proposed_notional_usd ?? 'NONE'}</dd></div>
        <div><dt>Proposed synthetic tokens</dt><dd>{risk.risk.proposed_token_quantity ?? 'NONE'}</dd></div>
        <div><dt>Proposed synthetic share exposure</dt><dd>{risk.risk.proposed_share_exposure ?? 'NONE'}</dd></div>
        <div><dt>Stress loss including costs / USD</dt><dd>{risk.risk.stress_loss_usd ?? 'NONE'}</dd></div>
        <div><dt>Slippage tolerance / bps</dt><dd>{risk.risk.slippage_tolerance_bps}</dd></div>
        <div><dt>Liquidity notional cap / USD</dt><dd>{risk.risk.liquidity_notional_cap_usd}</dd></div>
      </dl>
      <p>Stress loss is a scenario estimate, not a guaranteed maximum loss.</p>
      <ul>{risk.risk.checks.map(check => <li key={check.code}>{check.passed ? 'PASS' : 'FAIL'} · {check.code}: {check.detail}</li>)}</ul>
      {opportunity && risk.risk.status === 'PASS' && opportunity.opportunity.status === 'ACTIONABLE' ?
        <DemoPreparationFlow key={risk.risk.risk_id} trust={trust} opportunity={opportunity} risk={risk} opportunityExpired={expired} /> :
        <p>Quote, transaction and simulation not run: no actionable Opportunity with Risk PASS.</p>}
    </>}
    {opportunity && <details><summary>Opportunity / Risk audit contracts</summary><pre>{JSON.stringify({ opportunity, risk }, null, 2)}</pre></details>}
  </section>
}
