import type { FoundationStatus, SystemStatus, HealthStatus } from '../types/system'

function object(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

export function parseSystemStatus(value: unknown): SystemStatus {
  if (!object(value) || !object(value.gates) ||
    !['development', 'test', 'production'].includes(String(value.environment)) ||
    !['DEMO', 'LIVE_READ_ONLY'].includes(String(value.data_mode)) ||
    value.execution_mode !== 'DRY_RUN' || value.approval_mode !== 'PROPOSE_ONLY' ||
    value.live_trading_enabled !== false || value.require_simulation !== true ||
    !['connected', 'unavailable'].includes(String(value.database_status)) ||
    typeof value.service_version !== 'string' || typeof value.run_id !== 'string' ||
    (value.phase !== 1 && value.phase !== 2) || value.gates.DATA_GATE !== 'PASS' ||
    !['NOT_YET_TESTED', 'PASS'].includes(String(value.gates.DRY_RUN_GATE)) ||
    value.gates.SWAP_LIVE_GATE !== 'BLOCKED' || value.gates.RFQ_LIVE_GATE !== 'BLOCKED' ||
    value.gates.AGENTIC_WALLET_LIVE_GATE !== 'BLOCKED' ||
    !(value.demo_fixture === null || (object(value.demo_fixture) &&
      value.demo_fixture.data_mode === 'DEMO' && value.demo_fixture.execution_allowed === false &&
      typeof value.demo_fixture.fixture_id === 'string'))) {
    throw new Error('Backend status could not be verified. Live execution remains unavailable.')
  }
  if ((value.data_mode === 'DEMO' && value.demo_fixture === null) ||
      (value.data_mode === 'LIVE_READ_ONLY' && value.demo_fixture !== null)) {
    throw new Error('Backend status could not be verified. Demo data must remain isolated.')
  }
  return value as unknown as SystemStatus
}

function parseHealth(value: unknown): HealthStatus {
  if (!object(value) || !['ok', 'degraded'].includes(String(value.status)) ||
    !['connected', 'unavailable'].includes(String(value.database_status)) ||
    typeof value.service_version !== 'string' || typeof value.run_id !== 'string') {
    throw new Error('Backend health could not be verified.')
  }
  return value as unknown as HealthStatus
}

async function read(path: string, signal: AbortSignal, correlationId: string): Promise<unknown> {
  const response = await fetch(path, {
    method: 'GET', signal, headers: { 'X-Correlation-ID': correlationId }, cache: 'no-store',
  })
  if (!response.ok) throw new Error('Backend unavailable. Check the local service and retry.')
  return response.json()
}

export async function fetchFoundationStatus(signal: AbortSignal): Promise<FoundationStatus> {
  const correlationId = crypto.randomUUID()
  const controller = new AbortController()
  const abort = () => controller.abort()
  signal.addEventListener('abort', abort, { once: true })
  if (signal.aborted) controller.abort()
  const timer = setTimeout(abort, 5_000)
  let health: unknown
  let system: unknown
  try {
    [health, system] = await Promise.all([
      read('/api/health', controller.signal, correlationId),
      read('/api/system-status', controller.signal, correlationId),
    ])
  } finally {
    abort() // Cancel a sibling read if the other endpoint fails before it completes.
    clearTimeout(timer)
    signal.removeEventListener('abort', abort)
  }
  const parsedHealth = parseHealth(health)
  const parsedSystem = parseSystemStatus(system)
  if (parsedHealth.status !== 'ok' || parsedHealth.database_status !== 'connected' ||
      parsedSystem.database_status !== 'connected' ||
      parsedHealth.run_id !== parsedSystem.run_id) {
    throw new Error('Backend health could not be verified. Retry the status check.')
  }
  return { health: parsedHealth, system: parsedSystem }
}
