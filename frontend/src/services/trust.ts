// Display backend evidence only. No pricing, baseline, or trust calculations in this module.
export interface TrustResult {
  assessment_id: string
  ticker: string | null
  data_mode: 'DEMO' | 'LIVE'
  status: 'ASSESSED' | 'UNAVAILABLE'
  evaluated_at: string
  trust_gate: 'BLOCKED'
  regime: { state: string; baseline_bucket: string; previous_regular_close: string; schedule_version: string } | null
  representations: TrustRepresentation[]
  limitations: string[]
  no_broadcast_statement: 'No real transaction was broadcast.'
}
export interface TrustRepresentation {
  ticker: string; issuer: string; symbol: string; contract: string
  token_price_usd: string | null; token_to_share_ratio: string; token_timestamp: string | null
  classification: 'NORMAL' | 'LIKELY_NOISE' | 'LIKELY_INFORMATION' | 'INSUFFICIENT_EVIDENCE'
  confidence: 'LOW' | 'MEDIUM' | 'HIGH' | null
  evidence_quality: string
  reference: { status: string; reference_asof: string | null; timestamp_skew_seconds: string | null;
    token_age_seconds: string | null; reason_codes: string[];
    observation: { source: string; price: string | null; data_quality: string; kind: string } | null }
  economic_comparison: { effective_price_per_share_usd: string; comparable_token_value_usd: string; deviation: string } | null
  baseline: { status: string; sample_count: number; minimum_sample_count: number }
  liquidity: { status: string; volume_24h_usd: string | null; liquidity_usd: string | null }
  news: { state: string; coverage: string; article_ids: string[]; provider_llm_sentiment_used: false }
  analogues: { status: string; retrieved_sample_count: number; eligible_sample_count: number }
  reason_codes: string[]; missing_evidence: string[]
  features?: {
    volume_24h_usd: string; liquidity_usd: string; persistence_seconds: string;
    time_to_open_seconds: string; starting_deviation: string; ending_deviation: string;
    absolute_deviation: string; asof: string; available_at: string; news_state: string
  } | null
}
function object(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}
function strings(value: unknown): boolean { return Array.isArray(value) && value.every(v => typeof v === 'string') }
function exact(value: unknown, nullable = true): boolean {
  return (nullable && value === null) || (typeof value === 'string' && value.length <= 1000 &&
    /^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$/.test(value))
}
function timestamp(value: unknown, nullable = true): boolean {
  return nullable && value === null || typeof value === 'string' &&
    /(?:Z|[+-]\d{2}:\d{2})$/.test(value) && Number.isFinite(Date.parse(value))
}
export function parseTrust(value: unknown, mode: 'DEMO' | 'LIVE_READ_ONLY'): TrustResult {
  const invalid = () => { throw new Error('Trust evidence could not be verified.') }
  if (!object(value) || value.data_mode !== (mode === 'DEMO' ? 'DEMO' : 'LIVE') ||
    value.execution_mode !== 'DRY_RUN' || value.approval_mode !== 'PROPOSE_ONLY' ||
    value.live_trading_enabled !== false || value.require_simulation !== true ||
    value.transaction_broadcast !== false || value.execution_ready !== false ||
    value.llm_authoritative !== false || value.trust_gate !== 'BLOCKED' ||
    value.no_broadcast_statement !== 'No real transaction was broadcast.' ||
    typeof value.assessment_id !== 'string' || !timestamp(value.evaluated_at, false) ||
    !(value.ticker === null || typeof value.ticker === 'string') || !strings(value.limitations) ||
    !['ASSESSED', 'UNAVAILABLE'].includes(String(value.status)) || !Array.isArray(value.representations)) return invalid()
  if (value.regime !== null && (!object(value.regime) || typeof value.regime.state !== 'string' ||
    typeof value.regime.baseline_bucket !== 'string' || typeof value.regime.schedule_version !== 'string' ||
    !timestamp(value.regime.previous_regular_close, false))) return invalid()
  for (const row of value.representations) {
    if (!object(row) || !['NORMAL', 'LIKELY_NOISE', 'LIKELY_INFORMATION', 'INSUFFICIENT_EVIDENCE'].includes(String(row.classification)) ||
      !['LOW', 'MEDIUM', 'HIGH', null].includes(row.confidence as null) || typeof row.evidence_quality !== 'string' ||
      !['ticker', 'issuer', 'symbol', 'contract'].every(k => typeof row[k] === 'string') ||
      !exact(row.token_price_usd) || !exact(row.token_to_share_ratio, false) || !timestamp(row.token_timestamp) ||
      !strings(row.reason_codes) || !strings(row.missing_evidence) || !object(row.reference) ||
      typeof row.reference.status !== 'string' || !timestamp(row.reference.reference_asof) ||
      !exact(row.reference.timestamp_skew_seconds) || !exact(row.reference.token_age_seconds) ||
      !strings(row.reference.reason_codes) || !object(row.baseline) || typeof row.baseline.status !== 'string' ||
      !Number.isInteger(row.baseline.sample_count) || row.baseline.minimum_sample_count !== 30 ||
      !object(row.liquidity) || typeof row.liquidity.status !== 'string' || !exact(row.liquidity.volume_24h_usd) ||
      !exact(row.liquidity.liquidity_usd) || !object(row.news) || typeof row.news.state !== 'string' ||
      typeof row.news.coverage !== 'string' || !strings(row.news.article_ids) || row.news.provider_llm_sentiment_used !== false ||
      !object(row.analogues) || typeof row.analogues.status !== 'string' ||
      !Number.isInteger(row.analogues.retrieved_sample_count) || !Number.isInteger(row.analogues.eligible_sample_count)) return invalid()
    const ref = row.reference.observation
    if (ref !== null && (!object(ref) || !exact(ref.price) || typeof ref.source !== 'string' ||
      typeof ref.kind !== 'string' || typeof ref.data_quality !== 'string' || ref.source.startsWith('BINANCE') ||
      (mode === 'DEMO' ? ref.data_quality !== 'DEMO' : ref.data_quality === 'DEMO'))) return invalid()
    if (row.economic_comparison !== null && (!object(row.economic_comparison) ||
      !['effective_price_per_share_usd', 'comparable_token_value_usd', 'deviation'].every(k => exact((row.economic_comparison as Record<string, unknown>)[k], false)))) return invalid()
    if (row.classification !== 'INSUFFICIENT_EVIDENCE' && (row.reference.status !== 'AVAILABLE' ||
      row.baseline.status !== 'SUFFICIENT' || (row.baseline.sample_count as number) < 30 ||
      row.analogues.status !== 'SUFFICIENT' || (row.analogues.retrieved_sample_count as number) < 3 ||
      row.liquidity.status !== 'AVAILABLE' || row.news.coverage !== 'COMPLETE_REQUESTED_WINDOW' ||
      row.economic_comparison === null || (row.missing_evidence as string[]).length > 0 || row.confidence === null)) return invalid()
  }
  return value as unknown as TrustResult
}
export async function fetchTrust(ticker: string, mode: 'DEMO' | 'LIVE_READ_ONLY', signal: AbortSignal): Promise<TrustResult> {
  if (!/^[A-Z0-9][A-Z0-9.\-]{0,14}$/.test(ticker)) throw new Error('Invalid ticker.')
  const response = await fetch(`/api/assets/${encodeURIComponent(ticker)}/trust`, {
    method: 'GET', signal, cache: 'no-store', headers: { 'X-Correlation-ID': crypto.randomUUID() },
  })
  if (!response.ok) throw new Error('Trust unavailable.')
  return parseTrust(await response.json(), mode)
}
