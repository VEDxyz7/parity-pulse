import type { HealthStatus, SystemStatus } from '../types/system'

// Synthetic DEMO foundation metadata only; never a fallback for live failures.
export const systemFixture: SystemStatus = {
  environment: 'test', data_mode: 'DEMO', execution_mode: 'DRY_RUN',
  approval_mode: 'PROPOSE_ONLY', live_trading_enabled: false, require_simulation: true,
  database_status: 'connected', service_version: '0.1.0', phase: 1,
  run_id: '00000000-0000-4000-8000-000000000001',
  gates: {
    DATA_GATE: 'PASS', DRY_RUN_GATE: 'NOT_YET_TESTED', SWAP_LIVE_GATE: 'BLOCKED',
    RFQ_LIVE_GATE: 'BLOCKED', AGENTIC_WALLET_LIVE_GATE: 'BLOCKED',
  },
  demo_fixture: { fixture_id: 'parity-pulse-foundation-v1', data_mode: 'DEMO', execution_allowed: false },
}

export const healthFixture: HealthStatus = {
  status: 'ok', database_status: 'connected', service_version: '0.1.0',
  run_id: systemFixture.run_id,
}
