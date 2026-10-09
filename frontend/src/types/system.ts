export type GateState = 'PASS' | 'NOT_YET_TESTED' | 'BLOCKED'
export type GateName =
  | 'DATA_GATE' | 'DRY_RUN_GATE' | 'SWAP_LIVE_GATE'
  | 'RFQ_LIVE_GATE' | 'AGENTIC_WALLET_LIVE_GATE'

export interface SystemStatus {
  runtime_mode?: 'DEMO'
  environment: 'development' | 'test' | 'production'
  data_mode: 'DEMO' | 'LIVE_READ_ONLY'
  execution_mode: 'DRY_RUN' | 'LIVE'
  approval_mode: 'PROPOSE_ONLY' | 'AUTONOMOUS'
  live_trading_enabled: boolean
  require_simulation: true
  database_status: 'connected' | 'unavailable'
  service_version: string
  phase: 1 | 2
  run_id: string
  gates: Record<GateName, GateState>
  demo_fixture: {
    fixture_id: string
    data_mode: 'DEMO'
    execution_allowed: false
  } | null
}

export interface HealthStatus {
  status: 'ok' | 'degraded'
  database_status: 'connected' | 'unavailable'
  service_version: string
  run_id: string
}

export interface FoundationStatus {
  system: SystemStatus
  health: HealthStatus
}
