import type { ExecutionRow, Page, TerminalResult } from './terminal'

type Mode = TerminalResult['data_mode']
export type Evaluation = {
  evaluation_id: string; decision_id: string; scorecard_type: string; origin: string; ticker: string | null
  selected_issuer: string | null; data_mode: Mode; synthetic: boolean; decision_at: string; recorded_at: string
  evidence_asof: string; action: string; outcome: string; control_quality: string; control_quality_basis: string
  abstained: boolean; abstention_scope: string; abstention_reasons: string[]; confidence: string | null
  score: null; score_reason: string; trust_classification: string | null; requested_exposure_usd: string | null
  estimated_share_exposure: string | null; expected_net_edge_usd: string | null; reasons: string[]
  input_digest: string; source_digest: string; run_id: string | null; episode_id: string | null; correlation_id: string | null
  prediction: { predicted_return: string | null; actual_opening_return: string | null; predicted_direction: string | null
    actual_direction: string | null; direction_correct: boolean | null; absolute_magnitude_error: string | null
    classification_correct: null; correctly_ignored_noise: null; noise_suppressed: boolean; label_status: string }
  route: { route_id: string | null; selected_issuer: string | null; basis: string; token_price_usd: string | null
    shares_per_token: string | null; effective_cost_per_share_usd: string | null; liquidity_state: string
    liquidity_usd: string | null; liquidity_source: string | null; trust_state: string | null; tradability: string | null
    selected_cost_per_share_usd: string | null
    minimum_eligible_cost_per_share_usd: string | null; excess_cost_per_share_usd: string | null; minimum_cost_selected: boolean | null
    alternative_costs_per_share_usd: Record<string, string | null>; estimated_costs_usd: string | null
    estimated_fees_usd: string | null; estimated_gas_usd: string | null; estimated_slippage_bps: string | null
    actual_fees_native_base_units: string | null; actual_average_execution_price: string | null; actual_total_cost_usd: null
    actual_slippage_bps: null; simulated_cost_usd: null; provider: string | null; provider_quote_id: string | null; reasons: string[] }
  executions: ExecutionRow[]; allocations: Record<string, string | boolean | number | null>[]
  proposed_actions: Record<string, string | boolean | number | null>[]; paper_pnl: Record<string, string> | null
  broadcast: false; execution_ready: false
}
type Context = Pick<TerminalResult, 'data_mode' | 'generated_at' | 'production_gates' | 'broadcast' | 'execution_ready' | 'execution_mode' | 'approval_mode' | 'limitations'>
export type Scorecards = Context & { page: Page<Evaluation>; metrics: { decision_count: number; directional_samples: number
  directional_accuracy: string | null; high_confidence_samples: number; high_confidence_accuracy: string | null
  classification_accuracy: null; abstention_outcome_accuracy: null; statistical_validation: 'NOT_CLAIMED'; control_quality_counts: Record<string, number> } }
export type AuditEvent = { event_id: string; decision_id: string; timestamp: string; recorded_at: string; event_type: string
  status: string; actor: string; source: string; source_digest: string; correlation_id: string | null; execution_id: string | null
  input_summary: Record<string, string | boolean | number | null>; output_summary: Record<string, string | boolean | number | null>
  reasons: string[]; capture_kind: 'PERSISTED_SOURCE_PROJECTION' }
export type Trace = Context & { decision_id: string; complete_for_recorded_scope: boolean; scorecards: Evaluation[]; events: AuditEvent[]
  stages: { stage: string; status: string; event_ids: string[] }[] }
const gates = { DATA_GATE: 'PASS', DRY_RUN_GATE: 'PASS', TRUST_GATE: 'BLOCKED', OPPORTUNITY_GATE: 'BLOCKED_BY_TRUST', SWAP_LIVE_GATE: 'BLOCKED', RFQ_LIVE_GATE: 'BLOCKED', AGENTIC_WALLET_LIVE_GATE: 'BLOCKED' }
const obj = (v: unknown): v is Record<string, unknown> => typeof v === 'object' && v !== null && !Array.isArray(v)
const stamp = (v: unknown) => typeof v === 'string' && /(?:Z|[+-]\d{2}:\d{2})$/.test(v) && Number.isFinite(Date.parse(v))
const strings = (v: unknown) => Array.isArray(v) && v.every(s => typeof s === 'string')
const exact = (v: unknown) => v === null || typeof v === 'string' && v.length <= 1000 && /^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$/.test(v)
const finance = new Set(['token_price_usd','shares_per_token','effective_cost_per_share_usd','liquidity_usd','gross_pnl_usd','costs_usd','net_pnl_usd','return_pct','entry_cost_basis_usd','requested_exposure_usd','estimated_share_exposure','expected_net_edge_usd','predicted_return','actual_opening_return','absolute_magnitude_error','selected_cost_per_share_usd','minimum_eligible_cost_per_share_usd','excess_cost_per_share_usd','estimated_costs_usd','estimated_fees_usd','estimated_gas_usd','estimated_slippage_bps','actual_average_execution_price','actual_total_cost_usd','actual_slippage_bps','simulated_cost_usd','directional_accuracy','high_confidence_accuracy','notional_usd','target_weight','decision_time_weight','drift','drift_band','realized_net_pnl_usd','realized_gross_pnl_usd','network_fee_estimate_usd','average_execution_price'])
export function parseEvaluation<T extends Scorecards | Trace>(value: unknown, mode: Mode, trace = false): T {
  const fail = () => { throw new Error('Evaluation evidence could not be verified.') }
  if (!obj(value) || value.data_mode !== mode || value.broadcast !== false || value.execution_ready !== false || value.execution_mode !== 'DRY_RUN' || value.approval_mode !== 'PROPOSE_ONLY' || !stamp(value.generated_at) || !strings(value.limitations) || !obj(value.production_gates) || !Object.entries(gates).every(([k,v]) => (value.production_gates as Record<string,unknown>)[k] === v)) return fail()
  if (trace) {
    if (typeof value.decision_id !== 'string' || !Array.isArray(value.events) || value.events.length > 2000 || !Array.isArray(value.stages) || value.stages.length > 25 || !Array.isArray(value.scorecards) || typeof value.complete_for_recorded_scope !== 'boolean') return fail()
    for (const e of value.events) if (!obj(e) || !stamp(e.timestamp) || !stamp(e.recorded_at) || !['event_id','event_type','status','actor','source','source_digest'].every(k => typeof e[k] === 'string') || e.decision_id !== value.decision_id || e.capture_kind !== 'PERSISTED_SOURCE_PROJECTION' || !obj(e.input_summary) || !obj(e.output_summary) || !strings(e.reasons)) return fail()
    for (const s of value.stages) if (!obj(s) || typeof s.stage !== 'string' || !['RECORDED','UNAVAILABLE_OR_NOT_APPLICABLE'].includes(String(s.status)) || !strings(s.event_ids)) return fail()
  } else if (!obj(value.page) || !Array.isArray(value.page.items) || value.page.items.length > 100 || !Number.isInteger(value.page.offset) || !Number.isInteger(value.page.limit) || typeof value.page.has_more !== 'boolean' || !strings(value.page.reasons) || !obj(value.metrics) || typeof value.metrics.decision_count !== 'number' || !obj(value.metrics.control_quality_counts) || value.metrics.statistical_validation !== 'NOT_CLAIMED') return fail()
  const cards = trace ? value.scorecards as unknown[] : (value.page as Record<string, unknown>).items as unknown[]
  for (const c of cards) {
    if (!obj(c) || c.data_mode !== mode || c.broadcast !== false || c.execution_ready !== false || c.score !== null || !['OPPORTUNITY','DIRECT_EXPOSURE','AUTOPILOT'].includes(String(c.scorecard_type)) || !['CORRECT_ACTION','INCORRECT_ACTION','CORRECT_ABSTENTION','INCORRECT_ABSTENTION','UNSCORABLE'].includes(String(c.control_quality)) || !['evaluation_id','decision_id','origin','action','outcome','control_quality_basis','input_digest','source_digest'].every(k => typeof c[k] === 'string') || !stamp(c.decision_at) || !stamp(c.evidence_asof) || typeof c.abstained !== 'boolean' || typeof c.synthetic !== 'boolean' || !strings(c.reasons) || !strings(c.abstention_reasons) || !obj(c.route) || !obj(c.route.alternative_costs_per_share_usd) || !Object.values(c.route.alternative_costs_per_share_usd).every(exact) || !obj(c.prediction) || !Array.isArray(c.executions) || !Array.isArray(c.allocations) || !Array.isArray(c.proposed_actions)) return fail()
    for (const key of ['classification_correct','correctly_ignored_noise']) if (c.prediction[key] !== null) return fail()
  }
  let nodes = 0
  function bounded(v: unknown, depth = 0) {
    if (++nodes > 100000 || depth > 30) return fail()
    if (Array.isArray(v)) { if (v.length > 2000) return fail(); v.forEach(x => bounded(x, depth + 1)); return }
    if (!obj(v)) return
    for (const [k, entry] of Object.entries(v)) {
      if (['chainofthought','hiddenreasoning','reasoningsummary','privatekey','seedphrase','apikey','secretkey','authorization','usersignature','typeddatatosign','calldata'].includes(k.toLowerCase().replace(/[^a-z]/g, ''))) return fail()
      if (mode === 'LIVE_READ_ONLY' && (k === 'synthetic' && entry === true || k === 'data_mode' && entry === 'DEMO')) return fail()
      if (finance.has(k) && !exact(entry)) return fail()
      bounded(entry, depth + 1)
    }
  }
  bounded(value)
  return value as unknown as T
}
export async function fetchEvaluation<T extends Scorecards | Trace>(mode: Mode, params: URLSearchParams, signal: AbortSignal, decision?: string): Promise<T> {
  if (decision && !/^[A-Za-z0-9_.:-]{1,160}$/.test(decision)) throw new Error('Invalid decision reference.')
  const path = decision ? `/api/audit/decisions/${encodeURIComponent(decision)}` : '/api/scorecard'
  const controller = new AbortController(), abort = () => controller.abort()
  signal.addEventListener('abort', abort, { once: true }); if (signal.aborted) abort()
  const timer = window.setTimeout(abort, 8000)
  try {
    const response = await fetch(`${path}?${params}`, { method: 'GET', signal: controller.signal, cache: 'no-store', headers: { 'X-Correlation-ID': crypto.randomUUID() } })
    if (!response.ok) throw new Error('Evaluation unavailable.')
    return parseEvaluation<T>(await response.json(), mode, !!decision)
  } finally { clearTimeout(timer); signal.removeEventListener('abort', abort) }
}
