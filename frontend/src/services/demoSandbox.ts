import { parseTrust, type TrustResult } from './trust'

export type ScenarioId = 'steady' | 'thin-move' | 'supported-move'
export interface DemoScenario {
  scenario_id: ScenarioId; title: string; description: string
  dataset_type: 'DEMO_FIXTURE'; synthetic: true; production_eligible: false
}
export interface DemoResult extends DemoScenario {
  runtime_mode: 'DEMO'; fixture_version: 'demo-trust-1'; fixture_sha256: string
  fixture_episode_count: number; fixture_preceding_sample_count: number
  assessment: TrustResult
  production_gates: Record<string, string>
  news_inputs: { dataset_type: 'DEMO_FIXTURE'; synthetic: true; production_eligible: false;
    record: { data_mode: 'DEMO'; data_quality: 'DEMO'; source: 'DEMO_NEWS'; headline: string; published_timestamp: string; ingestion_timestamp: string } }[]
}
const ids = ['steady', 'thin-move', 'supported-move']
function object(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}
function marked(value: unknown): value is Record<string, unknown> {
  return object(value) && value.dataset_type === 'DEMO_FIXTURE' && value.synthetic === true && value.production_eligible === false
}
function scenario(value: unknown): value is Record<string, unknown> {
  return marked(value) && ids.includes(String(value.scenario_id)) && typeof value.title === 'string' &&
    value.title.length > 0 && value.title.length <= 80 && typeof value.description === 'string' && value.description.length <= 300
}
function invalid(): never { throw new Error('Demo evidence could not be verified. No classification was substituted.') }
function newsInput(value: unknown): boolean {
  if (!marked(value) || !object(value.record)) return false
  const record = value.record
  return record.data_mode === 'DEMO' && record.data_quality === 'DEMO' && record.source === 'DEMO_NEWS' &&
    typeof record.headline === 'string' && ['published_timestamp', 'ingestion_timestamp'].every(key =>
      typeof record[key] === 'string' && /(?:Z|[+-]\d{2}:\d{2})$/.test(record[key] as string) &&
      Number.isFinite(Date.parse(record[key] as string)))
}
export function parseDemoCatalog(value: unknown): DemoScenario[] {
  if (!marked(value) || value.runtime_mode !== 'DEMO' || !Array.isArray(value.scenarios) ||
    value.scenarios.length !== 3 || !value.scenarios.every(scenario) ||
    new Set(value.scenarios.map(row => row.scenario_id)).size !== 3) return invalid()
  return value.scenarios as unknown as DemoScenario[]
}
export function parseDemoResult(value: unknown, requested: ScenarioId): DemoResult {
  if (!scenario(value) || value.scenario_id !== requested || value.runtime_mode !== 'DEMO' ||
    value.fixture_version !== 'demo-trust-1' || typeof value.fixture_sha256 !== 'string' || !/^[0-9a-f]{64}$/.test(value.fixture_sha256) ||
    !Number.isInteger(value.fixture_episode_count) || (value.fixture_episode_count as number) < 0 || (value.fixture_episode_count as number) > 60 ||
    !Number.isInteger(value.fixture_preceding_sample_count) || (value.fixture_preceding_sample_count as number) < 0 ||
    (value.fixture_preceding_sample_count as number) > 32 || !object(value.production_gates) ||
    !Array.isArray(value.news_inputs) || value.news_inputs.length > 10 || !value.news_inputs.every(newsInput)) return invalid()
  const gates = value.production_gates
  if (gates.DATA_GATE !== 'PASS' || gates.DRY_RUN_GATE !== 'PASS' || gates.TRUST_GATE !== 'BLOCKED' ||
    gates.OPPORTUNITY_GATE !== 'BLOCKED_BY_TRUST' || gates.SWAP_LIVE_GATE !== 'BLOCKED' ||
    gates.RFQ_LIVE_GATE !== 'BLOCKED' || gates.AGENTIC_WALLET_LIVE_GATE !== 'BLOCKED') return invalid()
  const assessment = parseTrust(value.assessment, 'DEMO')
  for (const row of assessment.representations) {
    if (!row.contract.startsWith('demo:') || !['SYNTHETIC_DEMO', 'INSUFFICIENT'].includes(row.evidence_quality)) return invalid()
    if (row.features !== null && row.features !== undefined) {
      const feature: unknown = row.features
      if (!object(feature) || !['volume_24h_usd', 'liquidity_usd', 'persistence_seconds', 'time_to_open_seconds',
        'starting_deviation', 'ending_deviation', 'absolute_deviation'].every(key =>
        typeof feature[key] === 'string' && /^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$/.test(feature[key] as string)) ||
        !['asof', 'available_at'].every(key => typeof feature[key] === 'string' &&
          /(?:Z|[+-]\d{2}:\d{2})$/.test(feature[key] as string) && Number.isFinite(Date.parse(feature[key] as string))) ||
        !['NO_RELEVANT_NEWS', 'RELEVANT_NEWS', 'CORROBORATING', 'CONFLICTING', 'PARTIAL', 'UNAVAILABLE'].includes(String(feature.news_state))) return invalid()
    } else if (row.classification !== 'INSUFFICIENT_EVIDENCE') return invalid()
  }
  return { ...value, assessment } as unknown as DemoResult
}
async function read(path: string, signal: AbortSignal): Promise<unknown> {
  const response = await fetch(path, { method: 'GET', signal, cache: 'no-store', headers: { 'X-Correlation-ID': crypto.randomUUID() } })
  if (!response.ok) return invalid()
  return response.json()
}
export async function fetchDemoCatalog(signal: AbortSignal): Promise<DemoScenario[]> {
  return parseDemoCatalog(await read('/api/demo/trust/scenarios', signal))
}
export async function fetchDemoScenario(id: ScenarioId, signal: AbortSignal): Promise<DemoResult> {
  if (!ids.includes(id)) return invalid()
  return parseDemoResult(await read(`/api/demo/trust/scenarios/${id}`, signal), id)
}
