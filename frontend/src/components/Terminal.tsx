import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { fetchTerminal } from '../services/terminal'
import type { TerminalResult } from '../services/terminal'
import { StatusBadge } from './StatusBadge'
import { ScorecardAudit } from './ScorecardAudit'

const value = (v: string | null | undefined) => v ?? 'Unavailable'
const money = (v: string | null | undefined) => v === null || v === undefined ? 'Unavailable' : `$${v}`
const reasons = (codes: string[]) => codes.length ? codes.join(' · ') : 'No recorded rejection'
export function Terminal({ mode }: { mode: TerminalResult['data_mode'] }) {
  const [input, setInput] = useState('')
  const [ticker, setTicker] = useState('')
  const [offset, setOffset] = useState(0)
  const [evaluationOpen, setEvaluationOpen] = useState(false)
  const query = useQuery({ queryKey: ['terminal', mode, ticker, offset], queryFn: ({ signal }) => fetchTerminal(mode, ticker, offset, signal), retry: false })
  const data = query.isError || query.isFetching ? null : query.data
  return <section className="terminal" aria-label="Terminal analytics">
    <div className="page-heading"><div><div className="eyebrow">PARITY PULSE / ANALYTICS</div><h1>Terminal</h1><p>Backend-authoritative evidence. Observation only; no trading actions.</p></div><button className="refresh-button" disabled={query.isFetching} onClick={() => { void query.refetch() }}>Refresh Terminal</button></div>
    <div className="connection-alert"><div><strong>{mode === 'DEMO' ? 'SIMULATED DATA — NOT LIVE MARKET DATA' : 'LIVE READ ONLY — CACHED PROVIDER DATA'}</strong><p>NO REAL FUNDS WILL MOVE · Production Trust and live execution remain blocked.</p></div></div>
    <button className="refresh-button" aria-expanded={evaluationOpen} onClick={() => setEvaluationOpen(v => !v)}>Scorecard &amp; audit</button>
    {evaluationOpen && <ScorecardAudit key={mode} mode={mode} />}
    <form className="terminal-filter" onSubmit={e => { e.preventDefault(); setOffset(0); setTicker(input.trim().toUpperCase()) }}>
      <label htmlFor="terminal-ticker">Underlying ticker</label><input id="terminal-ticker" value={input} maxLength={15} placeholder="All cached stocks" onChange={e => setInput(e.target.value)} /><button className="refresh-button">Apply filter</button>
    </form>
    {query.isFetching && <p role="status">Loading Terminal evidence…</p>}
    {query.isError && <div role="alert" className="connection-alert">Terminal unavailable. No fallback values are displayed. Refresh or revise the ticker filter.</div>}
    {data && <>
      <p className="terminal-asof">Snapshot generated {data.generated_at} · {data.data_mode} · Request {data.request_id}</p>
      <p className="terminal-note">{reasons(data.limitations)}. Cached rows are not a live refresh. Missing values stay unavailable.</p>
      <section className="panel"><h2>Issuer spread board / normalized prices</h2><p>Token price, share ratio, independent reference and normalized share cost are supplied by backend services.</p>
        {!data.issuers.items.length ? <p>No cached representations match this filter.</p> : <div className="terminal-table-wrap"><table><thead><tr>{['Stock / issuer','Token / ratio','Token price','Effective $/share','Independent equity','Spread / deviation','Liquidity','Trust / market','Evidence'].map(h => <th key={h}>{h}</th>)}</tr></thead><tbody>{data.issuers.items.map(row => <tr key={`${row.ticker}:${row.chain_id}:${row.contract}`}>
          <td><strong>{row.ticker}</strong><small>{row.company}</small>{row.issuer}<small>{row.chain_id} · {row.contract}</small></td>
          <td>{row.token}<small>{row.token_to_share_ratio} shares/token</small><small>Ratio observed {row.ratio_observed_at}</small><small>Source as-of {value(row.ratio_source_timestamp)}</small></td>
          <td>{money(row.token_price_usd)}</td><td>{money(row.effective_price_per_share_usd)}</td><td>{money(row.independent_equity_price_usd)}<small>{row.reference.status}</small><small>{value(row.reference.reference_asof)}</small></td>
          <td>{money(row.spread_usd_per_share)}<small>{row.deviation_percent === null ? 'Unavailable' : `${row.deviation_percent}%`}</small><small>Skew {value(row.reference.timestamp_skew_seconds)} seconds</small></td>
          <td>{money(row.liquidity.liquidity_usd)}<small>{row.liquidity.status}</small><small>24h USD volume {money(row.liquidity.volume_24h_usd)}</small></td>
          <td>{row.trust.classification}<small>{row.market_state} / {row.regime}</small><small>Tradable: {row.tradable === null ? 'Unknown' : row.tradable ? 'Yes' : 'No'}</small><small>{row.route_status}</small></td>
          <td><StatusBadge tone={row.freshness === 'FRESH' ? 'green' : 'amber'}>{row.freshness}</StatusBadge><small>{row.eligibility}</small><details><summary>Sources and reasons</summary><p>{reasons(row.reasons)}</p>{row.observations.map((o,i) => <p key={i}>{o.source} · {o.data_quality}<br />Observed {value(o.observed_at)}<br />Available {o.available_at}<br />{o.provider_identifier}<br /><code>{o.digest}</code></p>)}</details></td>
        </tr>)}</tbody></table></div>}
      </section>
      <section className="panel"><h2>Trust monitor</h2><p>Existing deterministic Trust assessments. Stale classifications are retained only as labeled historical evidence.</p>
        {!data.trust.items.length && <p>No persisted Trust evidence for cached representations.</p>}
        {data.trust.items.map((row,i) => <article className="terminal-record" key={i}><strong>{row.ticker} · {value(row.issuer)}</strong><StatusBadge tone="amber">{row.classification}</StatusBadge><p>Confidence {value(row.confidence)} · {row.freshness} · Assessed {value(row.assessed_at)} · Age {value(row.age_seconds)} seconds · Regime {value(row.regime)}</p>
          {row.stored_evidence && <p>Stored classification: {row.stored_evidence.classification}. News: {row.stored_evidence.news.state} / {row.stored_evidence.news.coverage}. Baseline: {row.stored_evidence.baseline.sample_count} ({row.stored_evidence.baseline.status}). Analogues: {row.stored_evidence.analogues.retrieved_sample_count} ({row.stored_evidence.analogues.status}).</p>}
          <p>{reasons(row.reasons)}</p></article>)}
      </section>
      <section className="panel"><h2>Agent evidence</h2><p>Structured persisted outputs and references. Agents do not authorize execution.</p>
        {!data.agents.items.length && <p>No persisted agent runs. The Terminal does not invoke agents to fill this view.</p>}
        {data.agents.items.map(run => <article className="terminal-record" key={run.run_id}><strong>{run.status} · {run.decision.decision}</strong><p>{run.timestamp} · Run {run.run_id}</p><p>{reasons(run.decision.reasons)}</p>
          {run.agents.map(a => <details key={a.agent}><summary>{a.agent} · {a.status} · {a.confidence}</summary><p>{a.provider} / {a.model}</p><p>Evidence: {a.evidence_refs.join(', ') || 'Unavailable'}</p><p>Conflicts: {reasons(a.conflicts)}</p><p>{reasons(a.reasons)}</p><pre>{JSON.stringify(a.output, null, 2)}</pre></details>)}
          <details><summary>Evidence provenance and retrieved memory</summary>{run.evidence.map(e => <p key={e.evidence_id}>{e.evidence_id} · {e.source} · Observed {e.observed_at} · Available {e.available_at}<br /><code>{e.digest}</code></p>)}{run.memory.map(m => <p key={m.memory_id}>{m.stock} · {m.memory_id} · {m.trust_state} · {m.action}</p>)}</details></article>)}
      </section>
      <section className="panel"><h2>Execution analytics</h2><p>Proposals, simulation and confirmed settlement remain distinct. Quoted units do not establish ownership.</p>
        {!data.executions.items.length && <p>No persisted execution attempts.</p>}
        {data.executions.items.map(row => <article className="terminal-record" key={row.execution_id}><strong>{row.category} · {row.lifecycle_state}</strong><p>{row.synthetic ? 'SYNTHETIC FIXTURE — NOT A REAL TRADE' : row.source} · Actual completed trade: {row.actual_completed_trade ? 'Yes' : 'No'}</p><p>{row.execution_id} · Updated {row.updated_at}</p><p>Provider {value(row.provider)} · {value(row.execution_mode)} · Quote {value(row.quote_id)} · Simulation {value(row.simulation_status)}</p><p>Requested sell-token base units {value(row.requested_base_units)} · Quoted output {value(row.quoted_output_base_units)} · Filled {value(row.filled_base_units)} · Remaining {value(row.remaining_base_units)}</p><p>Estimated network fee {money(row.network_fee_estimate_usd)} · Actual fee native units {value(row.actual_fees_native_base_units)} · Gas provider units {value(row.estimated_gas_provider_units)} · Recorded quote latency {value(row.quote_latency_seconds)} seconds</p><p>Position {value(row.position_id)} / {value(row.position_state)} · Realized gross P&amp;L {money(row.realized_gross_pnl_usd)} · Realized net P&amp;L {money(row.realized_net_pnl_usd)}</p><details><summary>Fingerprint / reasons</summary><code>{value(row.fingerprint)}</code><p>{reasons(row.reasons)}</p></details></article>)}
      </section>
      <section className="panel"><h2>Historical episodes</h2><p>Decision-time inputs are separate from later opening outcomes. Replay provenance is retained.</p>
        {!data.episodes.items.length && <p>No mode-scoped replay episodes match this filter.</p>}
        {data.episodes.items.map(row => <article className="terminal-record" key={`${row.run_id}:${row.episode_id}`}><strong>{row.ticker} / {row.issuer} · {row.evidence_kind}</strong><p>{row.decision_at} · {row.regime} · {row.eligibility} · {row.trust_state}</p><p>Deviation fraction {value(row.deviation)} · USD volume {money(row.volume_usd)} · USD liquidity {money(row.liquidity_usd)}</p><p>Prediction {row.prediction.status} · Return fraction {value(row.prediction.predicted_return)} · Samples {row.prediction.sample_count}</p><p>Analogues {row.retrieval.status} · Retrieved {row.retrieval.retrieved_count}</p><p>Opening outcome {row.outcome_state} · Return fraction {value(row.opening_outcome?.opening_return)} · Outcome available {value(row.opening_outcome?.available_at)}</p><details><summary>Replay identity / reasons / provenance</summary><p>Run {row.run_id} · Episode {row.episode_id}<br />Dataset {row.dataset_digest}<br />Query as-of {row.query_as_of}</p><p>{reasons(row.reasons)}</p>{row.retrieval.matches.map(m => <p key={m.episode_id}>Analogue {m.episode_id}</p>)}{row.provenance.map((p,i) => <p key={i}>{p.source} · Available {p.available_at}</p>)}</details></article>)}
      </section>
      <section className="panel"><h2>Portfolio / Autopilot context</h2><p>{data.portfolio.status} · Configuration version {data.portfolio.config_version ?? 'Unavailable'} · Pending plan {value(data.portfolio.pending_plan_id)}</p><p>{reasons(data.portfolio.reasons)}</p></section>
      <div className="terminal-filter"><button className="refresh-button" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - 25))}>Previous records</button><span>Record offset {offset}</span><button className="refresh-button" disabled={!['issuers','trust','agents','executions','episodes'].some(k => data[k as 'issuers'].has_more)} onClick={() => setOffset(offset + 25)}>Next records</button></div>
    </>}
  </section>
}
