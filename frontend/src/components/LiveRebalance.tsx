import { useEffect, useState } from 'react'
import { apiRequest, ApiError } from '../services/api'

type Status = { wallet: string; signer: string | null; live_execution: boolean; max_notional_usd: string; max_slippage_bps: string; trust_required: boolean; equity_reference: string }
type Representation = { issuer: string; token: string; contract: string; token_price_usd: string; shares_per_token: string; price_per_share_usd: string; deviation_bps: string; market_state: string }
type Parity = { ticker: string; equity_reference_usd: string; equity_observed_at: string; representations: Representation[] }
type Action = { action_id: string; side: string; asset: string; notional_usd: string; eligible_for_preparation: boolean; reasons: string[]; route: { selected_representation: { token: string } | null } }
type Row = { asset: string; current_value_usd: string | null; target_value_usd: string | null; current_weight: string | null; target_weight: string; state: string }
type Plan = { plan_id: string; status: string; reasons: string[]; total_value_usd: string | null; rows: Row[]; actions: Action[] }
type Leg = { action_id: string; side: string; asset: string; token: string; status: string; notional_usd: string; approve_tx: string | null; swap_tx: string | null; reasons: string[]; realized_cost_usd: string | null; evidence: Record<string, string | null> }

const object = (value: unknown) => { if (!value || typeof value !== 'object') throw new Error('invalid'); return value }
const parse = <T,>(value: unknown) => object(value) as T
const parseList = <T,>(value: unknown) => { if (!Array.isArray(value)) throw new Error('invalid'); return value as T[] }
const money = (v: string | null | undefined) => v == null ? '—' : Number(v).toLocaleString(undefined, { style: 'currency', currency: 'USD', maximumFractionDigits: 2 })
const scan = (hash: string | null) => hash ? <a href={`https://bscscan.com/tx/${hash}`} target="_blank" rel="noreferrer">{hash.slice(0, 10)}…</a> : '—'
const message = (error: unknown) => error instanceof ApiError ? error.message : 'Request failed. No fallback data was substituted.'

export function LiveRebalance() {
  const [status, setStatus] = useState<Status | null>(null)
  const [ticker, setTicker] = useState('NVDA')
  const [parity, setParity] = useState<Parity | null>(null)
  const [plan, setPlan] = useState<Plan | null>(null)
  const [legs, setLegs] = useState<Leg[]>([])
  const [busy, setBusy] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const run = async (label: string, work: (signal: AbortSignal) => Promise<void>) => {
    setBusy(label); setError(null)
    const controller = new AbortController()
    try { await work(controller.signal) } catch (e) { if (!(e instanceof DOMException)) setError(message(e)) } finally { setBusy(null) }
  }
  const refreshFills = (signal: AbortSignal) => apiRequest('/api/live/fills', parseList<Leg>, { signal }).then(setLegs)
  useEffect(() => {
    const controller = new AbortController()
    apiRequest('/api/live/status', parse<Status>, { signal: controller.signal }).then(setStatus).catch(e => { if (!(e instanceof DOMException)) setError(message(e)) })
    refreshFills(controller.signal).catch(() => undefined)
    return () => controller.abort()
  }, [])

  return <section className="workspace-view" aria-label="Live wallet rebalance">
    <h1>Live rebalance</h1>
    <section className="panel">
      <h2>Wallet</h2>
      {status ? <>
        <p><strong>{status.live_execution ? 'LIVE EXECUTION ENABLED — real BSC mainnet transactions' : 'Read-only wallet planning — no transactions are sent'}</strong></p>
        <p>Wallet <a href={`https://bscscan.com/address/${status.wallet}`} target="_blank" rel="noreferrer"><code>{status.wallet}</code></a> · Signer: {status.signer ?? 'none'} · Per-trade cap {money(status.max_notional_usd)} · Slippage cap {status.max_slippage_bps} bps · Trust: {status.trust_required ? 'required' : 'not evaluated (classifier parked)'} · Equity reference: {status.equity_reference}</p>
      </> : <p role="status">{error ?? 'Loading wallet status…'}</p>}
    </section>

    <section className="panel">
      <h2>Parity: token price per share vs equity index</h2>
      <form onSubmit={event => { event.preventDefault(); void run('parity', signal => apiRequest(`/api/live/parity/${ticker}`, parse<Parity>, { signal, timeout: 20000 }).then(setParity)) }}>
        <label>Ticker <input value={ticker} maxLength={15} onChange={e => setTicker(e.target.value.toUpperCase().replace(/[^A-Z0-9]/g, ''))} /></label>
        <button className="refresh-button" disabled={busy !== null || !ticker}>Check parity</button>
      </form>
      {parity && <div className="comparison-scroll" tabIndex={0} role="region" aria-label="Parity table"><table>
        <caption>{parity.ticker} equity index {money(parity.equity_reference_usd)} at {parity.equity_observed_at}</caption>
        <thead><tr><th>Issuer</th><th>Token</th><th>Token price</th><th>Shares/token</th><th>Price per share</th><th>Deviation (bps)</th><th>Market</th></tr></thead>
        <tbody>{parity.representations.map(r => <tr key={r.contract}><td>{r.issuer}</td><td>{r.token}</td><td>{money(r.token_price_usd)}</td><td>{Number(r.shares_per_token).toFixed(6)}</td><td>{money(r.price_per_share_usd)}</td><td>{r.deviation_bps}</td><td>{r.market_state}</td></tr>)}</tbody>
      </table></div>}
    </section>

    <section className="panel">
      <h2>Drift plan</h2>
      <p>Configure targets on the <a href="#autopilot">Autopilot</a> page. Plans read on-chain balances and fresh Binance quotes; every action is risk-checked and capped.</p>
      <button className="refresh-button" disabled={busy !== null} onClick={() => void run('plan', signal => apiRequest('/api/portfolio/plans', parse<Plan>, { signal, body: { idempotency_key: crypto.randomUUID() }, timeout: 60000 }).then(setPlan))}>{busy === 'plan' ? 'Planning…' : 'Evaluate drift now'}</button>
      {plan && <>
        <p>Status <strong>{plan.status}</strong> · Portfolio value {money(plan.total_value_usd)} · {plan.reasons.join(', ')}</p>
        <div className="comparison-scroll" tabIndex={0} role="region" aria-label="Drift rows"><table><thead><tr><th>Asset</th><th>Current</th><th>Target</th><th>Weight</th><th>Target weight</th><th>State</th></tr></thead>
          <tbody>{plan.rows.map(r => <tr key={r.asset}><td>{r.asset}</td><td>{money(r.current_value_usd)}</td><td>{money(r.target_value_usd)}</td><td>{r.current_weight ? (Number(r.current_weight) * 100).toFixed(2) + '%' : '—'}</td><td>{(Number(r.target_weight) * 100).toFixed(2)}%</td><td>{r.state}</td></tr>)}</tbody></table></div>
        {plan.actions.length > 0 && <ul>{plan.actions.map(a => <li key={a.action_id}>{a.side} {money(a.notional_usd)} {a.asset} via {a.route.selected_representation?.token ?? '—'} · {a.eligible_for_preparation ? 'risk approved' : 'blocked: ' + a.reasons.join(', ')}</li>)}</ul>}
        {status?.live_execution && plan.status === 'REBALANCE_REQUIRED' && <button className="refresh-button" disabled={busy !== null} onClick={() => void run('execute', signal => apiRequest(`/api/live/plans/${plan.plan_id}/execute`, parse<{ plan_status: string; legs: Leg[] }>, { signal, method: 'POST', timeout: 240000 }).then(r => { setPlan({ ...plan, status: r.plan_status }); return refreshFills(signal) }))}>{busy === 'execute' ? 'Executing on BSC…' : 'Execute plan on BSC mainnet'}</button>}
      </>}
    </section>

    <section className="panel">
      <h2>Execution journal</h2>
      {legs.length === 0 ? <p>No live legs yet.</p> : <div className="comparison-scroll" tabIndex={0} role="region" aria-label="Fills"><table>
        <thead><tr><th>Side</th><th>Asset</th><th>Notional</th><th>Status</th><th>Approve tx</th><th>Swap tx</th><th>Execution cost vs mark</th><th>Reasons</th></tr></thead>
        <tbody>{legs.map(l => <tr key={l.action_id}><td>{l.side}</td><td>{l.asset}</td><td>{money(l.notional_usd)}</td><td>{l.status}</td><td>{scan(l.approve_tx)}</td><td>{scan(l.swap_tx)}</td><td>{money(l.realized_cost_usd)}</td><td>{l.reasons.join(', ')}</td></tr>)}</tbody>
      </table></div>}
    </section>
    {error && <p role="alert">{error}</p>}
  </section>
}
