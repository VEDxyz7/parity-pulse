import { apiRequest } from './api'
import { compare, date, decimal, marked, object, parseRisk, strings, uuid, type OpportunityResult } from './demoOpportunity'
import { parseSimulation, type PreparationResult, type QuoteResult, type SimulationResult } from './demoPreparation'

interface PaperMarker {
  source: 'DEMO'; execution_mode: 'PAPER'; dataset_type: 'DEMO_FIXTURE'; synthetic: true; production_eligible: false
  signed: false; transaction_broadcast: false; funds_moved: false
}
interface Fill extends PaperMarker {
  fill_id: string; order_id: string; filled_at: string; quantity: string; price_usd: string
  notional_usd: string; fees_usd: string; gas_usd: string; reserve_usd: string; fill_type: 'SYNTHETIC_QUOTE_FILL'
}
interface Exit extends PaperMarker {
  exit_id: string; position_id: string; observation_id: string; exited_at: string; quantity: string
  price_usd: string; notional_usd: string; fees_usd: string; gas_usd: string; released_reserve_usd: string
}
interface Pnl extends PaperMarker {
  position_id: string; gross_pnl_usd: string; costs_usd: string; net_pnl_usd: string; return_pct: string
  entry_cost_basis_usd: string; convention: 'SLIPPAGE_IN_PRICES_RESERVE_RELEASED_NOT_EXPENSE'
}
export interface Lifecycle extends PaperMarker {
  runtime_mode: 'DEMO'; scenario_id: string; production_gates: Record<string, string>
  order: PaperMarker & { order_id: string; transaction_id: string; quote_id: string; simulation_id: string; opportunity_id: string; risk_id: string; status: 'PAPER_FILLED'; created_at: string }
  fill: Fill
  position: PaperMarker & { position_id: string; fill_id: string; ticker: string; issuer: string; token: string; quantity: string
    entry_price_usd: string; entry_notional_usd: string; entry_costs_usd: string; reserved_usd: string; entered_at: string; state: 'OPEN' | 'EXITED'; exited_at: string | null }
  observation: null | (PaperMarker & { observation_id: string; position_id: string; observed_at: string; token_mark_price_usd: string
    sell_price_usd: string; fees_usd: string; gas_usd: string; fixture_sha256: string; description: string; clock_mode: 'EXPLICIT_SYNTHETIC_TIME_ADVANCE' })
  exit: Exit | null; pnl: Pnl | null
  events: (PaperMarker & { event_id: string; position_id: string; kind: 'ENTRY' | 'MONITOR' | 'EXIT'; occurred_at: string; reference_id: string })[]
}
export interface Scorecard extends PaperMarker {
  runtime_mode: 'DEMO'; scenario_id: string; production_gates: Record<string, string>; position_id: string
  trust_assessment_id: string; trust_classification: string; opportunity_status: 'ACTIONABLE'; risk_status: 'PASS'
  execution_status: 'PAPER_FILLED'; simulation_status: 'SIMULATION_PASS'; entry: Fill; exit: Exit; pnl: Pnl
  event_ids: string[]; reason_codes: string[]; evidence_quality: string; confidence: string
  quote_id: string; transaction_id: string; simulation_id: string; risk_id: string
}
function invalid(): never { throw new Error('Paper lifecycle could not be verified. No real execution occurred.') }
function paper(v: unknown): v is Record<string, unknown> {
  return marked(v) && v.source === 'DEMO' && v.execution_mode === 'PAPER' && v.signed === false && v.transaction_broadcast === false && v.funds_moved === false
}
function envelope(v: unknown, origin: OpportunityResult): v is Record<string, unknown> {
  return paper(v) && v.runtime_mode === 'DEMO' && v.scenario_id === origin.scenario_id && object(v.production_gates) &&
    Object.keys(v.production_gates).length === Object.keys(origin.production_gates).length &&
    Object.entries(origin.production_gates).every(([k, value]) => (v.production_gates as Record<string, unknown>)[k] === value)
}
function numbers(v: Record<string, unknown>, keys: string[]) { return keys.every(k => decimal(v[k])) }
function equal(a: unknown, b: unknown): boolean {
  if (object(a) && object(b)) return Object.keys(a).length === Object.keys(b).length && Object.keys(a).every(k => equal(a[k], b[k]))
  if (Array.isArray(a) && Array.isArray(b)) return a.length === b.length && a.every((x, i) => equal(x, b[i]))
  return a === b
}
export function parseLifecycle(v: unknown, quote: QuoteResult, prepared: PreparationResult, simulation: SimulationResult, origin: OpportunityResult): Lifecycle {
  if (!envelope(v, origin) || !quote.quote || !prepared.transaction || simulation.simulation.status !== 'SIMULATION_PASS' ||
    !paper(v.order) || !paper(v.fill) || !paper(v.position) || !Array.isArray(v.events)) return invalid()
  const q = quote.quote, t = prepared.transaction, o = v.order, f = v.fill, p = v.position
  if (!uuid(o.order_id) || o.status !== 'PAPER_FILLED' || o.transaction_id !== t.transaction_id || o.quote_id !== q.quote_id ||
    o.simulation_id !== simulation.simulation.simulation_id || o.opportunity_id !== q.opportunity_id || !uuid(o.risk_id) || !date(o.created_at) ||
    !equal(v.quote, q) || !equal(v.preparation, t) || !equal(v.simulation, simulation.simulation)) return invalid()
  const quoted = { ...origin, opportunity: quote.quoted_opportunity! }
  const risk = parseRisk({ ...origin, risk: v.risk }, quoted)
  if (risk.risk.status !== 'PASS' || risk.risk.risk_id !== o.risk_id) return invalid()
  const revalidation = parseSimulation({ ...simulation, simulation: v.fill_revalidation }, quote, prepared, origin)
  if (revalidation.simulation.status !== 'SIMULATION_PASS' || revalidation.simulation.risk_revalidation.risk_id !== o.risk_id ||
    revalidation.simulation.evaluated_at !== o.created_at) return invalid()
  if (!uuid(f.fill_id) || f.order_id !== o.order_id || f.fill_type !== 'SYNTHETIC_QUOTE_FILL' || f.filled_at !== o.created_at ||
    f.quantity !== q.output_token_quantity || f.price_usd !== q.execution_price_usd || f.notional_usd !== q.input_amount_usd ||
    f.fees_usd !== q.fees_usd || f.gas_usd !== q.gas_usd || f.reserve_usd !== q.execution_buffer_usd ||
    !uuid(p.position_id) || p.fill_id !== f.fill_id || p.ticker !== q.ticker || p.issuer !== q.issuer || p.token !== q.contract ||
    p.quantity !== f.quantity || p.entry_price_usd !== f.price_usd || p.entry_notional_usd !== f.notional_usd ||
    p.reserved_usd !== f.reserve_usd || p.entered_at !== f.filled_at || !decimal(p.entry_costs_usd) ||
    !['OPEN', 'EXITED'].includes(String(p.state))) return invalid()
  const expected = v.observation === null ? ['ENTRY'] : p.state === 'OPEN' ? ['ENTRY', 'MONITOR'] : ['ENTRY', 'MONITOR', 'EXIT']
  if (v.events.length !== expected.length || !v.events.every((e, i) => paper(e) && uuid(e.event_id) && e.position_id === p.position_id &&
    e.kind === expected[i] && date(e.occurred_at) && uuid(e.reference_id)) ||
    (v.events[0] as Record<string, unknown>).reference_id !== f.fill_id) return invalid()
  if (v.observation !== null) {
    const m = v.observation
    if (!paper(m) || !uuid(m.observation_id) || m.position_id !== p.position_id || !date(m.observed_at) ||
      Date.parse(m.observed_at as string) <= Date.parse(p.entered_at as string) || m.clock_mode !== 'EXPLICIT_SYNTHETIC_TIME_ADVANCE' ||
      typeof m.description !== 'string' || typeof m.fixture_sha256 !== 'string' || !/^[0-9a-f]{64}$/.test(m.fixture_sha256) ||
      !numbers(m, ['token_mark_price_usd','sell_price_usd','fees_usd','gas_usd']) ||
      compare(m.sell_price_usd as string, '0') <= 0 || (v.events[1] as Record<string, unknown>).reference_id !== m.observation_id) return invalid()
  }
  if (p.state === 'OPEN') {
    if (p.exited_at !== null || v.exit !== null || v.pnl !== null) return invalid()
  } else {
    const x = v.exit, n = v.pnl, m = v.observation
    if (!paper(x) || !paper(n) || !paper(m) || !uuid(x.exit_id) || x.position_id !== p.position_id ||
      x.observation_id !== m.observation_id || x.exited_at !== m.observed_at || p.exited_at !== x.exited_at ||
      x.quantity !== p.quantity || x.price_usd !== m.sell_price_usd || x.fees_usd !== m.fees_usd || x.gas_usd !== m.gas_usd ||
      x.released_reserve_usd !== p.reserved_usd || !decimal(x.notional_usd) || n.position_id !== p.position_id ||
      n.convention !== 'SLIPPAGE_IN_PRICES_RESERVE_RELEASED_NOT_EXPENSE' ||
      !numbers(n, ['gross_pnl_usd','costs_usd','net_pnl_usd','return_pct','entry_cost_basis_usd']) ||
      (v.events[2] as Record<string, unknown>).reference_id !== x.exit_id) return invalid()
  }
  return v as unknown as Lifecycle
}
export function parseScorecard(v: unknown, row: Lifecycle, origin: OpportunityResult): Scorecard {
  if (!envelope(v, origin) || row.position.state !== 'EXITED' || v.position_id !== row.position.position_id ||
    v.trust_assessment_id !== origin.opportunity.trust_assessment_id || v.trust_classification !== origin.opportunity.source_trust_classification ||
    v.opportunity_status !== 'ACTIONABLE' || v.risk_status !== 'PASS' || v.execution_status !== 'PAPER_FILLED' || v.simulation_status !== 'SIMULATION_PASS' ||
    !equal(v.entry, row.fill) || !equal(v.exit, row.exit) || !equal(v.pnl, row.pnl) || !equal(v.event_ids, row.events.map(e => e.event_id)) ||
    !strings(v.reason_codes) || v.confidence !== origin.opportunity.confidence || v.evidence_quality !== origin.opportunity.evidence_quality ||
    v.quote_id !== row.order.quote_id || v.transaction_id !== row.order.transaction_id || v.simulation_id !== row.order.simulation_id || v.risk_id !== row.order.risk_id) return invalid()
  return v as unknown as Scorecard
}
export async function paperRequest(path: string, signal: AbortSignal, body?: object): Promise<unknown> {
  return apiRequest('/api/demo/paper/' + path, value => value, { signal, body, timeout: 60_000 })
}
