import { Button } from '../ui/Button'
import { useCallback, useEffect, useRef, useState } from 'react'
import { fetchDemoCatalog, fetchDemoScenario, type DemoResult, type DemoScenario, type ScenarioId } from '../services/demoSandbox'
import { TrustEvidence } from './TrustEvidence'
import { DemoOpportunityFlow } from './DemoOpportunityFlow'
import { DemoPipelineContext, DemoPipelineStatus, demoStages, pendingPipeline, type DemoStage, type StageStatus } from './DemoPipeline'

export function DemoTrustSandbox() {
  const [scenarios, setScenarios] = useState<DemoScenario[]>([])
  const [selected, setSelected] = useState<ScenarioId>('steady')
  const [result, setResult] = useState<DemoResult | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [progress, setProgress] = useState(pendingPipeline)
  const report = useCallback((stage: DemoStage, status: StageStatus, detail: string) => {
    setProgress(current => ({ ...current, [stage]: { status, detail } }))
  }, [])
  const resetFrom = useCallback((stage: DemoStage) => {
    setProgress(current => ({ ...current, ...Object.fromEntries(demoStages.slice(demoStages.indexOf(stage)).map(key => [key, { status: 'pending', detail: 'Not run' }])) }))
  }, [])
  const pending = useRef<AbortController | null>(null)
  useEffect(() => {
    const controller = new AbortController()
    let cancelled = false
    const timer = setTimeout(() => controller.abort(), 60_000)
    void fetchDemoCatalog(controller.signal).then(rows => {
      if (!controller.signal.aborted) setScenarios(rows)
    }).catch(() => { if (!cancelled) setError('Scenario fixtures unavailable. No live data was substituted.') }).finally(() => clearTimeout(timer))
    return () => { cancelled = true; clearTimeout(timer); controller.abort(); pending.current?.abort(); pending.current = null }
  }, [])
  async function run(event: React.FormEvent) {
    event.preventDefault()
    pending.current?.abort()
    const controller = new AbortController()
    pending.current = controller
    setResult(null); setError(''); setBusy(true)
    resetFrom('TRUST'); report('TRUST', 'running', 'Evaluating the selected synthetic fixture')
    const timer = setTimeout(() => controller.abort(), 60_000)
    try {
      const response = await fetchDemoScenario(selected, controller.signal)
      if (pending.current === controller && !controller.signal.aborted) {
        setResult(response)
        const rows = response.assessment.representations
        report('TRUST', rows.length > 0 && rows.every(row => row.classification !== 'INSUFFICIENT_EVIDENCE') ? 'pass' : 'rejected', rows.map(row => `${row.classification}: ${row.reason_codes.join(' · ')}`).join('; ') || 'No representation evidence returned')
      }
    } catch {
      if (pending.current === controller) {
        setError('Scenario evidence unavailable or invalid. No classification was substituted.')
        report('TRUST', 'failed', 'Scenario evidence unavailable or invalid; no fallback was used')
      }
    } finally {
      clearTimeout(timer)
      if (pending.current === controller) setBusy(false)
    }
  }
  return <DemoPipelineContext.Provider value={{ report, resetFrom }}><section className="panel trust-panel demo-sandbox" id="demo-sandbox" aria-label="Scenario Trust workbench">
    <div className="panel-heading"><div><h2>Scenario workbench</h2><p>Illustrative data · synthetic scenarios, not live market data</p></div></div>
    <p className="demo-funds-notice"><strong>NO REAL FUNDS WILL MOVE</strong></p>
    <p className="trust-note">Synthetic scenarios use the existing deterministic Trust rules. Production Trust remains BLOCKED. These results are demonstrations, not historical replay or execution authority.</p>
    <form className="trust-form" onSubmit={event => { void run(event) }}>
      <label htmlFor="demo-scenario">Scenario</label>
      <select id="demo-scenario" value={selected} disabled={scenarios.length === 0} onChange={event => {
        pending.current?.abort(); pending.current = null; setBusy(false); setResult(null); setError('')
        resetFrom('TRUST')
        setSelected(event.target.value as ScenarioId)
      }}>{scenarios.map(row => <option key={row.scenario_id} value={row.scenario_id}>{row.title}</option>)}</select>
      <div className="demo-scenario-buttons" role="group" aria-label="Research scenarios">{scenarios.map(row => <Button
        key={row.scenario_id} type="button" className="refresh-button" aria-pressed={selected === row.scenario_id}
        onClick={() => { pending.current?.abort(); pending.current = null; setBusy(false); setResult(null); setError(''); resetFrom('TRUST'); setSelected(row.scenario_id) }}
      >{row.title}</Button>)}</div>
      <Button type="submit" className="refresh-button" disabled={busy || scenarios.length === 0}>{busy ? 'Evaluating scenario evidence…' : 'Run scenario'}</Button>
    </form>
    <p>{scenarios.find(row => row.scenario_id === selected)?.description}</p>
    {error && <p role="alert">{error}</p>}
    <DemoPipelineStatus progress={progress} />
    {result && <>
      <details><summary>Dataset identity &amp; provenance</summary><p>Dataset: {result.dataset_type} · Synthetic: true · Production eligible: false</p></details>
      <p>Fixed synthetic clock: <time>{result.assessment.evaluated_at}</time> · Fixture version: {result.fixture_version}</p>
      <p>Fixture baseline episodes: {result.fixture_episode_count} · Preceding synthetic observations: {result.fixture_preceding_sample_count}</p>
      <details><summary>Fixture SHA256</summary><code style={{ overflowWrap: 'anywhere' }}>{result.fixture_sha256}</code></details>
      {result.news_inputs.map(input => <p key={input.record.headline}>Synthetic headline: {input.record.headline}</p>)}
      {result.assessment.representations.map(row => row.features && <div className="demo-feature-evidence" key={row.contract}>
        <h3>Evidence/features supplied to the classifier</h3>
        <dl className="trust-facts">
          <div><dt>24h volume / USD</dt><dd>{row.features.volume_24h_usd}</dd></div>
          <div><dt>Persistence / seconds</dt><dd>{row.features.persistence_seconds}</dd></div>
          <div><dt>Time to next open / seconds</dt><dd>{row.features.time_to_open_seconds}</dd></div>
          <div><dt>Starting deviation</dt><dd>{row.features.starting_deviation}</dd></div>
          <div><dt>Ending deviation</dt><dd>{row.features.ending_deviation}</dd></div>
          <div><dt>Feature available at</dt><dd>{row.features.available_at}</dd></div>
        </dl>
        <details><summary>Baseline, analogue and news evidence</summary><pre>{JSON.stringify({ baseline: row.baseline, analogues: row.analogues, news: row.news }, null, 2)}</pre></details>
      </div>)}
      <TrustEvidence result={result.assessment} />
      <DemoOpportunityFlow key={result.assessment.assessment_id} trust={result} />
      <p>Production Trust and Opportunity remain blocked. All live execution remains blocked.</p>
    </>}
  </section></DemoPipelineContext.Provider>
}
