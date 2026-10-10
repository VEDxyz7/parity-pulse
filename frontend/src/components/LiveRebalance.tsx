import { useEffect, useState } from 'react'
import { apiRequest, ApiError } from '../services/api'
import type { GateName, GateState } from '../types/system'

type Fill = { action_id: string; plan_id: string; asset: string; side: 'BUY' | 'SELL'; status: string; notional_usd: string; approve_tx: string | null; swap_tx: string | null; reasons: string[]; created_at: string; updated_at: string }
const liveNames = ['SWAP_LIVE_GATE', 'RFQ_LIVE_GATE', 'AGENTIC_WALLET_LIVE_GATE'] as const
const states = new Set(['PREPARING', 'QUOTED', 'APPROVING', 'SIGNED', 'SUBMITTING', 'SUBMITTED', 'SUBMISSION_UNKNOWN', 'RECONCILIATION_REQUIRED', 'CONFIRMED', 'FAILED', 'REJECTED', 'NOT_FILLED'])
function parseFills(value: unknown): Fill[] {
  if (!Array.isArray(value) || value.length > 100) throw new Error('Invalid journal')
  return value.map(item => {
    if (!item || typeof item !== 'object' || Array.isArray(item)) throw new Error('Invalid fill')
    const row = item as Record<string, unknown>
    if (!['action_id', 'plan_id', 'asset', 'status', 'notional_usd', 'created_at', 'updated_at'].every(key => typeof row[key] === 'string') ||
      !/^[A-Za-z0-9_.:-]{1,128}$/.test(String(row.action_id)) || !['BUY', 'SELL'].includes(String(row.side)) || !states.has(String(row.status)) ||
      !/^\d+(?:\.\d+)?$/.test(String(row.notional_usd)) ||
      !['created_at', 'updated_at'].every(key => /(?:Z|[+-]\d\d:\d\d)$/.test(String(row[key])) && Number.isFinite(Date.parse(String(row[key])))) ||
      !['approve_tx', 'swap_tx'].every(key => row[key] === null || (typeof row[key] === 'string' && /^0x[0-9a-fA-F]{64}$/.test(row[key]))) ||
      !Array.isArray(row.reasons) || !row.reasons.every(reason => typeof reason === 'string')) throw new Error('Invalid fill')
    // Positive display allowlist. Legacy raw signatures/evidence never enter component state.
    return { action_id: String(row.action_id), plan_id: String(row.plan_id), asset: String(row.asset), side: row.side as Fill['side'], status: String(row.status), notional_usd: String(row.notional_usd), approve_tx: row.approve_tx as string | null, swap_tx: row.swap_tx as string | null, reasons: row.reasons as string[], created_at: String(row.created_at), updated_at: String(row.updated_at) }
  })
}
const transaction = (hash: string | null) => hash ? <a href={`https://bscscan.com/tx/${hash}`} target="_blank" rel="noreferrer">{hash.slice(0, 12)}…</a> : 'Unavailable'

/** Read-only diagnostics only. Browser credentials and execution actions are absent. */
export function LiveRebalance({ gates }: { gates: Record<GateName, GateState> }) {
  const [fills, setFills] = useState<Fill[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  useEffect(() => {
    const controller = new AbortController()
    apiRequest('/api/live/fills', parseFills, { signal: controller.signal }).then(setFills).catch((cause: unknown) => {
      if (controller.signal.aborted) return
      setFills(null)
      setError(cause instanceof ApiError && cause.status === 404 ? 'Execution worker diagnostics are not configured. Live execution remains blocked.' : 'Journal unavailable or invalid. No fallback evidence was substituted.')
    })
    return () => controller.abort()
  }, [])
  return <section className="workspace-view" aria-label="Execution status">
    <h1>Execution status</h1>
    <section className="panel"><h2>Independent execution gates</h2><p>Read-only diagnostics. DRY_RUN · PROPOSE_ONLY · simulation required. No real funds will move.</p><dl>{liveNames.map(name => <div key={name}><dt>{name}</dt><dd>{gates[name]}</dd></div>)}</dl><p>Trust remains mandatory. Closed-market execution and settlement equivalence remain unverified.</p><button className="refresh-button" disabled>Live rebalance unavailable</button><p>Review non-live drift proposals in <a href="#autopilot">Autopilot status</a>. Independent equity references remain separate from Binance index corroboration.</p></section>
    <section className="panel"><h2>Execution journal</h2>{error ? <p role="status">{error}</p> : fills === null ? <p role="status">Reading execution journal…</p> : fills.length === 0 ? <p>No recorded live legs.</p> : <div className="comparison-scroll" role="region" tabIndex={0} aria-label="Execution journal records"><table><thead><tr><th>Asset</th><th>Side</th><th>Notional USD</th><th>Status</th><th>Approval</th><th>Settlement</th><th>Reasons</th></tr></thead><tbody>{fills.map(fill => <tr key={fill.action_id}><td>{fill.asset}</td><td>{fill.side}</td><td>{fill.notional_usd}</td><td>{fill.status}</td><td>{transaction(fill.approve_tx)}</td><td>{transaction(fill.swap_tx)}</td><td>{fill.reasons.join(', ')}</td></tr>)}</tbody></table></div>}</section>
  </section>
}
