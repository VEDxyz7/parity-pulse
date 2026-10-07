import { parseRoute, type RouteDecision } from './routing'
export interface Estimate {
  issuer: string; contract: string; chain_id: string; token_symbol: string
  token_to_share_ratio: string; token_price_usd: string | null
  effective_cost_per_share_usd: string | null; estimated_token_quantity: string | null
  estimated_real_share_exposure: string | null; estimated_token_cost_usd: string | null
  unallocated_budget_usd: string | null; estimate_eligible: boolean
  exclusion_reasons: string[]; market_state: string; price_source: string
  price_timestamp: string | null; price_quality: string; data_mode: 'DEMO' | 'LIVE'
}
export interface Proposal {
  route_decision?: RouteDecision | null
  schema_version: 'ask-1'; proposal_id: string; status: 'DRY_RUN' | 'NO_PROPOSAL' | 'EXPIRED'
  data_mode: 'DEMO' | 'LIVE'; ticker: string | null; company_name: string | null
  requested_budget_usd: string | null; selected: Estimate | null; representations: Estimate[]
  route_selection_reason: string; broadcast_statement: 'No real transaction was broadcast.'
  valid_until: string; execution_blockers: string[]; limitations: Record<string, string>
  independent_equity: { status: string; price_usd_per_share: string | null; source: string | null }
}
const object = (v: unknown): v is Record<string, unknown> => typeof v === 'object' && v !== null && !Array.isArray(v)
const decimal = (v: unknown) => typeof v === 'string' && v.length <= 256 && /^(?:[0-9]+(?:\.[0-9]+)?)(?:[Ee][+-]?[0-9]+)?$/.test(v)
const strings = (v: unknown): v is string[] => Array.isArray(v) && v.every(s => typeof s === 'string')
function estimate(v: unknown, mode: string): boolean {
  if (!object(v) || v.data_mode !== mode || typeof v.estimate_eligible !== 'boolean' ||
      !strings(v.exclusion_reasons) || !['issuer', 'contract', 'chain_id', 'token_symbol', 'market_state', 'price_source', 'price_quality'].every(k => typeof v[k] === 'string') ||
      !decimal(v.token_to_share_ratio) || !(v.price_timestamp === null || typeof v.price_timestamp === 'string')) return false
  return ['token_price_usd', 'effective_cost_per_share_usd', 'estimated_token_quantity', 'estimated_real_share_exposure', 'estimated_token_cost_usd', 'unallocated_budget_usd'].every(k =>
    v.estimate_eligible ? decimal(v[k]) : v[k] === null || decimal(v[k]))
}
export function parseProposal(value: unknown, expectedMode: 'DEMO' | 'LIVE_READ_ONLY'): Proposal {
  const mode = expectedMode === 'DEMO' ? 'DEMO' : 'LIVE'
  if (!object(value) || value.schema_version !== 'ask-1' || value.data_mode !== mode ||
      !['DRY_RUN', 'NO_PROPOSAL', 'EXPIRED'].includes(String(value.status)) ||
      value.execution_mode !== 'DRY_RUN' || value.approval_mode !== 'PROPOSE_ONLY' ||
      value.require_simulation !== true || value.live_trading_enabled !== false ||
      value.execution_ready !== false || value.transaction_broadcast !== false ||
      value.simulation_status !== 'UNAVAILABLE' || value.provider_quote_id !== null ||
      value.fee_status !== 'UNKNOWN' || value.broadcast_statement !== 'No real transaction was broadcast.' ||
      typeof value.proposal_id !== 'string' || typeof value.route_selection_reason !== 'string' ||
      typeof value.valid_until !== 'string' || !Number.isFinite(Date.parse(value.valid_until)) ||
      !strings(value.execution_blockers) || !object(value.limitations) ||
      !Object.values(value.limitations).every(v => typeof v === 'string') ||
      !object(value.independent_equity) || typeof value.independent_equity.status !== 'string' ||
      !(value.independent_equity.price_usd_per_share === null || decimal(value.independent_equity.price_usd_per_share)) ||
      !(value.independent_equity.source === null || typeof value.independent_equity.source === 'string') ||
      !(value.ticker === null || typeof value.ticker === 'string') ||
      !(value.company_name === null || typeof value.company_name === 'string') ||
      !(value.requested_budget_usd === null || decimal(value.requested_budget_usd)) ||
      !Array.isArray(value.representations) || !value.representations.every(v => estimate(v, mode)) ||
      (value.status === 'DRY_RUN' ? !estimate(value.selected, mode) || !object(value.selected) ||
          value.selected.estimate_eligible !== true || value.quote_status !== 'INDICATIVE_ONLY' :
          value.selected !== null || value.quote_status !== 'UNAVAILABLE')) {
    throw new Error('Proposal could not be verified. No execution is available.')
  }
  if (value.route_decision !== undefined && value.route_decision !== null) {
    const route = parseRoute(value.route_decision, mode, value.ticker as string | null, value.requested_budget_usd as string | null)
    if (value.status === "DRY_RUN" && (!route.selected_representation || !object(value.selected) || route.selected_representation.contract !== value.selected.contract || route.selected_representation.issuer !== value.selected.issuer || route.selected_representation.chain_id !== value.selected.chain_id)) throw new Error("Route/proposal identity mismatch")
    if (value.status !== "DRY_RUN" && route.status !== "NO_ROUTE") throw new Error("Unavailable proposal cannot select a route")
  }
  return value as unknown as Proposal
}
export async function requestProposal(text: string, mode: 'DEMO' | 'LIVE_READ_ONLY', signal: AbortSignal): Promise<Proposal> {
  const response = await fetch('/api/exposure/quote', {
    method: 'POST', signal, cache: 'no-store',
    headers: { 'Content-Type': 'application/json', 'X-Correlation-ID': crypto.randomUUID() },
    body: JSON.stringify({ text }),
  })
  if (!response.ok) throw new Error('Proposal unavailable. Check your request and retry.')
  return parseProposal(await response.json(), mode)
}
