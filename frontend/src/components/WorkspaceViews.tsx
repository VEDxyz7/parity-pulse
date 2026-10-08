import { useQuery } from '@tanstack/react-query'
import { getWorkspace, getAudit, readRefresh, type Mode, type WorkspaceState } from '../services/workspace'
import { useEffect, useRef, useState } from 'react'
import { configurePortfolio, proposeDrift, type ConfigRequest } from '../services/workspace'
import { ApiError } from '../services/api'
import { RouteComparison } from './RouteComparison'
import type { RouteDecision } from '../services/routing'
import { parseRoute } from '../services/routing'
const value = (v: string | null | undefined) => v ?? 'Unavailable'
export function useWorkspace(mode: Mode) {
  return useQuery({ queryKey: ['workspace', mode], queryFn: ({ signal }) => getWorkspace(mode, signal), ...readRefresh })
}
function Inspection({ mode, children }: { mode: Mode; children: (data: WorkspaceState) => React.ReactNode }) {
  const query = useWorkspace(mode)
  return <>
    <button className="refresh-button" disabled={query.isFetching} onClick={() => void query.refetch()}>Refresh workspace state</button>
    {query.isFetching && <p role="status">Loading authoritative workspace state…</p>}
    {query.isError && <p role="alert">Workspace unavailable. Holdings, wallet and financial values remain unknown. No cached healthy result is substituted.</p>}
    {!query.isError && !query.isFetching && query.data && <><p>Observed <time>{query.data.generated_at}</time> · {query.data.data_mode} · {query.data.source}</p>{children(query.data)}</>}
  </>
}
export function SafetyNotice({ mode }: { mode: Mode }) {
  return <p className="mode-notice"><strong>{mode === 'DEMO' ? 'SIMULATED DATA — NOT LIVE MARKET DATA' : 'LIVE READ ONLY — PROVIDER DATA MAY BE UNAVAILABLE'}</strong><br />DRY_RUN · PROPOSE_ONLY · NO REAL FUNDS WILL MOVE</p>
}
export function PortfolioView({ mode, autopilot = false }: { mode: Mode; autopilot?: boolean }) {
  const workspace = useWorkspace(mode)
  return <section className="workspace-view" aria-label={autopilot ? 'Autopilot status' : 'Portfolio state'}>
    <h1>{autopilot ? 'Autopilot' : 'Portfolio'}</h1><SafetyNotice mode={mode} />
    <p>Backend-computed allocation, drift and positions. A saved mandate or rebalance proposal does not authorize execution.</p>
    <Inspection mode={mode}>{data => {
      const state = data.portfolio, plan = state.pending_plan ?? state.latest_decision
      return <>
        <section className="panel"><h2>Portfolio configuration</h2>{state.config ? <><p>Version {state.config.version} · Updated {state.config.updated_at} · Funding asset: {state.config.funding_symbol} (USD notional is separate)</p><div className="comparison-scroll" tabIndex={0} role="region" aria-label="Target allocations"><table><caption>Backend target allocation</caption><thead><tr><th>Asset</th><th>Kind</th><th>Target fraction</th><th>Drift band fraction</th></tr></thead><tbody>{state.config.targets.map(t => <tr key={t.asset}><td>{t.asset}</td><td>{t.kind}</td><td>{t.weight}</td><td>{t.drift_band}</td></tr>)}</tbody></table></div><p>Risk budget: {state.config.risk_budget_usd} USD · Rebalance cap: {state.config.max_rebalance_notional_usd} USD · Stock exposure cap: {state.config.max_stock_exposure_usd} USD · Maximum drift fraction: {state.config.max_drift} · Crypto enabled: {String(state.config.crypto_enabled)}</p></> : <p>No portfolio mandate is configured. Current allocation and total value are unavailable.</p>}</section>
        <section className="panel"><h2>{plan ? `Rebalance: ${plan.status}` : 'No rebalance decision'}</h2><p>Recovery: {state.recovery_complete ? 'Complete' : 'RECONCILIATION_REQUIRED'} · Active position coverage: {state.position_coverage_complete ? 'Complete within 100 records' : 'INCOMPLETE'}</p>
          {plan ? <><p>Total value at original capture: {value(plan.total_value_usd)} USD · Captured {plan.captured_at} · Updated {plan.updated_at}</p><p>This is a historical planning snapshot, not a current market valuation.</p><p>{plan.reasons.join(' · ')}</p><div className="comparison-scroll" tabIndex={0} role="region" aria-label="Allocation and drift"><table><caption>Backend allocation / drift snapshot</caption><thead><tr><th>Asset</th><th>Current value / USD</th><th>Current fraction</th><th>Target fraction</th><th>Drift</th><th>Band</th><th>Status</th></tr></thead><tbody>{plan.rows.map(r => <tr key={r.asset}><td>{r.asset}</td><td>{value(r.current_value_usd)}</td><td>{value(r.current_weight)}</td><td>{r.target_weight}</td><td>{value(r.drift)}</td><td>{r.allowed_band}</td><td>{r.state}: {r.reasons.join(' · ')}</td></tr>)}</tbody></table></div>
          <p>Funding at capture: {plan.funding ? `${plan.funding.asset.symbol} · available base units ${plan.funding.balance_base_units} · source ${plan.funding.source}` : 'Unavailable; wallet balance is not assumed USD'}</p>
          {plan.actions.map(action => <article key={action.action_id}><h3>{action.side} {action.asset} — proposal only</h3><p>Notional {action.notional_usd} USD · Tokens {action.quantity_base_units} base units · Share delta {action.estimated_share_delta}</p><p>Risk: {action.risk.status} · {action.reasons.join(' · ')}</p><details><summary>Rebalance route</summary><RouteComparison route={parseRoute(action.route, mode === 'DEMO' ? 'DEMO' : 'LIVE', action.asset, undefined, action.route.policy.purpose) as RouteDecision} expired /></details></article>)}
          <p>Preparation records: {plan.preparations.length}. Public approval and live execution are unavailable.</p><a className="refresh-button" href={`#audit/${encodeURIComponent(plan.plan_id)}`}>Inspect rebalance audit</a></> : <p>No pending rebalance or historical plan. No value or drift has been invented.</p>}
        </section>
        <section className="panel"><h2>Persistent positions</h2><p>Recent 100 records · History coverage {data.position_history_complete ? 'complete' : 'incomplete'} · UNKNOWN / RECONCILIATION_REQUIRED positions are unresolved, not owned holdings.</p>{!data.positions.length && <p>No persisted positions in this data mode.</p>}
          {data.positions.map(p => <article key={p.position_id} className="terminal-record"><h3>{p.instrument.ticker} / {p.instrument.issuer} · {p.state}</h3><p>Filled {p.filled_quantity_base_units} base units · Remaining {p.remaining_quantity_base_units} base units · {['UNKNOWN','RECONCILIATION_REQUIRED','FAILED','OPENING','PROPOSED'].includes(p.state) ? 'UNRESOLVED — no ownership confirmed' : `Backend share exposure ${p.normalized_share_exposure}`}</p><p>Effective cost/share: {value(p.effective_cost_per_share_usd)} USD · Gross P/L {value(p.gross_pnl_usd)} USD · Net P/L {value(p.net_pnl_usd)} USD</p><p>Updated {p.updated_at} · {p.reasons.join(' · ')}</p><code>{p.position_id}</code></article>)}
        </section>
      </>
    }}</Inspection>
    {autopilot && <MandateControls mode={mode} version={workspace.data?.portfolio.config?.version ?? 0} unavailable={workspace.isFetching || workspace.isError || !workspace.data} />}
  </section>
}
function MandateControls({ mode, version, unavailable }: { mode: Mode; version: number; unavailable: boolean }) {
  const query = useWorkspace(mode)
  const [ticker, setTicker] = useState(''), [weight, setWeight] = useState(''), [cash, setCash] = useState(''), [band, setBand] = useState('')
  const [cap, setCap] = useState(''), [risk, setRisk] = useState(''), [exposure, setExposure] = useState('')
  const [busy, setBusy] = useState(false), [message, setMessage] = useState('')
  const pending = useRef(false), key = useRef<string | null>(null)
  const signal = useRef<AbortController | null>(null)
  useEffect(() => () => signal.current?.abort(), [])
  // Local inputs describe a reviewed mandate, never current holdings or inferred risk.
  async function submit(event?: React.FormEvent) {
    event?.preventDefault(); if (pending.current || unavailable) return
    pending.current = true; setBusy(true); setMessage('')
    const controller = new AbortController(); signal.current = controller
    try {
      if (event) {
        const body: ConfigRequest = { targets: [{ asset: ticker.trim().toUpperCase(), kind: 'TOKENIZED_STOCK', weight, drift_band: band }, { asset: 'CASH', kind: 'CASH', weight: cash, drift_band: band }], funding_symbol: 'USDT', max_rebalance_notional_usd: cap, risk_budget_usd: risk, max_stock_exposure_usd: exposure, expected_version: version }
        await configurePortfolio(body, controller.signal)
        if (controller.signal.aborted) return
        setMessage('Mandate saved by backend. No order or wallet setting changed.'); key.current = null
      } else {
        key.current ??= crypto.randomUUID()
        const plan = await proposeDrift(key.current, mode, controller.signal)
        if (controller.signal.aborted) return
        setMessage(`Backend rebalance decision: ${plan.status} · ${plan.reasons.join(' · ')}. No execution.`)
      }
      await query.refetch()
    } catch (error) { if (!controller.signal.aborted) setMessage(error instanceof ApiError ? error.message + ' Retain the same planning key after uncertainty; a configuration conflict requires a refreshed version.' : 'Invalid mandate or response. Backend values were not substituted.') }
    finally { pending.current = false; if (!controller.signal.aborted) setBusy(false) }
  }
  return <section className="panel"><h2>Reviewed non-executable mandate</h2><p>Weights and drift bands are fractions. Backend validates the exact total and platform limits. Risk budget is ex-ante and does not guarantee maximum realized loss.</p>
    <form className="workspace-form" onSubmit={e => void submit(e)}>{[["Stock ticker",ticker,setTicker],["Stock target fraction",weight,setWeight],["Cash target fraction",cash,setCash],["Drift band fraction",band,setBand],["Rebalance cap USD",cap,setCap],["Risk budget USD",risk,setRisk],["Stock exposure cap USD",exposure,setExposure]].map(([label,input,setter]) => <label key={String(label)}>{String(label)}<input required autoComplete="off" maxLength={60} disabled={busy || unavailable} value={String(input)} onChange={e => (setter as (v:string)=>void)(e.target.value)} /></label>)}<button className="refresh-button" disabled={busy || unavailable}>Save reviewed mandate</button></form>
    <button className="refresh-button" disabled={busy || unavailable || version === 0} onClick={() => void submit()}>Evaluate drift proposal</button>
    <p>Retries and repeat reads retain the same planning identity until a new reviewed mandate is saved. Refreshing state never submits an action.</p>
    {message && <p role="status">{message}</p>}
  </section>
}
export function SystemView({ mode }: { mode: Mode }) {
  return <section className="workspace-view" aria-label="Settings and system health"><h1>Settings / System Health</h1><SafetyNotice mode={mode} /><Inspection mode={mode}>{data => <>
    <section className="panel"><h2>Wallet status</h2><p>{data.wallet.status} · Connection: {data.wallet.connection}</p><p>Address: {data.wallet.address ?? 'Unavailable'} · Balance: {data.wallet.balance ?? 'Unavailable'}</p><p>{data.wallet.reasons.join(' · ')} · Source {data.wallet.source}. The public API does not operate an authenticated wallet worker.</p></section>
    <section className="panel"><h2>Safety and capability gates</h2><dl className="ask-details">{Object.entries(data.production_gates??{}).map(([name,status]) => <div key={name}><dt>{name}</dt><dd>{status}</dd></div>)}</dl><p>Routing: {data.routing_status}</p><p>Simulation: {data.simulation_status}</p><p>Approval: {data.approval_status}</p><p>LIVE_BLOCKED · Execution ready: {String(data.execution_ready)} · Simulation required: {String(data.require_simulation)}</p><p>Provider entitlements and current observations are inspectable in Terminal; no provider refresh is triggered by this page.</p><a href="#terminal" className="refresh-button">Inspect provider evidence</a></section>
  </>}</Inspection></section>
}
export function AuditEvents({ mode }: { mode: Mode }) {
  const [offset,setOffset]=useState(0)
  const query=useQuery({queryKey:['audit-events',mode,offset],queryFn:({signal})=>getAudit(mode,offset,signal),...readRefresh})
  const data=query.isError||query.isFetching?null:query.data
  return <section className="panel"><h2>Audit events</h2><button className="refresh-button" disabled={query.isFetching} onClick={()=>void query.refetch()}>Refresh audit events</button>{query.isFetching&&<p role="status">Loading audit events…</p>}{query.isError&&<p role="alert">Audit events unavailable; no prior events substituted.</p>}{data&&<><p>As of {data.generated_at} · Recorded backend evidence</p>{!data.page.items.length&&<p>No recorded audit events in this scope.</p>}{data.page.items.map(e=><details key={e.event_id}><summary>{e.timestamp} · {e.event_type} · {e.status}</summary><p>{e.capture_kind} · {e.source} · {(e.reasons??[]).join(' · ')}</p><p>Correlation {e.correlation_id??'Unavailable'} · Decision {e.decision_id}</p><a className="refresh-button" href={`#audit/${encodeURIComponent(e.decision_id)}`}>Inspect decision trace</a></details>)}<div className="terminal-filter"><button disabled={!offset} className="refresh-button" onClick={()=>setOffset(Math.max(0,offset-25))}>Previous events</button><span>Event offset {offset}</span><button disabled={!data.page.has_more} className="refresh-button" onClick={()=>setOffset(offset+25)}>Next events</button></div></>}</section>
}
