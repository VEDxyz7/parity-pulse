import { apiRequest } from './api'
import { validateWire } from './contracts'
import type { WorkspaceState, OpportunityScan, OpportunityRequest, ConfigRequest, RebalancePlan, AuditPage, PortfolioConfig } from '../types/backend.generated'
export type Mode = 'DEMO' | 'LIVE_READ_ONLY'
export type { WorkspaceState, OpportunityScan, OpportunityRequest, ConfigRequest, RebalancePlan, AuditPage, PortfolioConfig }
function scoped<T extends { data_mode: Mode }>(value: T, mode: Mode): T {
  function inspect(v: unknown): void {
    if (Array.isArray(v)) { v.forEach(inspect); return }
    if (typeof v !== 'object' || v === null) return
    for (const [key, entry] of Object.entries(v)) {
      if (key === 'data_mode' && (mode === 'DEMO' ? entry !== 'DEMO' : entry === 'DEMO')) throw new Error('Backend mode mismatch.')
      if (mode === 'LIVE_READ_ONLY' && (key === 'synthetic' && entry === true || key === 'data_quality' && entry === 'DEMO')) throw new Error('Synthetic production evidence refused.')
      inspect(entry)
    }
  }
  if (value.data_mode !== mode) throw new Error('Backend mode mismatch.')
  inspect(value)
  return value
}
export function getWorkspace(mode: Mode, signal: AbortSignal) {
  return apiRequest('/api/workspace', value => scoped(validateWire<WorkspaceState>('WorkspaceState', value), mode), { signal })
}
export function scanOpportunity(body: OpportunityRequest, mode: Mode, signal: AbortSignal) {
  validateWire('OpportunityRequest', body)
  return apiRequest('/api/opportunities/scan', value => scoped(validateWire<OpportunityScan>('OpportunityScan', value), mode), { signal, body, timeout: 60_000 })
}
export function readScan(id: string, mode: Mode, signal: AbortSignal) {
  if (!/^[a-f0-9]{64}$/.test(id)) throw new Error('Invalid scan reference.')
  return apiRequest(`/api/opportunities/${id}`, value => scoped(validateWire<OpportunityScan>('OpportunityScan', value), mode), { signal })
}
export function configurePortfolio(body: ConfigRequest, signal: AbortSignal) {
  validateWire('ConfigRequest', body)
  // Backend validates the reviewed mandate and expected version. No blind retry of this write.
  return apiRequest('/api/autopilot', value => validateWire<PortfolioConfig>('PortfolioConfig', value), { signal, body })
}
export function proposeDrift(key: string, mode: Mode, signal: AbortSignal) {
  return apiRequest('/api/portfolio/plans', value => scoped(validateWire<RebalancePlan>('RebalancePlan', value), mode), { signal, body: { idempotency_key: key } })
}
export function getAudit(mode: Mode, offset: number, signal: AbortSignal) {
  return apiRequest(`/api/audit?limit=25&offset=${offset}`, value => scoped(validateWire<AuditPage>('AuditPage', value), mode), { signal })
}
export { readRefresh } from '../hooks/readRefresh'
