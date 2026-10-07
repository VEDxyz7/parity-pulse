import type { DemoResult, ScenarioId } from './demoSandbox'

interface Safety {
  dataset_type: 'DEMO_FIXTURE'; synthetic: true; production_eligible: false
  data_mode: 'DEMO'; execution_mode: 'DRY_RUN'; approval_mode: 'PROPOSE_ONLY'
  live_trading_enabled: false; require_simulation: true; execution_ready: false; transaction_broadcast: false
  no_broadcast_statement: 'No real transaction was broadcast.'
  quote_status: 'UNAVAILABLE'; preparation_status: 'UNAVAILABLE'; simulation_status: 'UNAVAILABLE'
}
export interface Opportunity extends Safety {
  opportunity_id: string; trust_assessment_id: string; evaluated_at: string; valid_until: string
  ticker: string; issuer: string; chain_id: 'DEMO'; contract: string; symbol: string
  source_trust_classification: string; confidence: string | null; evidence_quality: string
  status: 'NO_OPPORTUNITY' | 'REJECTED_BY_TRUST' | 'REJECTED' | 'ACTIONABLE'; action: 'BUY' | 'NONE'
  reason_codes: string[]; limitations: string[]
  inputs: { target_basis: 'HYPOTHETICAL_SCENARIO_ASSUMPTION'; minimum_net_edge_usd: string }
  economics: null | {
    token_price_usd: string; token_to_share_ratio: string; independent_share_price_usd: string
    effective_price_per_share_usd: string; reference_deviation: string; hypothetical_target_share_price_usd: string
    hypothetical_adjustment_per_share_usd: string; hypothetical_return_fraction: string; requested_notional_usd: string
    gross_hypothetical_edge_usd: string; estimated_slippage_usd: string; fees_usd: string; gas_usd: string
    execution_buffer_usd: string; net_hypothetical_edge_usd: string
    metric_basis: 'HYPOTHETICAL_SCENARIO_ASSUMPTION'; calibrated_prediction: false
  }
}
export interface Risk extends Safety {
  risk_id: string; opportunity_id: string; evaluated_at: string; status: 'PASS' | 'FAIL'
  approved_for_demo_analysis: boolean; reason_codes: string[]; checks: { code: string; passed: boolean; detail: string }[]
  maximum_allowed_notional_usd: string; proposed_notional_usd: string | null
  proposed_token_quantity: string | null; proposed_share_exposure: string | null; stress_loss_usd: string | null
  slippage_tolerance_bps: string; liquidity_notional_cap_usd: string; limitations: string[]
  inputs: { adverse_move_fraction: string; risk_budget_usd: string; budget_usd: string }
  policy: { policy_scope: 'SYNTHETIC_DEMO_ONLY'; min_confidence: string; min_liquidity_percentile: 50 }
}
interface Envelope {
  runtime_mode: 'DEMO'; dataset_type: 'DEMO_FIXTURE'; synthetic: true; production_eligible: false
  scenario_id: ScenarioId; inputs_fixture_sha256: string; production_gates: Record<string, string>
}
export interface OpportunityResult extends Envelope { trust_fixture_sha256: string; opportunity: Opportunity }
export interface RiskResult extends Envelope { risk: Risk }

export function object(v: unknown): v is Record<string, unknown> { return v !== null && typeof v === 'object' && !Array.isArray(v) }
export function marked(v: unknown): v is Record<string, unknown> {
  return object(v) && v.dataset_type === 'DEMO_FIXTURE' && v.synthetic === true && v.production_eligible === false
}
function invalid(): never { throw new Error('Demo analysis unavailable or invalid. No action was approved.') }
export function uuid(v: unknown): boolean { return typeof v === 'string' && /^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i.test(v) }
export function date(v: unknown): boolean { return typeof v === 'string' && /(?:Z|[+-]\d{2}:\d{2})$/.test(v) && Number.isFinite(Date.parse(v)) }
export function decimal(v: unknown): boolean {
  if (typeof v !== 'string' || v.length > 140 || !/^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$/.test(v)) return false
  const [mantissa, exponent = '0'] = v.toLowerCase().split('e')
  return mantissa.replace(/[^0-9]/g, '').length <= 96 && Math.abs(Number(exponent)) <= 36
}
// Schema comparisons only; financial calculations remain in the backend Decimal engines.
function parts(v: string): [bigint, number] {
  const [mantissa, exponent = '0'] = v.toLowerCase().split('e')
  return [BigInt(mantissa.replace('.', '')), Number(exponent) - (mantissa.split('.')[1]?.length ?? 0)]
}
export function compare(a: string, b: string): number {
  const [av, ae] = parts(a), [bv, be] = parts(b)
  const exponent = Math.min(ae, be)
  const left = av * 10n ** BigInt(ae - exponent), right = bv * 10n ** BigInt(be - exponent)
  return left < right ? -1 : left > right ? 1 : 0
}
const requiredChecks = ['OPPORTUNITY_ACTIONABLE', 'TRUST_REQUIRED', 'CONFIDENCE_MINIMUM', 'DECISION_VALID', 'DATA_FRESHNESS',
  'TIMESTAMP_ALIGNMENT', 'RISK_BUDGET_LIMIT', 'DAILY_LOSS_LIMIT', 'TRADE_COUNT_LIMIT', 'COOLDOWN', 'SLIPPAGE_LIMIT',
  'LIQUIDITY_MINIMUM', 'LIQUIDITY_PERCENTILE', 'NET_EDGE_MINIMUM', 'TOKEN_SIZE_METADATA', 'POSITION_CAP', 'BUDGET_CAP',
  'WALLET_LIMIT', 'PORTFOLIO_CAP', 'STRESS_RISK_BUDGET', 'STRESS_DAILY_LOSS', 'LIQUIDITY_POSITION_CAP']
export function strings(v: unknown): v is string[] { return Array.isArray(v) && v.length > 0 && v.length <= 40 && v.every(s => typeof s === 'string' && s.length > 0 && s.length <= 300) }
function safety(v: unknown): v is Record<string, unknown> {
  return marked(v) && v.data_mode === 'DEMO' && v.execution_mode === 'DRY_RUN' && v.approval_mode === 'PROPOSE_ONLY' &&
    v.live_trading_enabled === false && v.require_simulation === true && v.execution_ready === false && v.transaction_broadcast === false &&
    v.no_broadcast_statement === 'No real transaction was broadcast.' && v.quote_status === 'UNAVAILABLE' &&
    v.preparation_status === 'UNAVAILABLE' && v.simulation_status === 'UNAVAILABLE'
}
export function envelope(v: unknown, scenario: ScenarioId): v is Record<string, unknown> {
  if (!marked(v) || v.runtime_mode !== 'DEMO' || v.scenario_id !== scenario || typeof v.inputs_fixture_sha256 !== 'string' ||
    !/^[0-9a-f]{64}$/.test(v.inputs_fixture_sha256) || !object(v.production_gates)) return false
  return ['DATA_GATE', 'DRY_RUN_GATE'].every(k => (v.production_gates as Record<string, unknown>)[k] === 'PASS') &&
    ['TRUST_GATE', 'SWAP_LIVE_GATE', 'RFQ_LIVE_GATE', 'AGENTIC_WALLET_LIVE_GATE'].every(k => (v.production_gates as Record<string, unknown>)[k] === 'BLOCKED') &&
    v.production_gates.OPPORTUNITY_GATE === 'BLOCKED_BY_TRUST'
}
export function parseOpportunity(v: unknown, trust: DemoResult): OpportunityResult {
  if (!envelope(v, trust.scenario_id) || v.trust_fixture_sha256 !== trust.fixture_sha256 || !safety(v.opportunity)) return invalid()
  const o = v.opportunity
  const row = trust.assessment.representations[0]
  if (trust.assessment.representations.length !== 1 || !row || !uuid(o.opportunity_id) || o.trust_assessment_id !== trust.assessment.assessment_id ||
    o.ticker !== row.ticker || o.issuer !== row.issuer || o.contract !== row.contract || o.chain_id !== 'DEMO' || o.symbol !== row.symbol ||
    o.source_trust_classification !== row.classification || o.confidence !== row.confidence || o.evidence_quality !== row.evidence_quality ||
    !date(o.evaluated_at) || !date(o.valid_until) || Date.parse(o.valid_until as string) <= Date.parse(o.evaluated_at as string) ||
    !['NO_OPPORTUNITY', 'REJECTED_BY_TRUST', 'REJECTED', 'ACTIONABLE'].includes(String(o.status)) || !strings(o.reason_codes) || !strings(o.limitations) ||
    !marked(o.inputs) || o.inputs.target_basis !== 'HYPOTHETICAL_SCENARIO_ASSUMPTION' || !decimal(o.inputs.minimum_net_edge_usd)) return invalid()
  if (o.economics !== null) {
    const e = o.economics
    if (!marked(e) || e.metric_basis !== 'HYPOTHETICAL_SCENARIO_ASSUMPTION' || e.calibrated_prediction !== false ||
      !['token_price_usd', 'token_to_share_ratio', 'independent_share_price_usd', 'effective_price_per_share_usd', 'reference_deviation',
        'hypothetical_target_share_price_usd', 'hypothetical_adjustment_per_share_usd', 'hypothetical_return_fraction', 'requested_notional_usd',
        'gross_hypothetical_edge_usd', 'estimated_slippage_usd', 'fees_usd', 'gas_usd', 'execution_buffer_usd', 'net_hypothetical_edge_usd'].every(k => decimal(e[k])) ||
      e.token_price_usd !== row.token_price_usd || e.token_to_share_ratio !== row.token_to_share_ratio) return invalid()
  }
  if ((o.status === 'ACTIONABLE') !== (o.action === 'BUY') || !['BUY', 'NONE'].includes(String(o.action)) ||
    (o.status === 'ACTIONABLE' && (o.source_trust_classification !== 'LIKELY_INFORMATION' || o.economics === null))) return invalid()
  if (o.status === 'ACTIONABLE') {
    const e = o.economics as Record<string, string>
    if (compare(e.net_hypothetical_edge_usd, o.inputs.minimum_net_edge_usd as string) < 0 ||
      compare(e.hypothetical_adjustment_per_share_usd, '0') <= 0) return invalid()
  }
  return v as unknown as OpportunityResult
}
export function parseRisk(v: unknown, opportunity: OpportunityResult): RiskResult {
  if (!envelope(v, opportunity.scenario_id) || v.inputs_fixture_sha256 !== opportunity.inputs_fixture_sha256 || !safety(v.risk)) return invalid()
  const r = v.risk
  if (!uuid(r.risk_id) || r.opportunity_id !== opportunity.opportunity.opportunity_id || !date(r.evaluated_at) ||
    !['PASS', 'FAIL'].includes(String(r.status)) || typeof r.approved_for_demo_analysis !== 'boolean' ||
    !strings(r.reason_codes) || !strings(r.limitations) || !Array.isArray(r.checks) || r.checks.length === 0 || r.checks.length > 40 ||
    !r.checks.every(c => object(c) && typeof c.code === 'string' && typeof c.passed === 'boolean' && typeof c.detail === 'string') ||
    new Set(r.checks.map(c => (c as Record<string, unknown>).code)).size !== r.checks.length ||
    !['maximum_allowed_notional_usd', 'slippage_tolerance_bps', 'liquidity_notional_cap_usd'].every(k => decimal(r[k])) ||
    !['proposed_notional_usd', 'proposed_token_quantity', 'proposed_share_exposure', 'stress_loss_usd'].every(k => r[k] === null || decimal(r[k])) ||
    !marked(r.inputs) || !['adverse_move_fraction', 'risk_budget_usd', 'budget_usd'].every(k => decimal((r.inputs as Record<string, unknown>)[k])) ||
    !marked(r.policy) || r.policy.policy_scope !== 'SYNTHETIC_DEMO_ONLY' || r.policy.min_liquidity_percentile !== 50 ||
    !['LOW', 'MEDIUM', 'HIGH'].includes(String(r.policy.min_confidence))) return invalid()
  const passed = r.status === 'PASS'
  if (!requiredChecks.every(code => (r.checks as Record<string, unknown>[]).some(c => c.code === code))) return invalid()
  if (passed && !r.checks.some(c => (c as Record<string, unknown>).code === 'NONZERO_SIZE')) return invalid()
  if (passed !== r.approved_for_demo_analysis || passed !== r.checks.every(c => (c as Record<string, unknown>).passed === true) ||
    (passed && (opportunity.opportunity.status !== 'ACTIONABLE' || r.proposed_notional_usd === null || r.proposed_token_quantity === null || r.proposed_share_exposure === null || r.stress_loss_usd === null)) ||
    (!passed && ['proposed_notional_usd', 'proposed_token_quantity', 'proposed_share_exposure', 'stress_loss_usd'].some(k => r[k] !== null))) return invalid()
  if (passed && (compare(r.proposed_notional_usd as string, '0') <= 0 || compare(r.proposed_token_quantity as string, '0') <= 0 ||
    compare(r.proposed_notional_usd as string, r.maximum_allowed_notional_usd as string) > 0 ||
    Date.parse(r.evaluated_at as string) < Date.parse(opportunity.opportunity.evaluated_at) ||
    Date.parse(r.evaluated_at as string) >= Date.parse(opportunity.opportunity.valid_until))) return invalid()
  return v as unknown as RiskResult
}
async function post(path: string, body: object, signal: AbortSignal): Promise<unknown> {
  const response = await fetch(path, { method: 'POST', signal, cache: 'no-store', headers: {
    'Content-Type': 'application/json', 'X-Correlation-ID': crypto.randomUUID(),
  }, body: JSON.stringify(body) })
  if (!response.ok) return invalid()
  return response.json()
}
export async function fetchOpportunity(trust: DemoResult, signal: AbortSignal): Promise<OpportunityResult> {
  return parseOpportunity(await post('/api/demo/opportunity', { trust_assessment_id: trust.assessment.assessment_id }, signal), trust)
}
export async function fetchRisk(opportunity: OpportunityResult, signal: AbortSignal): Promise<RiskResult> {
  return parseRisk(await post('/api/demo/risk', { opportunity_id: opportunity.opportunity.opportunity_id }, signal), opportunity)
}
