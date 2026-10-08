// Authoritative values are exact strings from the backend. No financial arithmetic here.
export type Page<T> = { items: T[]; limit: number; offset: number; has_more: boolean; reasons: string[] }
export type TrustRow = {
  ticker: string; issuer: string | null; contract: string | null; assessment_id: string | null
  assessed_at: string | null; age_seconds: string | null; freshness: string; classification: string
  confidence: string | null; regime: string | null; reasons: string[]
  stored_evidence: { classification: string; news: { state: string; coverage: string; article_ids: string[] }
    baseline: { status: string; sample_count: number }; analogues: { status: string; retrieved_sample_count: number }
    missing_evidence: string[] } | null
}
export type IssuerRow = {
  ticker: string; company: string; issuer: string; token: string; contract: string; chain_id: string
  token_price_usd: string | null; token_to_share_ratio: string; effective_price_per_share_usd: string | null
  independent_equity_price_usd: string | null; deviation_percent: string | null; spread_usd_per_share: string | null
  ratio_observed_at: string; ratio_source_timestamp: string | null; freshness: string
  eligibility: string; tradable: boolean | null; market_state: string; regime: string; reasons: string[]
  reference: { status: string; reference_asof: string | null; timestamp_skew_seconds: string | null; reason_codes: string[] }
  liquidity: { status: string; liquidity_usd: string | null; volume_24h_usd: string | null }
  trust: TrustRow; route_status: string; provider_route_id: null
  observations: { source: string; digest: string; observed_at: string | null; available_at: string; data_quality: string; provider_identifier: string }[]
}
export type AgentRow = {
  run_id: string; timestamp: string; status: string; decision: { decision: string; reasons: string[] }
  agents: { agent: string; status: string; confidence: string; provider: string; model: string
    evidence_refs: string[]; reasons: string[]; conflicts: string[]; output: object }[]
  evidence: { evidence_id: string; source: string; observed_at: string; available_at: string; digest: string }[]
  memory: { memory_id: string; stock: string; action: string; trust_state: string }[]
}
export type ExecutionRow = {
  execution_id: string; lifecycle_state: string; category: string; source: string; synthetic: boolean
  actual_completed_trade: boolean; execution_mode: string | null; provider: string | null; quote_id: string | null
  simulation_status: string | null; fingerprint: string | null; created_at: string; updated_at: string
  requested_base_units: string | null; quoted_output_base_units: string | null; filled_base_units: string | null
  remaining_base_units: string | null; average_execution_price: string | null; network_fee_estimate_usd: string | null
  actual_fees_native_base_units: string | null; estimated_gas_provider_units: string | null; quote_latency_seconds: string | null
  realized_gross_pnl_usd: string | null; realized_net_pnl_usd: string | null; position_id: string | null
  position_state: string | null; reasons: string[]
}
export type EpisodeRow = {
  episode_id: string; run_id: string; dataset_digest: string; ticker: string; issuer: string; contract: string
  decision_at: string; query_as_of: string; regime: string; evidence_kind: string; eligibility: string; trust_state: string
  deviation: string | null; volume_usd: string | null; liquidity_usd: string | null; feature_available_at: string | null
  prediction: { status: string; predicted_return: string | null; sample_count: number; reason: string }
  retrieval: { status: string; retrieved_count: number; matches: { episode_id: string }[] }
  outcome_state: string; opening_outcome: { opening_return: string | null; available_at: string | null } | null
  reasons: string[]; provenance: { source: string; available_at: string }[]
}
export type TerminalResult = {
  schema_version: 'terminal-1'; data_mode: 'DEMO' | 'LIVE_READ_ONLY'; generated_at: string
  run_id: string; request_id: string; correlation_id: string; production_gates: Record<string, string>
  execution_mode: 'DRY_RUN'; execution_ready: false; broadcast: false; approval_mode: 'PROPOSE_ONLY'
  issuers: Page<IssuerRow>; trust: Page<TrustRow>; agents: Page<AgentRow>
  executions: Page<ExecutionRow>; episodes: Page<EpisodeRow>
  portfolio: { config_version: number | null; pending_plan_id: string | null; status: string; reasons: string[] }
  limitations: string[]
}
const gates = { DATA_GATE: 'PASS', DRY_RUN_GATE: 'PASS', TRUST_GATE: 'BLOCKED', OPPORTUNITY_GATE: 'BLOCKED_BY_TRUST', SWAP_LIVE_GATE: 'BLOCKED', RFQ_LIVE_GATE: 'BLOCKED', AGENTIC_WALLET_LIVE_GATE: 'BLOCKED' }
const financial = new Set(['token_price_usd', 'token_to_share_ratio', 'effective_price_per_share_usd', 'independent_equity_price_usd', 'comparable_token_value_usd', 'deviation', 'absolute_deviation', 'deviation_percent', 'spread_usd_per_share', 'age_seconds', 'liquidity_usd', 'volume_24h_usd', 'volume_usd', 'predicted_return', 'opening_return', 'average_execution_price', 'network_fee_estimate_usd', 'quote_latency_seconds', 'realized_gross_pnl_usd', 'realized_net_pnl_usd'])
const object = (v: unknown): v is Record<string, unknown> => typeof v === 'object' && v !== null && !Array.isArray(v)
const timestamp = (v: unknown) => typeof v === 'string' && /(?:Z|[+-]\d{2}:\d{2})$/.test(v) && Number.isFinite(Date.parse(v))
const strings = (v: unknown) => Array.isArray(v) && v.every(x => typeof x === 'string')
const exact = (v: unknown) => v === null || typeof v === 'string' && v.length <= 1000 && /^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$/.test(v)
export function parseTerminal(value: unknown, mode: TerminalResult['data_mode']): TerminalResult {
  const fail = () => { throw new Error('Terminal evidence could not be verified.') }
  if (!object(value) || value.schema_version !== 'terminal-1' || value.data_mode !== mode ||
    value.execution_mode !== 'DRY_RUN' || value.approval_mode !== 'PROPOSE_ONLY' || value.execution_ready !== false || value.broadcast !== false ||
    !timestamp(value.generated_at) || !['run_id', 'request_id', 'correlation_id'].every(k => typeof value[k] === 'string') ||
    !object(value.production_gates) || !Object.entries(gates).every(([k,v]) => (value.production_gates as Record<string,unknown>)[k] === v) ||
    !strings(value.limitations) || !object(value.portfolio) || typeof value.portfolio.status !== 'string' || !strings(value.portfolio.reasons)) return fail()
  for (const name of ['issuers', 'trust', 'agents', 'executions', 'episodes']) {
    const p = value[name]
    if (!object(p) || !Array.isArray(p.items) || p.items.length > 100 || !Number.isInteger(p.limit) || !Number.isInteger(p.offset) || typeof p.has_more !== 'boolean' || !strings(p.reasons)) return fail()
    for (const row of p.items) {
      if (!object(row)) return fail()
      if (name === 'issuers' && (!['ticker','issuer','token','contract','company','chain_id','freshness','eligibility','market_state','regime'].every(k => typeof row[k] === 'string') || !['token_price_usd','token_to_share_ratio','effective_price_per_share_usd','independent_equity_price_usd','deviation_percent','spread_usd_per_share'].every(k => exact(row[k])) || row.token_to_share_ratio === null || !Array.isArray(row.observations) || !object(row.reference) || !object(row.liquidity) || !object(row.trust) || !strings(row.reasons))) return fail()
      if (name === 'trust' && (!['ticker','freshness','classification'].every(k => typeof row[k] === 'string') || !strings(row.reasons))) return fail()
      if (name === 'agents' && (!Array.isArray(row.agents) || row.agents.length > 6 || !Array.isArray(row.evidence) || row.evidence.length > 64 || !Array.isArray(row.memory) || !object(row.decision))) return fail()
      if (name === 'executions' && (!['execution_id','category','lifecycle_state'].every(k => typeof row[k] === 'string') || typeof row.actual_completed_trade !== 'boolean' || typeof row.synthetic !== 'boolean' || !strings(row.reasons))) return fail()
      if (name === 'episodes' && (!timestamp(row.decision_at) || !object(row.prediction) || !object(row.retrieval) || !Array.isArray(row.retrieval.matches) || !strings(row.reasons))) return fail()
    }
  }
  function bounded(v: unknown, depth = 0) {
    if (depth > 25) return fail()
    if (Array.isArray(v)) { if (v.length > 500) return fail(); v.forEach(x => bounded(x, depth + 1)); return }
    if (!object(v)) return
    for (const [k, entry] of Object.entries(v)) {
      if (['chain_of_thought', 'hidden_reasoning', 'private_key', 'userSignature', 'typedDataToSign'].includes(k)) return fail()
      if (mode === 'LIVE_READ_ONLY' && ((k === 'data_mode' && entry === 'DEMO') || (k === 'data_quality' && entry === 'DEMO') || (k === 'synthetic' && entry === true) || (k === 'evidence_kind' && entry === 'SYNTHETIC_TEST'))) return fail()
      if (financial.has(k) && !(entry === null || typeof entry === 'string' && entry.length <= 1000 && /^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$/.test(entry))) return fail()
      bounded(entry, depth + 1)
    }
  }
  bounded(value)
  return value as unknown as TerminalResult
}
export async function fetchTerminal(mode: TerminalResult['data_mode'], ticker: string, offset: number, signal: AbortSignal): Promise<TerminalResult> {
  if (ticker && !/^[A-Z0-9][A-Z0-9.\-]{0,14}$/.test(ticker)) throw new Error('Enter a supported ticker.')
  const params = new URLSearchParams({ limit: '25', offset: String(offset), ...(ticker ? { ticker } : {}) })
  const controller = new AbortController()
  const abort = () => controller.abort()
  signal.addEventListener('abort', abort, { once: true })
  if (signal.aborted) controller.abort()
  const timeout = window.setTimeout(abort, 8000)
  try {
    const response = await fetch(`/api/terminal?${params}`, { method: 'GET', signal: controller.signal, cache: 'no-store', headers: { 'X-Correlation-ID': crypto.randomUUID() } })
    if (!response.ok) throw new Error('Terminal records unavailable.')
    return parseTerminal(await response.json(), mode)
  } finally { clearTimeout(timeout); signal.removeEventListener('abort', abort) }
}
