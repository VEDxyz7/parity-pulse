import { createContext, useContext } from 'react'

// Presentation state only. API responses remain authoritative for every decision and value.
export const demoStages = ['TRUST', 'OPPORTUNITY', 'RISK', 'ROUTING', 'QUOTE', 'PREPARATION', 'SIMULATION', 'PAPER EXECUTION', 'POSITION', 'MONITOR', 'EXIT', 'P&L', 'SCORECARD'] as const
export type DemoStage = typeof demoStages[number]
export type StageStatus = 'pending' | 'running' | 'pass' | 'rejected' | 'failed'
export interface StageProgress { status: StageStatus; detail: string }
export type PipelineProgress = Record<DemoStage, StageProgress>
export function pendingPipeline(): PipelineProgress {
  return Object.fromEntries(demoStages.map(stage => [stage, { status: 'pending', detail: 'Not run' }])) as PipelineProgress
}
export const DemoPipelineContext = createContext({
  report: (_stage: DemoStage, _status: StageStatus, _detail: string) => {},
  resetFrom: (_stage: DemoStage) => {},
})
export const useDemoPipeline = () => useContext(DemoPipelineContext)

export function DemoPipelineStatus({ progress }: { progress: PipelineProgress }) {
  const stopped = demoStages.find(stage => ['rejected', 'failed'].includes(progress[stage].status))
  return <section className="demo-pipeline" aria-label="Decision pipeline status">
    <h3>Decision pipeline</h3>
    <p>Statuses report completed API outcomes, not production gate approval. Routing is returned by the existing Opportunity and Quote APIs.</p>
    <ol>{demoStages.map(stage => <li key={stage} data-stage={stage} data-status={progress[stage].status}>
      <div><strong>{stage}</strong><span className={`pipeline-status ${progress[stage].status}`}>{progress[stage].status}</span></div>
      <small>{progress[stage].detail}</small>
    </li>)}</ol>
    {stopped && <p className="pipeline-stop" role="status">Pipeline stopped at {stopped}: {progress[stopped].detail}. Pending stages have not run. No real funds will move.</p>}
  </section>
}
