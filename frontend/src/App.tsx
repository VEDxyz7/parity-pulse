import {
  Activity, ArrowDownUp, ArrowUpRight, Check, CircleHelp, Database, Layers3,
  LayoutDashboard, LockKeyhole, Radio, RefreshCw, ShieldCheck, Sparkles, Workflow,
} from 'lucide-react'
import { useSystemStatus } from './hooks/useSystemStatus'
import { AskFlow } from './components/AskFlow'
import { TrustPanel } from './components/TrustPanel'
import { Terminal } from './components/Terminal'
import { ScorecardAudit } from './components/ScorecardAudit'
import { AgentApi } from './components/AgentApi'
import { DemoTrustSandbox } from './components/DemoTrustSandbox'
import { StatusBadge } from './components/StatusBadge'
import { CapabilityOverview, FloatingWidgets, MarketOverview } from './components/DashboardVisuals'
import type { GateName } from './types/system'
import { lazy, Suspense, useEffect, useState } from 'react'

const OpportunityView = lazy(() => import('./components/OpportunityView').then(m => ({ default: m.OpportunityView })))
const PortfolioView = lazy(() => import('./components/WorkspaceViews').then(m => ({ default: m.PortfolioView })))
const SystemView = lazy(() => import('./components/WorkspaceViews').then(m => ({ default: m.SystemView })))
const AuditEvents = lazy(() => import('./components/WorkspaceViews').then(m => ({ default: m.AuditEvents })))

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
  const showTerminal = hash === '#terminal'
  const showAgentApi = hash === '#agent-api'
  const showOpportunity = hash === '#opportunity' || hash.startsWith('#opportunity/')
  const scanId = /^#opportunity\/([a-f0-9]{64})$/.exec(hash)?.[1]
  const showPortfolio = hash === '#portfolio', showAutopilot = hash === '#autopilot'
  const showSettings = hash === '#settings', showAudit = hash === '#audit' || hash.startsWith('#audit/')
  let decisionId: string | undefined
  try {
    const decoded = decodeURIComponent(hash.slice('#audit/'.length))
    if (hash.startsWith('#audit/') && /^[A-Za-z0-9_.:-]{1,160}$/.test(decoded)) decisionId = decoded
  } catch { /* Invalid URI never becomes an API identifier. */ }
  const showAsk = hash === '#ask'
  const additional = showOpportunity || showPortfolio || showAutopilot || showSettings || showAudit || showAsk
  useEffect(() => {
    if (!['#ask', '#system', '#capabilities'].includes(hash)) return
    const frame = requestAnimationFrame(() => document.getElementById(hash.slice(1))?.scrollIntoView({ behavior: 'smooth' }))
    return () => cancelAnimationFrame(frame)
  }, [hash, available])
  const connection = query.isPending ? 'Checking backend' : available ? 'Backend connected' : 'Backend unavailable'

  return <div className="page">
    <a className="skip-link" href="#main-content" onClick={event => { event.preventDefault(); document.getElementById('main-content')?.focus() }}>Skip to main content</a>
    <header className="product-hero">
      <p className="hero-brand"><Activity size={18} />Parity Pulse</p>
      <p className="hero-title"><span>Intelligence</span> for Tokenized Equities</p>
      <p className="hero-subtitle">Independent evidence. Clearer exposure. A more informed portfolio.</p>
    </header>
    <div className="composition">
    <FloatingWidgets side="left" system={system} checking={query.isPending} />
    <div className="app-layout">
    <aside className="sidebar">
      <a className="brand" href="#main-content" aria-label="Parity Pulse home">
        <span className="brand-mark"><Activity size={23} strokeWidth={2.2} /></span>
        <span>Parity<span className="brand-light">Pulse</span><small>EQUITY INTELLIGENCE</small></span>
      </a>
      <div className="workspace-label">YOUR WORKSPACE <span>01</span></div>
      <nav aria-label="Main navigation" className="navigation">
        <a href="#overview" className={`nav-item ${showDemo || showTerminal || showAgentApi || additional ? '' : 'active'}`} aria-current={showDemo || showTerminal || showAgentApi || additional ? undefined : 'page'}><LayoutDashboard size={18} />Overview{!showDemo && !showTerminal && !showAgentApi && !additional && <span className="nav-dot" />}</a>
        <a href="#agent-api" className={`nav-item ${showAgentApi ? 'active' : ''}`} aria-current={showAgentApi ? 'page' : undefined}><Layers3 size={18} />Agent API</a>
        <a href="#terminal" className={`nav-item ${showTerminal ? 'active' : ''}`} aria-current={showTerminal ? 'page' : undefined}><Database size={18} />Terminal</a>
        <a href="#settings" className={`nav-item ${showSettings ? 'active' : ''}`} aria-current={showSettings ? 'page' : undefined}><Activity size={18} />System status</a>
        <a href="#demo-sandbox" className={`nav-item demo-nav ${showDemo ? 'active' : ''}`} aria-current={showDemo ? 'page' : undefined}><ShieldCheck size={18} />DEMO SANDBOX{showDemo && <span className="nav-dot" />}</a>
        <a href="#opportunity" className={`nav-item ${showOpportunity ? 'active' : ''}`} aria-current={showOpportunity ? 'page' : undefined}><Sparkles size={18} />Opportunity analysis</a>
        <a href="#autopilot" className={`nav-item ${showAutopilot ? 'active' : ''}`} aria-current={showAutopilot ? 'page' : undefined}><Workflow size={18} />Autopilot status</a>
        <a href="#portfolio" className={`nav-item ${showPortfolio ? 'active' : ''}`} aria-current={showPortfolio ? 'page' : undefined}><Layers3 size={18} />Portfolio</a>
        <a href="#audit" className={`nav-item ${showAudit ? 'active' : ''}`} aria-current={showAudit ? 'page' : undefined}><Activity size={18} />Scorecard / Audit</a>
        <div className="nav-section">EXECUTION AUTHORITY</div>
        <button className="nav-item" disabled={!askReady} onClick={() => { window.location.hash = 'ask' }}><ArrowDownUp size={18} />Direct Exposure<LockKeyhole size={13} /></button>
        <button className="nav-item deferred" disabled title="Execution blocked by production safety gates"><Sparkles size={18} />Opportunity<LockKeyhole size={13} /></button>
        <button className="nav-item deferred" disabled title="Execution blocked by production safety gates"><Workflow size={18} />Autopilot<LockKeyhole size={13} /></button>
        <p className="nav-note">Ask for exposure when verified. Analytical views are available; production execution remains blocked.</p>
      </nav>
      <div className="sidebar-bottom">
        <div className="safe-card"><ShieldCheck size={20} /><strong>Non-live workspace</strong><p>Prepare exposure estimates.<br />Live execution is unavailable.</p></div>
        <a className="help-link" href="#capabilities"><CircleHelp size={17} />Capability gates<ArrowUpRight size={14} /></a>
        <div className="workspace-profile"><span>PP</span><div>Local workspace<small>{askReady ? 'Master Phase 15 · Non-live integration' : `Phase ${system?.phase ?? 1} · ${system?.phase === 2 ? 'Data layer' : 'Foundation'}`}</small></div></div>
      </div>
    </aside>
    <div className="workspace">
      <header className="topbar"><div><span className="breadcrumb">Workspace</span><span className="breadcrumb-slash">/</span>{showOpportunity ? 'Opportunity analysis' : showPortfolio ? 'Portfolio' : showAutopilot ? 'Autopilot' : showSettings ? 'System Health' : showAudit ? 'Scorecard / Audit' : showAsk ? 'Buy a Stock' : showAgentApi ? 'Agent API' : showTerminal ? 'Terminal' : showDemo ? 'DEMO SANDBOX' : 'Overview'}</div><StatusBadge tone={available ? 'green' : 'amber'}>{connection}</StatusBadge></header>
      <main id="main-content" tabIndex={-1}>
        {additional ? (system ? <Suspense fallback={<p role="status">Loading page…</p>}><div key={`${hash}:${system.run_id}:${system.data_mode}`}>
          {showOpportunity ? <OpportunityView mode={system.data_mode} sandbox={system.runtime_mode === 'DEMO'} scanId={scanId} /> : showPortfolio || showAutopilot ? <PortfolioView mode={system.data_mode} autopilot={showAutopilot} /> : showSettings ? <SystemView mode={system.data_mode} /> : showAudit ? <div className="workspace-view"><h1>Scorecard / Audit</h1><ScorecardAudit mode={system.data_mode} initialDecision={decisionId ? decisionId : undefined} /><AuditEvents mode={system.data_mode} /></div> : <><h1>Buy a Stock</h1><AskFlow mode={system.data_mode} /><TrustPanel mode={system.data_mode} /></>}
        </div></Suspense> : <section className="panel demo-unavailable"><h1>Backend state unavailable</h1><p role="status">A verified backend is required. No financial values or cached healthy state are substituted.</p><button className="refresh-button" disabled={query.isFetching} onClick={() => void query.refetch()}>Retry backend status</button></section>) : showAgentApi ? <AgentApi /> : showTerminal ? (system ? <Terminal key={`terminal:${system.run_id}:${system.data_mode}`} mode={system.data_mode} /> : <section className="panel"><h1>Terminal</h1><p>A verified backend is required. Analytical values remain unavailable.</p></section>) : showDemo ? <>
          <section className="page-heading" aria-label="Synthetic sandbox mode"><div><div className="eyebrow">PARITY PULSE / DEMO</div><h1>DEMO SANDBOX</h1><p>SIMULATED DATA — NOT LIVE MARKET DATA</p><p><strong>NO REAL FUNDS WILL MOVE</strong></p></div><a className="refresh-button" href="#overview">Return to Overview</a></section>
          {system?.runtime_mode === 'DEMO' && askReady ? <DemoTrustSandbox key={`sandbox:${system.run_id}`} /> : <section className="panel demo-unavailable" aria-label="Demo sandbox availability">
            <h2>{available ? 'The connected backend has the sandbox disabled.' : 'A verified DEMO backend is required.'}</h2>
            <p>The sandbox uses existing DEMO APIs only. No production Trust assessment or live data is substituted.</p>
            {available && <><p>Start the existing backend from the repository root in its isolated DEMO runtime, then refresh this page:</p><pre>RUNTIME_MODE=DEMO DATA_MODE=DEMO .venv/bin/python -m uvicorn app.main:create_app --factory --app-dir backend --host 127.0.0.1 --port 8000 --no-access-log</pre><p>Use the existing startup runbook to manage the backend process. Production gates remain unchanged.</p></>}
            <button className="refresh-button" disabled={query.isFetching} onClick={() => { void query.refetch() }}>Refresh status</button>
          </section>}
        </> : <>
        {system?.runtime_mode === 'DEMO' && <section className="connection-alert" aria-label="Synthetic sandbox mode"><ShieldCheck size={19} /><div><strong>DEMO SANDBOX</strong><p>SIMULATED DATA — NOT LIVE MARKET DATA</p></div></section>}
        <div className="page-heading"><div><div className="eyebrow">WORKSPACE / OVERVIEW</div><h1>{askReady ? "Invest in Global Stocks, Smarter." : "Your workspace, ready to grow."}</h1><p>A clear view of your environment and the capabilities available today.</p></div><button className="refresh-button" onClick={() => { void query.refetch() }} disabled={query.isFetching}><RefreshCw size={15} className={query.isFetching ? 'spinning' : ''} />{query.isFetching ? 'Checking' : 'Refresh status'}</button></div>
        {query.isError && <div role="alert" className="connection-alert"><Radio size={19} /><div><strong>We couldn’t reach a healthy backend.</strong><p>Check that the local backend is running, then refresh. Service values remain unknown until verified.</p></div></div>}
        <section className="metrics" aria-label="Operational configuration">
          <article className="metric"><span>Data mode<Database size={17} /></span><strong>{system?.data_mode.replaceAll('_', ' ') ?? 'Unknown'}</strong><small>{system?.data_mode === 'DEMO' ? 'Isolated, deterministic demo data' : system ? 'Provider reads · entitlement dependent' : 'Awaiting verified source status'}</small><div className="metric-accent" aria-hidden="true" /></article>
          <article className="metric"><span>Execution mode<ShieldCheck size={17} /></span><strong>{system?.execution_mode.replaceAll('_', ' ') ?? 'Unknown'}</strong><small>Proposal only · no live execution</small><div className="metric-accent" aria-hidden="true" /></article>
          <article className="metric"><span>Dry-run gate<Layers3 size={17} /></span><strong className={system?.gates.DRY_RUN_GATE === 'PASS' ? 'positive-text' : 'warning-text'}>{system?.gates.DRY_RUN_GATE.replaceAll('_', ' ') ?? 'Unknown'}</strong><small>Verified non-live workflow scope</small><div className="metric-accent" aria-hidden="true" /></article>
          <article className="metric"><span>Live swap gate<LockKeyhole size={17} /></span><strong className={system?.gates.SWAP_LIVE_GATE === 'PASS' ? 'positive-text' : 'warning-text'}>{system?.gates.SWAP_LIVE_GATE.replaceAll('_', ' ') ?? 'Unknown'}</strong><small>Independent execution safety gate</small><div className="metric-accent" aria-hidden="true" /></article>
        </section>
        <div className="analytics-grid"><MarketOverview /><CapabilityOverview system={system} /></div>
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
        <section className="foundation-banner" aria-label="Development scope"><div className="banner-icon"><Layers3 size={26} /></div><div><span className="banner-kicker">{askReady ? 'MASTER PHASE 15' : `ENGINEERING STAGE ${system?.phase === 2 ? '02' : '01'}`}</span><h2>A safe starting point.</h2><p>{askReady ? 'Backend-authoritative exposure, Opportunity analysis, Portfolio and Audit. Proposals and simulations remain separate from confirmed trades. Production Trust remains blocked.' : system?.phase === 2 ? 'Read-only data is available through the backend. Intelligence and execution workflows will follow in later phases.' : 'The application foundation is here. Intelligence and execution workflows will follow in later phases.'}</p></div><span className="banner-tag"><LockKeyhole size={14} />Live execution unavailable</span></section>
        {askReady && <p className="mode-notice">Current US market status / next regular opening: unavailable on this health summary. Inspect the backend calendar and per-asset observations in <a href="#terminal">Terminal</a>. Missing market values are not inferred from the browser clock.</p>}
        {askReady && <section className="home-actions" aria-label="Primary product actions"><a href="#ask" className="panel">Buy a Stock<small>Compare exposure and review a dry-run proposal</small></a><a href="#opportunity" className="panel">Find Opportunity<small>Analytical scans; production execution blocked</small></a><a href="#autopilot" className="panel">Autopilot<small>Inspect targets and propose drift rebalances</small></a></section>}
        <section className="demo-entry"><div><strong>DEMO SANDBOX</strong><p>Explore the existing synthetic pipeline. No real funds will move.</p></div><a className="refresh-button" href="#demo-sandbox">Open DEMO SANDBOX</a></section>
        {askReady && system && <AskFlow key={`${system.run_id}:${system.data_mode}`} mode={system.data_mode} />}
        {askReady && system && <TrustPanel key={`trust:${system.run_id}:${system.data_mode}`} mode={system.data_mode} />}
        <section className="scope-note"><div><ShieldCheck size={20} /><div><strong>Built for safe development</strong><p>No funds move here. Simulation stays required, and execution remains propose-only.</p></div></div><span>{askReady ? 'ESTIMATES ONLY' : 'FOUNDATION ONLY'}</span></section>
        <footer className="page-footer"><span>Parity Pulse <span className="footer-dot">·</span> Tokenized equity intelligence</span><span>{system ? `${system.approval_mode.replaceAll('_', ' ')} · SIMULATION REQUIRED` : 'SERVICE STATUS UNVERIFIED'}</span></footer>
        </>}
      </main>
    </div>
    </div>
    <FloatingWidgets side="right" system={system} checking={query.isPending} />
    </div>
  </div>
}
