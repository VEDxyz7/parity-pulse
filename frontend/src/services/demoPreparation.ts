import { apiRequest } from './api'
import { parseRoute, type RouteDecision } from './routing'
import type { DemoResult } from './demoSandbox'
import { compare, date, decimal, envelope, marked, object, parseOpportunity, parseRisk, strings, uuid,
  type OpportunityResult, type Risk, type RiskResult } from './demoOpportunity'

interface Safety {
  dataset_type: 'DEMO_FIXTURE'; synthetic: true; production_eligible: false; source: 'DEMO'
  execution_mode: 'DRY_RUN'; approval_mode: 'PROPOSE_ONLY'; require_simulation: true
  live_trading_enabled: false; execution_ready: false; transaction_broadcast: false; signed: false; funds_moved: false
  no_broadcast_statement: 'No real transaction was broadcast.'
}
export interface DemoQuote extends Safety {
  quote_id: string; fingerprint: string; context_sha256: string; opportunity_id: string; source_risk_id: string
  ticker: string; issuer: string; chain_id: 'DEMO'; contract: string; symbol: string; decimals: number
  direction: 'BUY'; input_asset: 'DEMO_USD'; quote_type: 'SYNTHETIC_ECONOMIC_QUOTE'; provider_quote_id: null; executable: false
  quoted_at: string; valid_until: string; market_observed_at: string; market_observation_kind: 'PRICE_INFO' | 'PRICE'
  mark_price_usd: string; execution_price_usd: string; token_to_share_ratio: string
  requested_notional_usd: string; base_notional_usd: string; input_amount_usd: string; output_token_quantity: string; share_exposure: string
  fees_usd: string; gas_usd: string; execution_buffer_usd: string; slippage_bps: string; estimated_slippage_usd: string
  total_cash_required_usd: string; net_hypothetical_edge_usd: string
}
export interface Transaction extends Safety {
  transaction_id: string; fingerprint: string; quote_fingerprint: string; context_sha256: string
  quote_id: string; opportunity_id: string; prepared_at: string; valid_until: string
  transaction_type: 'DEMO_BUY_REQUEST'; encoding: 'CANONICAL_JSON_DEMO_REQUEST'
  calldata: null; signature: null; broadcastable: false
  parameters: { ticker: string; issuer: string; chain_id: 'DEMO'; target_token: string; token_symbol: string; token_decimals: number
    token_base_units: string; direction: 'BUY'; input_asset: 'DEMO_USD'; quote_id: string; quantity: string
    base_notional_usd: string; maximum_input_usd: string; minimum_output_tokens: string; maximum_slippage_bps: string
    fees_usd: string; gas_usd: string; execution_buffer_usd: string; total_cash_required_usd: string }
}
interface Base extends Safety { runtime_mode: 'DEMO'; scenario_id: string; inputs_fixture_sha256: string; reason_codes: string[] }
export interface QuoteResult extends Base {
  route_decision?: RouteDecision | null
  status: 'QUOTED' | 'BLOCKED'; quote: DemoQuote | null; opportunity: OpportunityResult['opportunity']
  risk_before_quote: Risk; quoted_opportunity: OpportunityResult['opportunity'] | null; risk_revalidation: Risk | null
}
export interface PreparationResult extends Base { status: 'PREPARED' | 'BLOCKED'; transaction: Transaction | null; risk_revalidation: Risk }
export interface SimulationResult extends Base {
  simulation: Safety & { simulation_id: string; transaction_id: string; transaction_fingerprint: string; quote_id: string; quote_fingerprint: string
    evaluated_at: string; valid_until: string; method: 'LOCAL_DEMO_CONSTRAINT_EVALUATION'; chain_simulation: false
    status: 'SIMULATION_PASS' | 'SIMULATION_FAIL'; reason_codes: string[]; checks: { code: string; passed: boolean; detail: string }[]; risk_revalidation: Risk }
}
function invalid(): never { throw new Error('DEMO downstream result could not be verified. No execution occurred.') }
function sha(v: unknown): boolean { return typeof v === 'string' && /^[a-f0-9]{64}$/.test(v) }
function safety(v: unknown): v is Record<string, unknown> {
  return marked(v) && v.source === 'DEMO' && v.execution_mode === 'DRY_RUN' && v.approval_mode === 'PROPOSE_ONLY' &&
    v.require_simulation === true && v.live_trading_enabled === false && v.execution_ready === false && v.transaction_broadcast === false &&
    v.signed === false && v.funds_moved === false && v.no_broadcast_statement === 'No real transaction was broadcast.'
}
function base(v: unknown, o: OpportunityResult): v is Record<string, unknown> {
  return envelope(v, o.scenario_id) && safety(v) && v.inputs_fixture_sha256 === o.inputs_fixture_sha256 && strings(v.reason_codes)
}
function wrappedOpportunity(v: Record<string, unknown>, raw: unknown, trust: DemoResult, origin: OpportunityResult): OpportunityResult {
  return parseOpportunity({ ...v, route_decision: null, trust_fixture_sha256: origin.trust_fixture_sha256, opportunity: raw }, trust)
}
export function parseQuote(v: unknown, trust: DemoResult, origin: OpportunityResult, risk: RiskResult): QuoteResult {
  if (!base(v, origin) || !['QUOTED', 'BLOCKED'].includes(String(v.status))) return invalid()
  const current = wrappedOpportunity(v, v.opportunity, trust, origin)
  if (current.opportunity.opportunity_id !== origin.opportunity.opportunity_id) return invalid()
  const before = parseRisk({ ...v, risk: v.risk_before_quote }, current)
  if (v.quote !== null) {
    const q = v.quote
    if (!safety(q) || !uuid(q.quote_id) || !sha(q.fingerprint) || !sha(q.context_sha256) ||
      q.opportunity_id !== origin.opportunity.opportunity_id || q.source_risk_id !== risk.risk.risk_id ||
      q.ticker !== origin.opportunity.ticker || q.issuer !== origin.opportunity.issuer || q.chain_id !== 'DEMO' ||
      q.contract !== origin.opportunity.contract || q.symbol !== origin.opportunity.symbol || !Number.isInteger(q.decimals) ||
      (q.decimals as number) < 0 || (q.decimals as number) > 255 || q.direction !== 'BUY' || q.input_asset !== 'DEMO_USD' ||
      q.quote_type !== 'SYNTHETIC_ECONOMIC_QUOTE' || q.provider_quote_id !== null || q.executable !== false ||
      !['PRICE_INFO', 'PRICE'].includes(String(q.market_observation_kind)) || !date(q.quoted_at) || !date(q.valid_until) || !date(q.market_observed_at) ||
      Date.parse(q.valid_until as string) <= Date.parse(q.quoted_at as string) || !marked(q.economics_inputs) ||
      !['mark_price_usd', 'execution_price_usd', 'token_to_share_ratio', 'requested_notional_usd', 'base_notional_usd', 'input_amount_usd',
        'output_token_quantity', 'share_exposure', 'fees_usd', 'gas_usd', 'execution_buffer_usd', 'slippage_bps',
        'estimated_slippage_usd', 'total_cash_required_usd', 'net_hypothetical_edge_usd'].every(k => decimal(q[k])) ||
      compare(q.output_token_quantity as string, '0') <= 0 || compare(q.input_amount_usd as string, q.requested_notional_usd as string) > 0) return invalid()
    const quoted = wrappedOpportunity(v, v.quoted_opportunity, trust, origin)
    if (quoted.opportunity.opportunity_id !== q.opportunity_id) return invalid()
    const after = parseRisk({ ...v, risk: v.risk_revalidation }, quoted)
    if (v.status === 'QUOTED' && (before.risk.status !== 'PASS' || after.risk.status !== 'PASS' || risk.risk.status !== 'PASS')) return invalid()
  } else if (v.status === 'QUOTED' || v.quoted_opportunity !== null || v.risk_revalidation !== null) return invalid()
  if (v.route_decision !== undefined && v.route_decision !== null) {
    const route = parseRoute(v.route_decision, "DEMO", origin.opportunity.ticker, undefined, "OPPORTUNITY")
    if (v.status === "QUOTED" && (route.status !== "ROUTE_SELECTED" || route.selected_representation?.contract !== origin.opportunity.contract || route.selected_representation?.issuer !== origin.opportunity.issuer)) return invalid()
  }
  return v as unknown as QuoteResult
}
function quoteOpportunity(q: QuoteResult, origin: OpportunityResult): OpportunityResult {
  if (q.status !== 'QUOTED' || q.quote === null || q.quoted_opportunity === null) return invalid()
  return { ...origin, opportunity: q.quoted_opportunity }
}
export function parsePreparation(v: unknown, q: QuoteResult, origin: OpportunityResult): PreparationResult {
  if (!base(v, origin) || !['PREPARED', 'BLOCKED'].includes(String(v.status))) return invalid()
  const quoted = quoteOpportunity(q, origin), quote = q.quote!
  const risk = parseRisk({ ...v, risk: v.risk_revalidation }, quoted)
  if (v.transaction !== null) {
    const t = v.transaction
    if (!safety(t) || !uuid(t.transaction_id) || !sha(t.fingerprint) || t.quote_fingerprint !== quote.fingerprint ||
      t.context_sha256 !== quote.context_sha256 || t.quote_id !== quote.quote_id || t.opportunity_id !== quote.opportunity_id ||
      !date(t.prepared_at) || t.valid_until !== quote.valid_until || t.transaction_type !== 'DEMO_BUY_REQUEST' ||
      t.encoding !== 'CANONICAL_JSON_DEMO_REQUEST' || t.calldata !== null || t.signature !== null || t.broadcastable !== false || !marked(t.parameters)) return invalid()
    const p = t.parameters
    if (p.ticker !== quote.ticker || p.issuer !== quote.issuer || p.chain_id !== 'DEMO' || p.target_token !== quote.contract ||
      p.token_symbol !== quote.symbol || p.token_decimals !== quote.decimals || p.direction !== 'BUY' || p.input_asset !== 'DEMO_USD' ||
      p.quote_id !== quote.quote_id || typeof p.token_base_units !== 'string' || !/^[1-9][0-9]{0,511}$/.test(p.token_base_units) ||
      p.quantity !== quote.output_token_quantity || p.minimum_output_tokens !== quote.output_token_quantity ||
      p.base_notional_usd !== quote.base_notional_usd || p.maximum_input_usd !== quote.input_amount_usd ||
      p.maximum_slippage_bps !== quote.slippage_bps || p.fees_usd !== quote.fees_usd || p.gas_usd !== quote.gas_usd ||
      p.execution_buffer_usd !== quote.execution_buffer_usd || p.total_cash_required_usd !== quote.total_cash_required_usd ||
      risk.risk.status !== 'PASS' || v.status !== 'PREPARED' ||
      Date.parse(t.prepared_at as string) < Date.parse(quote.quoted_at) || Date.parse(t.prepared_at as string) >= Date.parse(quote.valid_until)) return invalid()
  } else if (v.status !== 'BLOCKED') return invalid()
  return v as unknown as PreparationResult
}
const simulationChecks = ['QUOTE_VALID', 'REQUEST_VALID', 'CURRENT_INPUTS_UNCHANGED', 'QUOTE_FINGERPRINT', 'TRANSACTION_FINGERPRINT',
  'QUOTE_BINDING', 'REPRESENTATION_VALID', 'RISK_REVALIDATION', 'ALLOWED_SIZE', 'SLIPPAGE_LIMIT', 'LIQUIDITY_LIMIT', 'EXECUTION_PRICE',
  'AMOUNT_EQUIVALENCE', 'BASE_UNITS', 'QUOTED_NET_EDGE', 'EXPECTED_COSTS', 'CASH_LIMITS', 'NO_EXECUTION']
export function parseSimulation(v: unknown, q: QuoteResult, prepared: PreparationResult, origin: OpportunityResult): SimulationResult {
  if (!base(v, origin) || !safety(v.simulation) || prepared.status !== 'PREPARED' || prepared.transaction === null) return invalid()
  const s = v.simulation, t = prepared.transaction, quote = q.quote!
  if (!uuid(s.simulation_id) || s.transaction_id !== t.transaction_id || s.transaction_fingerprint !== t.fingerprint ||
    s.quote_id !== quote.quote_id || s.quote_fingerprint !== quote.fingerprint || !date(s.evaluated_at) || s.valid_until !== quote.valid_until ||
    s.method !== 'LOCAL_DEMO_CONSTRAINT_EVALUATION' || s.chain_simulation !== false || !strings(s.reason_codes) ||
    !['SIMULATION_PASS', 'SIMULATION_FAIL'].includes(String(s.status)) || !Array.isArray(s.checks) || s.checks.length !== simulationChecks.length ||
    !s.checks.every(c => object(c) && typeof c.code === 'string' && typeof c.passed === 'boolean' && typeof c.detail === 'string') ||
    new Set(s.checks.map(c => (c as Record<string, unknown>).code)).size !== simulationChecks.length ||
    !simulationChecks.every(code => (s.checks as Record<string, unknown>[]).some(c => c.code === code))) return invalid()
  const risk = parseRisk({ ...v, risk: s.risk_revalidation }, quoteOpportunity(q, origin))
  const passed = s.status === 'SIMULATION_PASS'
  if (passed !== s.checks.every(c => (c as Record<string, unknown>).passed === true) ||
    (passed && (risk.risk.status !== 'PASS' || Date.parse(s.evaluated_at as string) < Date.parse(t.prepared_at) ||
      Date.parse(s.evaluated_at as string) >= Date.parse(quote.valid_until)))) return invalid()
  return v as unknown as SimulationResult
}
async function post(path: string, body: object, signal: AbortSignal): Promise<unknown> {
  return apiRequest(path, value => value, { signal, body, timeout: 60_000 })
}
export async function fetchQuote(trust: DemoResult, origin: OpportunityResult, risk: RiskResult, signal: AbortSignal): Promise<QuoteResult> {
  return parseQuote(await post('/api/demo/quote', { risk_id: risk.risk.risk_id }, signal), trust, origin, risk)
}
export async function fetchPreparation(q: QuoteResult, origin: OpportunityResult, signal: AbortSignal): Promise<PreparationResult> {
  if (!q.quote || q.status !== 'QUOTED') return invalid()
  return parsePreparation(await post('/api/demo/prepare', { quote_id: q.quote.quote_id }, signal), q, origin)
}
export async function fetchSimulation(q: QuoteResult, prepared: PreparationResult, origin: OpportunityResult, signal: AbortSignal): Promise<SimulationResult> {
  if (!prepared.transaction || prepared.status !== 'PREPARED') return invalid()
  return parseSimulation(await post('/api/demo/simulate', { transaction_id: prepared.transaction.transaction_id }, signal), q, prepared, origin)
}
