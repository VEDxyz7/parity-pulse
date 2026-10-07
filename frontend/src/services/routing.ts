import { compare, date, decimal, object, uuid } from './demoOpportunity'

export interface RouteIdentity { underlying: string; issuer: string; chain_id: string; contract: string; token: string }
export interface RouteCandidate {
  candidate_id: string; eligible: boolean; rank: number | null; rejection_reasons: string[]; limitations: string[]
  effective_cost_per_share_usd: string | null; estimated_costs_usd: string | null; all_in_cost_per_share_usd: string | null; ranking_cost_per_share_usd: string | null
  liquidity_state: 'AVAILABLE' | 'UNAVAILABLE' | 'UNVERIFIED' | 'STALE'; cost_state: 'AVAILABLE' | 'UNAVAILABLE' | 'UNVERIFIED' | 'STALE'
  trust_state: string; tradability: 'TRADABLE' | 'NOT_TRADABLE' | 'UNKNOWN'
  inputs: {
    identity: RouteIdentity; data_mode: 'DEMO' | 'LIVE'; token_price_usd: string | null; token_to_share_ratio: string
    price_source: string; price_timestamp: string | null; price_quality: string; ratio_source: string; ratio_observed_at: string
    supported: boolean; normalization_eligible: boolean; market_state: string; tradable: boolean | null
    liquidity_usd: string | null; liquidity_source: string | null; liquidity_timestamp: string | null; volume_usd: string | null
    fees_usd: string | null; gas_usd: string | null; slippage_bps: string | null; cost_source: string | null; cost_timestamp: string | null
    trust_state: string; trust_source: string | null; trust_timestamp: string | null; trust_assessment_id: string | null
    risk_state: string; risk_id: string | null; risk_timestamp: string | null; risk_source: string | null; risk_max_notional_usd: string | null
    route_available: boolean | null; route_support: string
  }
}
export interface RouteDecision {
  schema_version: 'routing-1'; route_id: string; underlying: string | null; requested_notional_usd: string | null; data_mode: 'DEMO' | 'LIVE'
  source: 'DETERMINISTIC_ROUTER'; timestamp: string; valid_until: string; status: 'ROUTE_SELECTED' | 'NO_ROUTE'
  selected_representation: RouteIdentity | null; issuer: string | null; candidates: RouteCandidate[]; selected_candidate: RouteCandidate | null
  ranking_basis: 'TOKEN_PRICE_ONLY' | 'ALL_IN_ESTIMATE' | 'NONE'; reason_codes: string[]; explanation: string
  policy: { version: 'routing-1'; purpose: 'INDICATIVE_EXPOSURE' | 'OPPORTUNITY'; require_costs: boolean; require_liquidity: boolean; require_trust: boolean; require_risk: boolean
    min_liquidity_usd: string | null; max_slippage_bps: string | null; max_age_seconds: 120; ranking: 'MIN_EXACT_EFFECTIVE_COST_THEN_IDENTITY'; weights: null
    unknown_cost_behavior: 'COMMON_PRICE_ONLY_BASIS_OR_REJECT_IF_REQUIRED' }
  execution_ready: false; transaction_broadcast: false; live_trading_enabled: false; execution_mode: 'DRY_RUN'; provider_execution_mode: null
  no_broadcast_statement: 'No real transaction was broadcast.'
}
function invalid(): never { throw new Error('Route decision could not be verified. No execution is available.') }
function strings(v: unknown): v is string[] { return Array.isArray(v) && v.length <= 80 && v.every(s => typeof s === 'string' && s.length > 0 && s.length < 500) }
function identity(v: unknown): v is Record<string, string> { return object(v) && ['underlying','issuer','chain_id','contract','token'].every(k => typeof v[k] === 'string' && v[k].length > 0) }
function equal(a: unknown, b: unknown): boolean {
  if (object(a) && object(b)) return Object.keys(a).length === Object.keys(b).length && Object.keys(a).every(k => equal(a[k], b[k]))
  if (Array.isArray(a) && Array.isArray(b)) return a.length === b.length && a.every((x,i) => equal(x,b[i]))
  return a === b
}
export function parseRoute(value: unknown, mode: 'DEMO' | 'LIVE', underlying: string | null, budget?: string | null, purpose: 'INDICATIVE_EXPOSURE' | 'OPPORTUNITY' = 'INDICATIVE_EXPOSURE'): RouteDecision {
  if (!object(value) || value.schema_version !== 'routing-1' || !uuid(value.route_id) || value.underlying !== underlying || value.data_mode !== mode ||
    value.source !== 'DETERMINISTIC_ROUTER' || !date(value.timestamp) || !date(value.valid_until) || Date.parse(value.valid_until as string) < Date.parse(value.timestamp as string) ||
    !['ROUTE_SELECTED','NO_ROUTE'].includes(String(value.status)) || value.execution_ready !== false || value.transaction_broadcast !== false || value.live_trading_enabled !== false ||
    value.execution_mode !== 'DRY_RUN' || value.provider_execution_mode !== null || value.no_broadcast_statement !== 'No real transaction was broadcast.' ||
    !(value.requested_notional_usd === null || decimal(value.requested_notional_usd)) || (budget !== undefined && value.requested_notional_usd !== budget) ||
    !strings(value.reason_codes) || typeof value.explanation !== 'string' || !['TOKEN_PRICE_ONLY','ALL_IN_ESTIMATE','NONE'].includes(String(value.ranking_basis)) ||
    !object(value.policy) || !Array.isArray(value.candidates)) return invalid()
  const policy = value.policy
  if (policy.version !== 'routing-1' || policy.purpose !== purpose || policy.weights !== null || policy.max_age_seconds !== 120 ||
    policy.ranking !== 'MIN_EXACT_EFFECTIVE_COST_THEN_IDENTITY' || policy.unknown_cost_behavior !== 'COMMON_PRICE_ONLY_BASIS_OR_REJECT_IF_REQUIRED' ||
    !['require_costs','require_liquidity','require_trust','require_risk'].every(k => typeof policy[k] === 'boolean') ||
    !['min_liquidity_usd','max_slippage_bps'].every(k => policy[k] === null || decimal(policy[k])) ||
    (purpose === 'OPPORTUNITY' && (!policy.require_costs || !policy.require_liquidity || !policy.require_trust || !policy.require_risk || policy.min_liquidity_usd === null || policy.max_slippage_bps === null))) return invalid()
  for (const c of value.candidates) {
    if (!object(c) || !object(c.inputs)) return invalid()
    const input = c.inputs
    if (!uuid(c.candidate_id) || !identity(input.identity) || input.identity.underlying !== underlying ||
      input.data_mode !== mode || !decimal(input.token_to_share_ratio) || compare(input.token_to_share_ratio as string, '0') <= 0 ||
      !['token_price_usd','liquidity_usd','volume_usd','fees_usd','gas_usd','slippage_bps','risk_max_notional_usd'].every(k => input[k] === null || decimal(input[k])) ||
      !['price_source','price_quality','ratio_source','market_state','trust_state','risk_state','route_support'].every(k => typeof input[k] === 'string') ||
      !date(input.ratio_observed_at) || !['price_timestamp','liquidity_timestamp','cost_timestamp','trust_timestamp','risk_timestamp'].every(k => input[k] === null || date(input[k])) ||
      !['liquidity_source','cost_source','trust_source','risk_source'].every(k => input[k] === null || typeof input[k] === 'string') ||
      !['trust_assessment_id','risk_id'].every(k => input[k] === null || uuid(input[k])) ||
      typeof input.supported !== 'boolean' || typeof input.normalization_eligible !== 'boolean' || !(input.tradable === null || typeof input.tradable === 'boolean') ||
      !(input.route_available === null || typeof input.route_available === 'boolean') || typeof c.eligible !== 'boolean' || !strings(c.rejection_reasons) || !strings(c.limitations) ||
      !['effective_cost_per_share_usd','estimated_costs_usd','all_in_cost_per_share_usd','ranking_cost_per_share_usd'].every(k => c[k] === null || decimal(c[k])) ||
      !['AVAILABLE','UNAVAILABLE','UNVERIFIED','STALE'].includes(String(c.liquidity_state)) || !['AVAILABLE','UNAVAILABLE','UNVERIFIED','STALE'].includes(String(c.cost_state)) ||
      typeof c.trust_state !== 'string' || !['TRADABLE','NOT_TRADABLE','UNKNOWN'].includes(String(c.tradability))) return invalid()
    if (c.eligible) {
      if (!Number.isInteger(c.rank) || (c.rank as number) < 1 || c.rejection_reasons.length || c.ranking_cost_per_share_usd === null ||
        c.effective_cost_per_share_usd === null || c.tradability !== 'TRADABLE' || !input.supported || !input.normalization_eligible ||
        (policy.require_liquidity && c.liquidity_state !== 'AVAILABLE') || (policy.require_costs && c.cost_state !== 'AVAILABLE') ||
        (policy.require_trust && !['NORMAL','LIKELY_INFORMATION'].includes(input.trust_state as string)) ||
        (purpose === 'OPPORTUNITY' && input.trust_state !== 'LIKELY_INFORMATION') || (policy.require_risk && input.risk_state !== 'PASS')) return invalid()
    } else if (c.rank !== null || c.rejection_reasons.length === 0 || c.ranking_cost_per_share_usd !== null) return invalid()
  }
  const candidates = value.candidates as unknown as RouteCandidate[], eligible = candidates.filter(c => c.eligible)
  if (new Set(candidates.map(c => c.candidate_id)).size !== candidates.length && value.status === 'ROUTE_SELECTED') return invalid()
  if (new Set(eligible.map(c => c.rank)).size !== eligible.length || !eligible.every(c => c.rank! <= eligible.length)) return invalid()
  if (value.status === 'ROUTE_SELECTED') {
    const selected = candidates.find(c => c.rank === 1)
    if (!selected || !equal(value.selected_candidate, selected) || !equal(value.selected_representation, selected.inputs.identity) || value.issuer !== selected.inputs.identity.issuer ||
      (value.ranking_basis === 'ALL_IN_ESTIMATE' && !eligible.every(c => c.cost_state === 'AVAILABLE')) || value.ranking_basis === 'NONE') return invalid()
  } else if (value.selected_candidate !== null || value.selected_representation !== null || value.issuer !== null || eligible.length) return invalid()
  return value as unknown as RouteDecision
}
