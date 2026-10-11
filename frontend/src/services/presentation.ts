import { apiRequest } from './api'
import { validateWire } from './contracts'
import type { PresentationWorkspace, PresentationAnalysis, PresentationScan, RouteDecision, PresentationAnalysis_ScenarioRequest } from '../types/backend.generated'
export type ScenarioInputs = PresentationAnalysis_ScenarioRequest
export const presentation = {
  workspace: (signal: AbortSignal) => apiRequest('/api/presentation/workspace', value => validateWire<PresentationWorkspace>('PresentationWorkspace', value), { signal }),
  research: (body: ScenarioInputs, signal: AbortSignal) => apiRequest('/api/presentation/research', value => validateWire<PresentationAnalysis>('PresentationAnalysis', value), { body, signal }),
  scan: (body: {budget: string; risk_budget: string; window: 'regular' | 'reopening'; universe: ('NVDA' | 'AAPL')[]}, signal: AbortSignal) => apiRequest('/api/presentation/scan', value => validateWire<PresentationScan>('PresentationScan', value), { body, signal }),
  exposure: (body: ScenarioInputs, signal: AbortSignal) => apiRequest('/api/presentation/exposure', value => validateWire<RouteDecision>('RouteDecision', value), { body, signal }),
}
