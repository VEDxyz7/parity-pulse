import { Button } from '../ui/Button'
import { useEffect, useRef, useState } from 'react'
import type { OpportunityResult } from '../services/demoOpportunity'
import type { PreparationResult, QuoteResult, SimulationResult } from '../services/demoPreparation'
import { paperRequest, parseLifecycle, parseScorecard, type Lifecycle, type Scorecard } from '../services/demoPaper'
import { useDemoPipeline } from './DemoPipeline'

export function DemoPaperFlow({ quote, prepared, simulation, origin, expired, onFilled }: {
  quote: QuoteResult; prepared: PreparationResult; simulation: SimulationResult; origin: OpportunityResult; expired: boolean; onFilled: () => void
}) {
  const pipeline = useDemoPipeline()
  const [row, setRow] = useState<Lifecycle | null>(null)
  const [score, setScore] = useState<Scorecard | null>(null)
  const [busy, setBusy] = useState(false), [error, setError] = useState('')
  const pending = useRef<AbortController | null>(null)
  useEffect(() => () => { pending.current?.abort(); pending.current = null }, [])
  async function run(stage: 'fill' | 'monitor' | 'exit' | 'score') {
    if (!prepared.transaction || simulation.simulation.status !== 'SIMULATION_PASS') return
    pending.current?.abort(); const controller = new AbortController(); pending.current = controller
    setBusy(true); setError('')
    const label = stage === 'fill' ? 'PAPER EXECUTION' : stage === 'monitor' ? 'MONITOR' : stage === 'exit' ? 'EXIT' : 'SCORECARD'
    pipeline.report(label, 'running', 'Calling the existing isolated paper ledger')
    const timer = setTimeout(() => controller.abort(), 60_000)
    try {
      const base = 'positions/' + row?.position.position_id
      const value = stage === 'fill' ? await paperRequest('fills', controller.signal, {
        transaction_id: prepared.transaction.transaction_id, simulation_id: simulation.simulation.simulation_id,
      }) : stage === 'score' ? await paperRequest(base + '/scorecard', controller.signal) :
        await paperRequest(base + '/' + stage, controller.signal, stage === 'exit' ? { observation_id: row?.observation?.observation_id } : {})
      if (pending.current !== controller || controller.signal.aborted) return
      if (stage === 'score' && row) {
        const result = parseScorecard(value, row, origin)
        setScore(result); pipeline.report('SCORECARD', 'pass', `${result.execution_status}: ledger-derived scorecard`)
      } else {
        const result = parseLifecycle(value, quote, prepared, simulation, origin)
        setRow(result); onFilled()
        pipeline.report(label, 'pass', stage === 'fill' ? result.order.status : stage === 'exit' ? result.position.state : 'Explicit synthetic observation returned')
        pipeline.report('POSITION', 'pass', `${result.position.state}: ${result.position.position_id}`)
        if (result.pnl) pipeline.report('P&L', 'pass', `Backend-calculated net PAPER P&L: ${result.pnl.net_pnl_usd} USD`)
      }
    } catch {
      if (pending.current === controller) {
        setError('Paper step unavailable, expired or invalid. Existing ledger records are retained. No real funds moved; retrying the same paper fill cannot duplicate it.')
        pipeline.report(label, 'failed', 'Paper API result unavailable, expired or invalid; ledger records retained')
      }
    } finally { clearTimeout(timer); if (pending.current === controller) setBusy(false) }
  }
  if (simulation.simulation.status !== 'SIMULATION_PASS') return null
  return <section className="demo-paper-flow" aria-label="Paper Position and Scorecard">
    <h4>PAPER EXECUTION → Position → Monitor → Exit → Scorecard</h4>
    <p><strong>SIMULATED DATA — NOT LIVE TRADING</strong><br />NO REAL FUNDS MOVED</p>
    <p>Session-only paper ledger; restarting the isolated backend clears paper records. Production databases are untouched.</p>
    <Button className="refresh-button" disabled={busy || (!row && expired)} onClick={() => { void run('fill') }}>
      {row ? 'Retrieve Paper Fill' : 'Create Paper Fill'}
    </Button>
    {!row && expired && <p role="status">Simulation/quote expired. Refresh the analysis before creating a paper fill.</p>}
    {error && <p role="alert">{error}</p>}
    {row && <>
      <h4>Paper execution: <strong>{row.order.status}</strong></h4>
      <p>SYNTHETIC_QUOTE_FILL · No real funds moved · Fill ID: <code>{row.fill.fill_id}</code></p>
      <h4>Position: <strong>{row.position.state}</strong></h4>
      <p>{row.position.ticker} / {row.position.issuer} · Illustrative paper position · Position ID: <code>{row.position.position_id}</code></p>
      <dl className="trust-facts">
        <div><dt>Entry quantity / tokens</dt><dd>{row.fill.quantity}</dd></div>
        <div><dt>Entry price / USD per token, including slippage</dt><dd>{row.fill.price_usd}</dd></div>
        <div><dt>Entry notional / USD</dt><dd>{row.fill.notional_usd}</dd></div>
        <div><dt>Entry fees and gas / USD</dt><dd>{row.position.entry_costs_usd}</dd></div>
        <div><dt>Execution reserve / USD, released on exit</dt><dd>{row.position.reserved_usd}</dd></div>
      </dl>
      <p>Entry synthetic time: {row.fill.filled_at}. Current paper Risk was revalidated using ledger cash, exposure, losses, trade count and cooldown.</p>
      {row.position.state === 'OPEN' && !row.observation && <Button className="refresh-button" disabled={busy} onClick={() => { void run('monitor') }}>Monitor Synthetic Opening Observation</Button>}
      {row.observation && <>
        <h4>Monitor: explicit synthetic observation</h4>
        <p>{row.observation.description}</p>
        <p>Synthetic time advanced to {row.observation.observed_at}. This is not a real market opening bar.</p>
        <dl className="trust-facts">
          <div><dt>Exit observation mark / USD per token</dt><dd>{row.observation.token_mark_price_usd}</dd></div>
          <div><dt>Synthetic SELL price including slippage / USD per token</dt><dd>{row.observation.sell_price_usd}</dd></div>
          <div><dt>Exit fee / USD</dt><dd>{row.observation.fees_usd}</dd></div>
          <div><dt>Exit gas / USD</dt><dd>{row.observation.gas_usd}</dd></div>
        </dl>
        {row.position.state === 'OPEN' && <Button className="refresh-button" disabled={busy} onClick={() => { void run('exit') }}>Exit Paper Position</Button>}
      </>}
      {row.pnl && <>
        <h4>Realized PAPER P&amp;L</h4>
        <dl className="trust-facts">
          <div><dt>Gross P&amp;L / USD</dt><dd>{row.pnl.gross_pnl_usd}</dd></div>
          <div><dt>Entry + exit fees and gas / USD</dt><dd>{row.pnl.costs_usd}</dd></div>
          <div><dt>Net P&amp;L / USD</dt><dd>{row.pnl.net_pnl_usd}</dd></div>
          <div><dt>Return on entry cost basis / %</dt><dd>{row.pnl.return_pct}</dd></div>
        </dl>
        <p>Slippage is already in entry/exit prices. The unused reserve is released, not charged as a fee.</p>
        <Button className="refresh-button" disabled={busy} onClick={() => { void run('score') }}>View Paper Scorecard</Button>
      </>}
      {score && <>
        <h4>Scorecard: <strong>EXITED</strong></h4>
        <p>Scenario: {score.scenario_id} · Trust: {score.trust_classification} · Evidence: {score.evidence_quality} · Confidence: {score.confidence}</p>
        <p>Opportunity: {score.opportunity_status} · Risk: {score.risk_status} · Local simulation: {score.simulation_status} · Paper result: {score.execution_status}</p>
        <p>Net PAPER P&amp;L: {score.pnl.net_pnl_usd} USD · Return: {score.pnl.return_pct}%</p>
        <p>Ledger-derived reasons: {score.reason_codes.join(' · ')}</p>
        <p>Production Trust and Opportunity remain blocked. All live execution remains blocked.</p>
      </>}
      <details><summary>Paper lifecycle and scorecard audit records</summary><pre>{JSON.stringify({ row, score }, null, 2)}</pre></details>
    </>}
  </section>
}
