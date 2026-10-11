import { ReadRefresh } from '../ui/ReadRefresh'
import { Button } from '../ui/Button'
import { DataContext } from './DataContext'
import { readRefresh } from '../hooks/readRefresh'
import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { fetchEvaluation } from '../services/scorecard'
import type { Scorecards, Trace } from '../services/scorecard'
import { StatusBadge } from './StatusBadge'

const value = (v: string | null | undefined) => v ?? 'Unavailable'
const money = (v: string | null | undefined) => v == null ? 'Unavailable' : `$${v}`
const codes = (v: string[]) => v.join(' · ') || 'No recorded reason'
export function ScorecardAudit({ mode, initialDecision }: { initialDecision?: string; mode: Scorecards['data_mode'] }) {
  const [kind, setKind] = useState(''), [ticker, setTicker] = useState(''), [outcome, setOutcome] = useState('')
  const [filter, setFilter] = useState(''), [offset, setOffset] = useState(0), [decision, setDecision] = useState(initialDecision ?? '')
  const params = new URLSearchParams(filter); params.set('limit', '25'); params.set('offset', String(offset))
  const query = useQuery({ queryKey: ['scorecard', mode, filter, offset], queryFn: ({ signal }) => fetchEvaluation<Scorecards>(mode, params, signal), ...readRefresh })
  const trace = useQuery({ queryKey: ['audit', mode, decision], queryFn: ({ signal }) => fetchEvaluation<Trace>(mode, new URLSearchParams(), signal, decision), enabled: !!decision, ...readRefresh })
  const data = query.isError || query.isFetching ? null : query.data
  const trail = trace.isError || trace.isFetching ? null : trace.data
  return <section className="panel scorecard-audit" aria-label="Scorecard and audit">
    <h2>Scorecard &amp; audit</h2><p>Persisted backend evaluations. Policy consistency, prediction quality and settlement evidence stay separate.</p>
    <DataContext mode={mode} />
    <form className="terminal-filter" onSubmit={e => { e.preventDefault(); setOffset(0); setDecision(''); setFilter(new URLSearchParams({ ...(kind ? { scorecard_type: kind } : {}), ...(ticker ? { ticker: ticker.trim().toUpperCase() } : {}), ...(outcome ? { outcome } : {}) }).toString()) }}>
      <label>Evaluation type <select value={kind} onChange={e => setKind(e.target.value)}><option value="">All types</option>{['OPPORTUNITY','DIRECT_EXPOSURE','AUTOPILOT'].map(k => <option key={k}>{k}</option>)}</select></label>
      <label>Scorecard ticker <input value={ticker} maxLength={15} onChange={e => setTicker(e.target.value)} /></label>
      <label>Outcome <select value={outcome} onChange={e => setOutcome(e.target.value)}><option value="">All outcomes</option>{['PROPOSED','REJECTED','DEFERRED','BLOCKED','SIMULATED','CONFIRMED','UNKNOWN','RECONCILIATION_REQUIRED','PAPER_FILLED','PAPER_EXITED','COMPLETED','NO_ACTION'].map(o => <option key={o}>{o}</option>)}</select></label>
      <Button className="refresh-button">Filter evaluations</Button>
    </form>
    <ReadRefresh refetch={query.refetch} busy={query.isFetching} beforeRead={()=>setDecision('')}>Refresh evaluations</ReadRefresh>
    {query.isFetching && <p role="status">Loading scorecards…</p>}
    {query.isError && <p role="alert">Scorecard unavailable. No fallback or cached outcome is displayed.</p>}
    {data && <>
      <p>Evaluated snapshot {data.generated_at}. Historical decision timestamps are shown separately; this is not a live market refresh.</p>
      <p>{codes(data.page.reasons)} · {codes(data.limitations)}</p>
      <p>Evaluations {data.metrics.decision_count} · Direction samples {data.metrics.directional_samples} · Direction accuracy fraction {value(data.metrics.directional_accuracy)} · High-confidence accuracy fraction {value(data.metrics.high_confidence_accuracy)}. Statistical validation: {data.metrics.statistical_validation}.</p>
      {!data.page.items.length && <p>No completed decision records match this filter.</p>}
      {data.page.items.map(c => <article className="terminal-record" key={c.evaluation_id}>
        <strong>{c.scorecard_type} · {value(c.ticker)} / {value(c.selected_issuer)}</strong><StatusBadge tone={c.abstained ? 'amber' : 'green'}>{c.outcome}</StatusBadge>
        <p>{c.synthetic ? 'SYNTHETIC EVALUATION — NOT A REAL TRADE' : c.origin} · {c.action} · {c.control_quality}</p>
        <p>Policy basis: {c.control_quality_basis}. Composite score unavailable: {c.score_reason}.</p>
        <p>Decision {c.decision_at} · Evidence as-of {c.evidence_asof} · Recorded {c.recorded_at}</p>
        <p>Abstention: {c.abstained ? 'Yes' : 'No'} · Scope {c.abstention_scope} · {codes(c.abstention_reasons)}</p><p>{codes(c.reasons)}</p>
        <p>Trust {value(c.trust_classification)} · Confidence {value(c.confidence)} · Requested exposure {money(c.requested_exposure_usd)} · Estimated shares {value(c.estimated_share_exposure)}</p>
        <p>Predicted {value(c.prediction.predicted_direction)} / {value(c.prediction.predicted_return)} · Actual {value(c.prediction.actual_direction)} / {value(c.prediction.actual_opening_return)} · Direction correct {c.prediction.direction_correct === null ? 'Unknown' : c.prediction.direction_correct ? 'Yes' : 'No'}</p>
        <p>Classification correctness unavailable: {c.prediction.label_status}. Noise suppression recorded: {c.prediction.noise_suppressed ? 'Yes' : 'No'}; outcome correctness unknown.</p>
        <details><summary>Route cost efficiency</summary><p>Recorded ranking basis {c.route.basis} · Selected {money(c.route.selected_cost_per_share_usd)} per share · Minimum eligible {money(c.route.minimum_eligible_cost_per_share_usd)} · Excess {money(c.route.excess_cost_per_share_usd)}</p><p>Token price {money(c.route.token_price_usd)} · Shares/token {value(c.route.shares_per_token)} · Normalized cost {money(c.route.effective_cost_per_share_usd)} per share</p><p>Liquidity {c.route.liquidity_state} / {money(c.route.liquidity_usd)} · Source {value(c.route.liquidity_source)} · Trust {value(c.route.trust_state)} · Tradability {value(c.route.tradability)}</p><p>Estimated cost {money(c.route.estimated_costs_usd)} · Fees {money(c.route.estimated_fees_usd)} · Gas {money(c.route.estimated_gas_usd)} · Slippage {value(c.route.estimated_slippage_bps)} bps</p><p>Actual total USD cost {money(c.route.actual_total_cost_usd)} · Simulated USD cost {money(c.route.simulated_cost_usd)} · Actual native fee units {value(c.route.actual_fees_native_base_units)}</p><p>Provider {value(c.route.provider)} · Quote {value(c.route.provider_quote_id)}</p>{Object.entries(c.route.alternative_costs_per_share_usd).map(([id,cost]) => <p key={id}>{id}: {money(cost)} per share</p>)}</details>
        {!c.executions.length ? <p>No execution evidence. A proposal, local simulation or paper fill does not establish a real investment outcome.</p> : c.executions.map(e => <p key={e.execution_id}>{e.category} / {e.lifecycle_state} · Actual completed trade: {e.actual_completed_trade ? 'Yes' : 'No'} · Filled {value(e.filled_base_units)} · Remaining {value(e.remaining_base_units)} · Position {value(e.position_state)} · {codes(e.reasons)}</p>)}
        {c.paper_pnl && <details><summary>Existing illustrative paper accounting</summary><pre>{JSON.stringify(c.paper_pnl, null, 2)}</pre></details>}
        {!!c.allocations.length && <details><summary>Autopilot allocation / drift / proposed actions</summary><pre>{JSON.stringify({ allocations: c.allocations, proposed_actions: c.proposed_actions }, null, 2)}</pre></details>}
        <p>Decision reference {c.decision_id}</p><Button className="refresh-button" onClick={() => { setDecision(c.decision_id); if (decision === c.decision_id) void trace.refetch() }}>Trace decision {c.decision_id}</Button>
      </article>)}
      <div className="terminal-filter"><Button className="refresh-button" disabled={!offset} onClick={() => { setDecision(''); setOffset(Math.max(0, offset - 25)) }}>Previous evaluations</Button><span>Evaluation offset {offset}</span><Button className="refresh-button" disabled={!data.page.has_more} onClick={() => { setDecision(''); setOffset(offset + 25) }}>Next evaluations</Button></div>
    </>}
    {decision && <section className="decision-audit" aria-label="Decision audit trace"><h3>Decision audit trace</h3>
      {trace.isFetching && <p role="status">Loading decision trace…</p>}
      {trace.isError && <p role="alert">Audit trace unavailable. No prior trace is shown.</p>}
      {trail && <><p>Decision {trail.decision_id} · Complete for recorded scope: {trail.complete_for_recorded_scope ? 'Yes' : 'No'}</p><p>{codes(trail.limitations)}</p><p>Source projections reference original journal records; they are not new provider or execution operations.</p>
        <div className="terminal-table-wrap"><table><thead><tr><th>Stage</th><th>Evidence</th></tr></thead><tbody>{trail.stages.map(s => <tr key={s.stage}><td>{s.stage}</td><td>{s.status}</td></tr>)}</tbody></table></div>
        {trail.events.map(e => <details key={e.event_id}><summary>{e.timestamp} · {e.event_type} · {e.status}</summary><p>Actor {e.actor} · Source {e.source} · Captured {e.recorded_at}</p><p>Correlation {value(e.correlation_id)} · Execution {value(e.execution_id)}</p><p>{codes(e.reasons)}</p><pre>{JSON.stringify({ inputs: e.input_summary, outputs: e.output_summary }, null, 2)}</pre><code>{e.source_digest}</code></details>)}
      </>}
    </section>}
  </section>
}
