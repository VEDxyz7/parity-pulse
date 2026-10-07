import {
  Activity, ArrowDownUp, ArrowUpRight, Check, CircleHelp, Database, Layers3,
  LayoutDashboard, LockKeyhole, Radio, RefreshCw, ShieldCheck, Sparkles, Workflow,
} from 'lucide-react'
import { useSystemStatus } from './hooks/useSystemStatus'
import { AskFlow } from './components/AskFlow'
import { TrustPanel } from './components/TrustPanel'
import { DemoTrustSandbox } from './components/DemoTrustSandbox'
import { StatusBadge } from './components/StatusBadge'
import type { GateName } from './types/system'
import { useEffect, useState } from 'react'

const gates: { key: GateName; label: string; description: string }[] = [
  { key: 'DATA_GATE', label: 'Data & read-only', description: 'Verified access for non-live development' },
  { key: 'DRY_RUN_GATE', label: 'Dry-run workflow', description: 'Feasible · implementation and tests pending' },
  { key: 'SWAP_LIVE_GATE', label: 'Live swap execution', description: 'Transaction equivalence not verified' },
  { key: 'RFQ_LIVE_GATE', label: 'Live RFQ execution', description: 'Settlement equivalence not verified' },
  { key: 'AGENTIC_WALLET_LIVE_GATE', label: 'Live wallet execution', description: 'Wallet runtime integration not verified' },
]

export function App() {
  const [hash, setHash] = useState(window.location.hash)
  useEffect(() => {
    const update = () => setHash(window.location.hash)
    window.addEventListener('hashchange', update)
    return () => window.removeEventListener('hashchange', update)
  }, [])
  const query = useSystemStatus()
  const verified = !query.isError && query.data ? query.data : null
  const system = verified?.system
  const available = Boolean(verified)
  const askReady = system?.gates.DRY_RUN_GATE === 'PASS'
  const showDemo = hash === '#demo-sandbox' || (hash === '' && system?.runtime_mode === 'DEMO')
  useEffect(() => {
    if (!['#ask', '#system', '#capabilities'].includes(hash)) return
    const frame = requestAnimationFrame(() => document.getElementById(hash.slice(1))?.scrollIntoView({ behavior: 'smooth' }))
    return () => cancelAnimationFrame(frame)
  }, [hash, available])
  const connection = query.isPending ? 'Checking backend' : available ? 'Backend connected' : 'Backend unavailable'

  return <div className="app-layout">
    <a className="skip-link" href="#main-content" onClick={event => { event.preventDefault(); document.getElementById('main-content')?.focus() }}>Skip to main content</a>
    <aside className="sidebar">
      <a className="brand" href="#main-content" aria-label="Parity Pulse home">
        <span className="brand-mark"><Activity size={23} strokeWidth={2.2} /></span>
        <span>Parity<span className="brand-light">Pulse</span><small>EQUITY INTELLIGENCE</small></span>
      </a>
      <div className="workspace-label">YOUR WORKSPACE <span>01</span></div>
      <nav aria-label="Main navigation" className="navigation">
        <a href="#overview" className={`nav-item ${showDemo ? '' : 'active'}`} aria-current={showDemo ? undefined : 'page'}><LayoutDashboard size={18} />Overview{!showDemo && <span className="nav-dot" />}</a>
        <a href="#system" className="nav-item"><Activity size={18} />System status</a>
        <a href="#demo-sandbox" className={`nav-item demo-nav ${showDemo ? 'active' : ''}`} aria-current={showDemo ? 'page' : undefined}><ShieldCheck size={18} />DEMO SANDBOX{showDemo && <span className="nav-dot" />}</a>
        <div className="nav-section">PRODUCT MODES</div>
        <button className="nav-item" disabled={!askReady} onClick={() => { window.location.hash = 'ask' }}><ArrowDownUp size={18} />Direct Exposure<LockKeyhole size={13} /></button>
        <button className="nav-item deferred" disabled title="Available in a later phase"><Sparkles size={18} />Opportunity<LockKeyhole size={13} /></button>
        <button className="nav-item deferred" disabled title="Available in a later phase"><Workflow size={18} />Autopilot<LockKeyhole size={13} /></button>
        <p className="nav-note">Ask for exposure when verified. Opportunity and Autopilot remain unavailable.</p>
      </nav>
      <div className="sidebar-bottom">
        <div className="safe-card"><ShieldCheck size={20} /><strong>Non-live workspace</strong><p>Prepare exposure estimates.<br />Live execution is unavailable.</p></div>
        <a className="help-link" href="#capabilities"><CircleHelp size={17} />Capability gates<ArrowUpRight size={14} /></a>
        <div className="workspace-profile"><span>PP</span><div>Local workspace<small>{askReady ? 'Canonical Phase 1 · Working Ask Flow' : `Phase ${system?.phase ?? 1} · ${system?.phase === 2 ? 'Data layer' : 'Foundation'}`}</small></div></div>
      </div>
    </aside>
    <div className="workspace">
      <header className="topbar"><div><span className="breadcrumb">Workspace</span><span className="breadcrumb-slash">/</span>{showDemo ? 'DEMO SANDBOX' : 'Overview'}</div><StatusBadge tone={available ? 'green' : 'amber'}>{connection}</StatusBadge></header>
      <main id="main-content" tabIndex={-1}>
        {showDemo ? <>
          <section className="page-heading" aria-label="Synthetic sandbox mode"><div><div className="eyebrow">PARITY PULSE / DEMO</div><h1>DEMO SANDBOX</h1><p>SIMULATED DATA — NOT LIVE MARKET DATA</p><p><strong>NO REAL FUNDS WILL MOVE</strong></p></div><a className="refresh-button" href="#overview">Return to Overview</a></section>
          {system?.runtime_mode === 'DEMO' && askReady ? <DemoTrustSandbox key={`sandbox:${system.run_id}`} /> : <section className="panel demo-unavailable" aria-label="Demo sandbox availability">
            <h2>{available ? 'The connected backend has the sandbox disabled.' : 'A verified DEMO backend is required.'}</h2>
            <p>The sandbox uses existing DEMO APIs only. No production Trust assessment or live data is substituted.</p>
            {available && <><p>Start the existing backend from the repository root in its isolated DEMO runtime, then refresh this page:</p><pre>RUNTIME_MODE=DEMO DATA_MODE=DEMO .venv/bin/python -m uvicorn app.main:create_app --factory --app-dir backend --host 127.0.0.1 --port 8000 --no-access-log</pre><p>Use the existing startup runbook to manage the backend process. Production gates remain unchanged.</p></>}
            <button className="refresh-button" disabled={query.isFetching} onClick={() => { void query.refetch() }}>Refresh status</button>
          </section>}
        </> : <>
        {system?.runtime_mode === 'DEMO' && <section className="connection-alert" aria-label="Synthetic sandbox mode"><ShieldCheck size={19} /><div><strong>DEMO SANDBOX</strong><p>SIMULATED DATA — NOT LIVE MARKET DATA</p></div></section>}
        <div className="page-heading"><div><div className="eyebrow">PARITY PULSE / FOUNDATION</div><h1>Your workspace, ready to grow.</h1><p>A clear view of your environment and the capabilities available today.</p></div><button className="refresh-button" onClick={() => { void query.refetch() }} disabled={query.isFetching}><RefreshCw size={15} className={query.isFetching ? 'spinning' : ''} />{query.isFetching ? 'Checking' : 'Refresh status'}</button></div>
        <section className="foundation-banner" aria-label="Development scope"><div className="banner-icon"><Layers3 size={26} /></div><div><span className="banner-kicker">{askReady ? 'CANONICAL PHASE 01' : `ENGINEERING STAGE ${system?.phase === 2 ? '02' : '01'}`}</span><h2>A safe starting point.</h2><p>{askReady ? 'Working Ask Flow: deterministic exposure estimates with persisted proposals. Trust assessments are available separately; the Trust gate remains blocked.' : system?.phase === 2 ? 'Read-only data is available through the backend. Intelligence and execution workflows will follow in later phases.' : 'The application foundation is here. Intelligence and execution workflows will follow in later phases.'}</p></div><span className="banner-tag"><LockKeyhole size={14} />Live execution unavailable</span></section>
        <section className="demo-entry"><div><strong>DEMO SANDBOX</strong><p>Explore the existing synthetic pipeline. No real funds will move.</p></div><a className="refresh-button" href="#demo-sandbox">Open DEMO SANDBOX</a></section>
        {query.isError && <div role="alert" className="connection-alert"><Radio size={19} /><div><strong>We couldn’t reach a healthy backend.</strong><p>Check that the local backend is running, then refresh. Service values remain unknown until verified.</p></div></div>}
        <section className="metrics" aria-label="Operational configuration">
          <article className="metric"><span>Environment<Layers3 size={17} /></span><strong>{system?.environment ?? 'Unknown'}</strong><small>Application environment</small></article>
          <article className="metric"><span>Data mode<Database size={17} /></span><strong>{system?.data_mode.replaceAll('_', ' ') ?? 'Unknown'}</strong><small>{system?.data_mode === 'DEMO' ? 'Isolated, deterministic demo data' : system?.phase === 2 ? 'Provider reads subject to account permissions' : 'No data provider connected in Phase 1'}</small></article>
          <article className="metric"><span>Execution mode<ShieldCheck size={17} /></span><strong>{system?.execution_mode.replaceAll('_', ' ') ?? 'Unknown'}</strong><small>Proposal only · no live execution</small></article>
        </section>
        {askReady && system && <AskFlow key={`${system.run_id}:${system.data_mode}`} mode={system.data_mode} />}
        {askReady && system && <TrustPanel key={`trust:${system.run_id}:${system.data_mode}`} mode={system.data_mode} />}
        <div className="panels">
          <section className="panel" id="system"><div className="panel-heading"><div><h2>System health</h2><p>The essentials behind your workspace.</p></div><Activity size={19} /></div>
            <div className="health-row"><div className="row-icon"><Radio size={17} /></div><div><strong>Backend service</strong><small>FastAPI application</small></div><StatusBadge tone={available ? 'green' : 'amber'}>{query.isPending ? 'Checking' : available ? 'Healthy' : 'Unavailable'}</StatusBadge></div>
            <div className="health-row"><div className="row-icon"><Database size={17} /></div><div><strong>Database</strong><small>SQLite · foundation metadata</small></div><StatusBadge tone={system?.database_status === 'connected' ? 'green' : 'neutral'}>{system?.database_status === 'connected' ? 'Connected' : 'Unknown'}</StatusBadge></div>
            <div className="health-row"><div className="row-icon"><Layers3 size={17} /></div><div><strong>Demo fixture</strong><small>{system?.demo_fixture ? 'DEMO · no execution authority' : 'Foundation metadata only'}</small></div><StatusBadge tone={system?.demo_fixture ? 'green' : 'neutral'}>{system?.demo_fixture ? 'Loaded' : system ? 'Not loaded' : 'Unknown'}</StatusBadge></div>
            <div className="panel-footer"><span>Service version</span><code>{system ? `v${system.service_version}` : 'Unknown'}</code></div>
          </section>
          <section className="panel" id="capabilities"><div className="panel-heading"><div><h2>Capability gates</h2><p>Development progress stays separate from live authority.</p></div><ShieldCheck size={19} /></div>
            <div className="gate-list">{gates.map(gate => {
              const state = system?.gates[gate.key]
              return <div className="gate-row" key={gate.key}><span className={`gate-symbol ${state === 'PASS' ? 'passed' : ''}`}>{state === 'PASS' ? <Check size={14} /> : <LockKeyhole size={13} />}</span><div><strong>{gate.label}</strong><small>{gate.key === 'DRY_RUN_GATE' && askReady ? 'Verified Ask proposals · simulation unavailable · no live actions' : gate.description}</small></div><span className={`gate-state ${state === 'PASS' ? 'passed' : ''}`}>{state === 'NOT_YET_TESTED' ? 'Not yet tested' : state ? state.toLowerCase() : 'Unknown'}</span></div>
            })}</div>
          </section>
        </div>
        <section className="scope-note"><div><ShieldCheck size={20} /><div><strong>Built for safe development</strong><p>No funds move here. Simulation stays required, and execution remains propose-only.</p></div></div><span>{askReady ? 'ESTIMATES ONLY' : 'FOUNDATION ONLY'}</span></section>
        <footer className="page-footer"><span>Parity Pulse <span className="footer-dot">·</span> Tokenized equity intelligence</span><span>{system ? `${system.approval_mode.replaceAll('_', ' ')} · SIMULATION REQUIRED` : 'SERVICE STATUS UNVERIFIED'}</span></footer>
        </>}
      </main>
    </div>
  </div>
}
