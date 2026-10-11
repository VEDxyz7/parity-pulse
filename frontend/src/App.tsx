import { Button, MetalLink } from './ui/Button'
import { ReadRefresh } from './ui/ReadRefresh'
import { useRouteMotion } from './ui/useRouteMotion'
import {
  Activity, ArrowDownUp, ArrowUpRight, Check, Database, Layers3,
  LockKeyhole, Menu, X, Radio, RefreshCw, ShieldCheck, Sparkles, Workflow,
} from 'lucide-react'
import { useSystemStatus } from './hooks/useSystemStatus'
import { AskFlow } from './components/AskFlow'
import { TrustPanel } from './components/TrustPanel'
import { Terminal } from './components/Terminal'
import { ScorecardAudit } from './components/ScorecardAudit'
import { AgentApi } from './components/AgentApi'
import { DemoTrustSandbox } from './components/DemoTrustSandbox'
import { StatusBadge } from './components/StatusBadge'
import { MarketSnapshot } from './components/MarketSnapshot'
import { dataLabel, DataContext } from './components/DataContext'
import type { GateName } from './types/system'
import { lazy, Suspense, useEffect, useRef, useState } from 'react'

const OpportunityView = lazy(() => import('./components/OpportunityView').then(m => ({ default: m.OpportunityView })))
const PortfolioView = lazy(() => import('./components/WorkspaceViews').then(m => ({ default: m.PortfolioView })))
const SystemView = lazy(() => import('./components/WorkspaceViews').then(m => ({ default: m.SystemView })))
const AuditEvents = lazy(() => import('./components/WorkspaceViews').then(m => ({ default: m.AuditEvents })))

const LiveRebalance = lazy(() => import('./components/LiveRebalance').then(m => ({ default: m.LiveRebalance })))

const gates: { key: GateName; label: string; description: string }[] = [
  { key: 'DATA_GATE', label: 'Data & read-only', description: 'Verified read-only source access' },
  { key: 'DRY_RUN_GATE', label: 'Dry-run workflow', description: 'Non-live proposals require verified workflow coverage' },
  { key: 'SWAP_LIVE_GATE', label: 'Live swap execution', description: 'Transaction equivalence not verified' },
  { key: 'RFQ_LIVE_GATE', label: 'Live RFQ execution', description: 'Settlement equivalence not verified' },
  { key: 'AGENTIC_WALLET_LIVE_GATE', label: 'Live wallet execution', description: 'Wallet runtime integration not verified' },
]

export function App() {
  const root = useRef<HTMLDivElement>(null)
  const [hash, setHash] = useState(window.location.hash)
  useRouteMotion(hash, root)
  const [menuOpen, setMenuOpen] = useState(false)
  useEffect(() => {
    const update = () => { setHash(window.location.hash); setMenuOpen(false) }
    window.addEventListener('hashchange', update)
    return () => window.removeEventListener('hashchange', update)
  }, [])
  const query = useSystemStatus()
  const verified = !query.isError && query.data ? query.data : null
  const system = verified?.system
  const available = Boolean(verified)
  const askReady = system?.gates.DRY_RUN_GATE === 'PASS'
  const showDemo = hash === '#demo-sandbox'
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
  const showAsk = hash === '#ask', showLive = hash === '#live'
  const additional = showOpportunity || showPortfolio || showAutopilot || showSettings || showAudit || showAsk || showLive
  useEffect(() => {
    if (!['#ask', '#system', '#capabilities', '#trust'].includes(hash)) return
    const frame = requestAnimationFrame(() => document.getElementById(hash.slice(1))?.scrollIntoView({ behavior: window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth' }))
    return () => cancelAnimationFrame(frame)
  }, [hash, available])
  const connection = query.isPending ? 'Checking backend' : available ? 'Backend connected' : 'Backend unavailable'

  return <div ref={root} className={`page ${menuOpen ? 'menu-open' : ''}`}>
    <a className="skip-link" href="#main-content" onClick={event => { event.preventDefault(); document.getElementById('main-content')?.focus() }}>Skip to main content</a>
    <header className="site-header">
      <a className="brand" href="#overview" aria-label="Parity Pulse home"><Activity size={27} strokeWidth={1.4} /><span>PARITY PULSE<small>TOKENIZED EQUITY INTELLIGENCE</small></span></a>
      <Button className="mobile-menu refresh-button" aria-expanded={menuOpen} aria-controls="primary-navigation workspace-tools" onClick={() => setMenuOpen(open => !open)}>{menuOpen ? <X size={17} /> : <Menu size={17} />}Menu</Button>
      <nav id="primary-navigation" aria-label="Main navigation" className="primary-navigation">
        {[
          ['#overview', 'Overview', !showDemo && !showTerminal && !showAgentApi && !additional && hash !== '#trust'],
          ['#terminal', 'Markets', showTerminal], ['#trust', 'Trust & Signals', hash === '#trust'],
          ['#opportunity', 'Opportunities', showOpportunity], ['#portfolio', 'Portfolio', showPortfolio],
          ['#demo-sandbox', 'Research Lab', showDemo],
        ].map(([href, label, active]) => <a key={String(href)} href={String(href)} aria-current={active ? 'page' : undefined}>{label}</a>)}
      </nav>
      <MetalLink className="header-action" href="#ask">Compare exposure <ArrowUpRight size={14} /></MetalLink>
    </header>
    <div className="app-layout"><div className="workspace">
      <header className="topbar"><nav id="workspace-tools" aria-label="Workspace tools"><a href="#agent-api" aria-current={showAgentApi ? 'page' : undefined}>Agent API</a><a href="#settings" aria-current={showSettings ? 'page' : undefined}>Data Sources</a><a href="#autopilot" aria-current={showAutopilot ? 'page' : undefined}>Autopilot status</a><a href="#live" aria-current={showLive ? 'page' : undefined}>Execution status</a><a href="#audit" aria-current={showAudit ? 'page' : undefined}>Scorecard / Audit</a></nav><StatusBadge tone={available ? 'green' : 'amber'}>{connection}</StatusBadge></header>
      <main id="main-content" tabIndex={-1}>
        {additional ? (system ? <Suspense fallback={<p role="status">Loading page…</p>}><div key={`${hash}:${system.run_id}:${system.data_mode}`}>
          {showLive ? <LiveRebalance gates={system.gates} /> : showOpportunity ? <OpportunityView mode={system.data_mode} sandbox={system.runtime_mode === 'DEMO'} scanId={scanId} /> : showPortfolio || showAutopilot ? <PortfolioView mode={system.data_mode} autopilot={showAutopilot} /> : showSettings ? <SystemView mode={system.data_mode} /> : showAudit ? <div className="workspace-view"><h1>Scorecard / Audit</h1><ScorecardAudit mode={system.data_mode} initialDecision={decisionId ? decisionId : undefined} /><AuditEvents mode={system.data_mode} /></div> : <><h1>Buy a Stock</h1><AskFlow mode={system.data_mode} /><TrustPanel mode={system.data_mode} /></>}
        </div></Suspense> : <section className="panel demo-unavailable"><h1>Backend state unavailable</h1><p role="status">A verified backend is required. No financial values or cached healthy state are substituted.</p><Button className="refresh-button" disabled={query.isFetching} onClick={() => void query.refetch()}>Retry backend status</Button></section>) : showAgentApi ? <AgentApi /> : showTerminal ? (system ? <Terminal key={`terminal:${system.run_id}:${system.data_mode}`} mode={system.data_mode} /> : <section className="panel"><h1>Terminal</h1><p>A verified backend is required. Analytical values remain unavailable.</p></section>) : showDemo ? <>
          <section className="page-heading" aria-label="Research Lab"><div><div className="eyebrow">PARITY PULSE / SCENARIO RESEARCH</div><h1>Research Lab</h1><p>Explore how evidence becomes a decision, from Trust to a paper position.</p></div><a className="refresh-button" href="#overview">Return to Overview</a></section>
          <DataContext mode="DEMO" />
          {system?.runtime_mode === 'DEMO' && askReady ? <DemoTrustSandbox key={`sandbox:${system.run_id}`} /> : <section className="panel demo-unavailable" aria-label="Research Lab availability">
            <h2>{available ? 'Scenario research is disabled on this backend.' : 'A verified isolated research backend is required.'}</h2>
            <p>This workspace uses isolated synthetic scenarios. No production Trust assessment or live data is substituted.</p>
            <p>Use the existing startup runbook to enable the isolated research runtime. Production gates remain unchanged.</p>
            <Button className="refresh-button" disabled={query.isFetching} onClick={() => { void query.refetch() }}>Refresh status</Button>
          </section>}
        </> : <>
        <section className="overview-hero"><div><div className="eyebrow">EQUITIES / EVIDENCE / EXPOSURE</div><h1>Markets move.<br /> <span>Evidence matters.</span></h1><p>Monitor tokenized equities. Compare representations.<br className="desktop-break" /> Understand the evidence behind every dislocation.</p><div className="hero-actions"><MetalLink className="primary-button" href="#terminal">Explore Markets <ArrowUpRight size={15} /></MetalLink><a className="refresh-button" href="#demo-sandbox">Open Research Lab <ArrowUpRight size={15} /></a></div></div><aside className="hero-summary" aria-label="Workspace context"><span className="eyebrow">YOUR OBSERVATION DESK</span><p className="desk-description">Independent evidence. Clearer exposure.</p><dl><div><dt>Data context</dt><dd>{system ? dataLabel(system.data_mode) : 'Unknown'}</dd></div><div><dt>Execution</dt><dd>{system ? 'Disabled · proposals only' : 'Awaiting verification'}</dd></div><div><dt>US session / next opening</dt><dd>See per-asset market observations</dd></div></dl><a href="#settings" className="text-link">Inspect Data Sources <ArrowUpRight size={14} /></a></aside></section>
        {query.isError && <div role="alert" className="connection-alert"><Radio size={19} /><div><strong>We couldn’t reach a healthy backend.</strong><p>Check that the local backend is running, then refresh. Service values remain unknown until verified.</p></div></div>}
        {query.isPending && <p role="status">Checking workspace connectivity…</p>}
        <MarketSnapshot key={system ? `snapshot:${system.run_id}:${system.data_mode}` : 'unverified-snapshot'} mode={askReady && system ? system.data_mode : undefined} />
        <div className="panels">
          <section className="panel" id="system"><div className="panel-heading"><div><h2>System health</h2><p>The essentials behind your workspace.</p></div><ReadRefresh refetch={query.refetch} busy={query.isFetching} description="Backend health and configuration rechecked."><RefreshCw size={14} />Refresh status</ReadRefresh></div>
            <div className="health-row"><div className="row-icon"><Radio size={17} /></div><div><strong>Backend service</strong><small>FastAPI application</small></div><StatusBadge tone={available ? 'green' : 'amber'}>{query.isPending ? 'Checking' : available ? 'Healthy' : 'Unavailable'}</StatusBadge></div>
            <div className="health-row"><div className="row-icon"><Database size={17} /></div><div><strong>Database</strong><small>Persisted workspace records</small></div><StatusBadge tone={system?.database_status === 'connected' ? 'green' : 'neutral'}>{system?.database_status === 'connected' ? 'Connected' : 'Unknown'}</StatusBadge></div>
            <div className="health-row"><div className="row-icon"><Layers3 size={17} /></div><div><strong>Illustrative dataset</strong><small>{system?.demo_fixture ? 'Synthetic inputs · no execution authority' : 'No synthetic dataset loaded'}</small></div><StatusBadge tone={system?.demo_fixture ? 'green' : 'neutral'}>{system?.demo_fixture ? 'Loaded' : system ? 'Not loaded' : 'Unknown'}</StatusBadge></div>
            <div className="panel-footer"><span>Service version</span><code>{system ? `v${system.service_version}` : 'Unknown'}</code></div>
          </section>
          <section className="panel" id="capabilities"><div className="panel-heading"><div><h2>Capability gates</h2><p>Evidence and execution authority remain separate.</p></div><ShieldCheck size={19} /></div>
            <div className="gate-list">{gates.map(gate => {
              const state = system?.gates[gate.key]
              return <div className="gate-row" key={gate.key}><span className={`gate-symbol ${state === 'PASS' ? 'passed' : ''}`}>{state === 'PASS' ? <Check size={14} /> : <LockKeyhole size={13} />}</span><div><strong>{gate.label}</strong><small>{gate.key === 'DRY_RUN_GATE' && askReady ? 'Verified Ask proposals · simulation unavailable · no live actions' : gate.description}</small></div><span className={`gate-state ${state === 'PASS' ? 'passed' : ''}`}>{state === 'NOT_YET_TESTED' ? 'Not yet tested' : state ? state.toLowerCase() : 'Unknown'}</span></div>
            })}</div>
          </section>
        </div>
        <section className="home-actions" aria-label="Primary product actions"><a href="#ask" className="panel">Compare exposure<small>Discover representations and review an indicative proposal</small></a><a href="#opportunity" className="panel">Find Opportunity<small>Inspect analytical scans; production execution blocked</small></a><a href="#demo-sandbox" className="panel">Research Lab<small>Explore synthetic scenarios and a paper position lifecycle</small></a></section>

        {askReady && system && <AskFlow key={`${system.run_id}:${system.data_mode}`} mode={system.data_mode} />}
        {askReady && system && <TrustPanel key={`trust:${system.run_id}:${system.data_mode}`} mode={system.data_mode} />}
        <section className="scope-note"><div><ShieldCheck size={20} /><div><strong>Evidence first. Execution guarded.</strong><p>No funds move here. Simulation stays required, and execution remains propose-only.</p></div></div><span>ESTIMATES ONLY</span></section>
        <footer className="page-footer"><span>Parity Pulse <span className="footer-dot">·</span> Tokenized equity intelligence</span><span>{system ? 'Review required · simulation required · no live trading' : 'Service status unverified'}</span></footer>
        </>}
      </main>
        <section className="execution-controls" aria-label="Execution authority"><span className="eyebrow">EXECUTION AUTHORITY</span><Button className="refresh-button" disabled={!askReady} onClick={() => { window.location.hash = 'ask' }}><ArrowDownUp size={15} />Direct Exposure</Button><Button className="refresh-button" disabled title="Execution blocked by production safety gates"><Sparkles size={15} />Opportunity<LockKeyhole size={13} /></Button><Button className="refresh-button" disabled title="Execution blocked by production safety gates"><Workflow size={15} />Autopilot<LockKeyhole size={13} /></Button><p>Analytical proposals are available when verified. Live execution remains disabled.</p></section>
    </div></div>
  </div>
}
