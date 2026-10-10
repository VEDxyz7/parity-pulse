import { Activity, ArrowUpRight, ChartNoAxesCombined, Database, LockKeyhole, ShieldCheck } from 'lucide-react'
import type { SystemStatus } from '../types/system'

type Snapshot = { system: SystemStatus | undefined; checking: boolean }

// Presentation of the existing health snapshot only. No requests, market estimates or gate decisions.
export function FloatingWidgets({ system, checking, side }: Snapshot & { side: 'left' | 'right' }) {
  if (side === 'left') return <aside className="floating-widgets left-widgets" aria-label="Workspace safety summary">
    <section className="floating-card">
      <div className="widget-label"><ShieldCheck size={15} />Execution safety</div>
      <p className="widget-value">{system ? system.execution_mode.replaceAll('_', ' ') + ' only' : 'Unverified'}</p>
      <p className="widget-caption">{system ? system.approval_mode.replaceAll('_', ' ') : 'Awaiting backend status'}</p>
      <div className="widget-divider" />
      <p className="widget-footnote">{system ? `Live trading: ${system.live_trading_enabled ? 'enabled' : 'disabled'}` : 'Execution status unknown'}</p>
      <p className="widget-footnote">{system ? `Simulation: ${system.require_simulation ? 'required' : 'not required'}` : 'Safety settings unverified'}</p>
    </section>
    <section className="floating-card">
      <div className="widget-label"><Activity size={15} />Backend health</div>
      <div className={`connection-orbit ${system ? 'connected' : ''}`} aria-hidden="true"><Activity size={35} strokeWidth={1.3} /></div>
      <p className="widget-caption">{checking ? 'Verifying connection' : system ? 'Service reachable' : 'Service unavailable'}</p>
      <p className="widget-footnote">{system ? `Version ${system.service_version}` : 'No healthy state substituted'}</p>
    </section>
  </aside>

  return <aside className="floating-widgets right-widgets" aria-label="Workspace data summary">
    <section className="floating-card">
      <div className="widget-label"><Database size={15} />Source context</div>
      <p className="widget-value context-value">{system?.environment ?? 'Unverified'}</p>
      <p className="widget-caption">{system?.data_mode === 'DEMO' ? 'Synthetic inputs, isolated' : system ? 'Read-only provider inputs' : 'Source status unavailable'}</p>
      <div className="widget-divider" />
      <p className="widget-footnote">{system?.data_mode === 'DEMO' ? 'Not live market data.' : 'Availability varies by source.'}</p>
      <a className="widget-link" href="#terminal">Inspect evidence<ArrowUpRight size={13} /></a>
    </section>
    <section className="floating-card">
      <div className="widget-label"><LockKeyhole size={15} />Live capabilities</div>
      <dl className="widget-gates">
        {([['SWAP', 'SWAP_LIVE_GATE'], ['RFQ', 'RFQ_LIVE_GATE'], ['Wallet', 'AGENTIC_WALLET_LIVE_GATE']] as const).map(([label, key]) =>
          <div key={key}><dt>{label}</dt><dd className={system?.gates[key] === 'PASS' ? 'positive-text' : 'warning-text'}>{system?.gates[key] ?? 'UNKNOWN'}</dd></div>,
        )}
      </dl>
      <p className="widget-footnote">Backend-reported authority</p>
    </section>
  </aside>
}

export function CapabilityOverview({ system }: Pick<Snapshot, 'system'>) {
  // Categorical counts of the five gates already returned by the health API, not financial performance.
  const states = system ? [system.gates.DATA_GATE, system.gates.DRY_RUN_GATE, system.gates.SWAP_LIVE_GATE, system.gates.RFQ_LIVE_GATE, system.gates.AGENTIC_WALLET_LIVE_GATE] : []
  const passed = states.filter(state => state === 'PASS').length
  const blocked = states.filter(state => state === 'BLOCKED').length
  const pending = states.length - passed - blocked
  const fill = states.length ? `conic-gradient(var(--mint) 0 ${passed / states.length * 100}%, var(--amber) ${passed / states.length * 100}% ${(passed + blocked) / states.length * 100}%, var(--chart-neutral) ${(passed + blocked) / states.length * 100}% 100%)` : 'var(--border)'

  return <section className="panel capability-overview" aria-label="Capability state distribution">
    <div className="panel-heading"><div><h2>Capability distribution</h2><p>Reported gates · not investment performance</p></div><ShieldCheck size={17} /></div>
    <div className="capability-chart">
      <div className="gate-donut" style={{ background: fill }} role="img" aria-label={system ? `${passed} passed, ${blocked} blocked, ${pending} not yet tested out of ${states.length} reported gates` : 'Gate distribution unavailable until backend status is verified'}>
        <div><strong>{system ? `${passed}/${states.length}` : '—'}</strong><span>{system ? 'gates passed' : 'unverified'}</span></div>
      </div>
      <dl className="chart-legend">
        <div><dt><i className="legend-pass" />Passed</dt><dd>{system ? passed : '—'}</dd></div>
        <div><dt><i className="legend-blocked" />Blocked</dt><dd>{system ? blocked : '—'}</dd></div>
        <div><dt><i className="legend-pending" />Untested</dt><dd>{system ? pending : '—'}</dd></div>
      </dl>
    </div>
    <p className="chart-note">Read-only progress does not grant execution authority.</p>
  </section>
}

export function MarketOverview() {
  return <section className="panel market-overview" aria-label="Market series availability">
    <div className="panel-heading"><div><h2>Market observations</h2><p>Tokenized equities / independent reference</p></div><ChartNoAxesCombined size={17} /></div>
    <div className="chart-empty">
      <span className="empty-chart-icon"><ChartNoAxesCombined size={25} strokeWidth={1.4} /></span>
      <strong>Price history unavailable</strong>
      <p>This health summary does not supply a market series. No chart values have been inferred.</p>
      <a href="#terminal">Explore cached evidence<ArrowUpRight size={14} /></a>
    </div>
    <div className="market-panel-footer"><span><i />Source-backed observations only</span><span>No fabricated history</span></div>
  </section>
}
