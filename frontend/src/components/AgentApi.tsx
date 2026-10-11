import { Button } from '../ui/Button'
import { dataLabel } from './DataContext'
import { useEffect, useState } from 'react'
import { getCatalog, type ToolCatalog } from '../services/agentApi'

export function AgentApi() {
  const [catalog, setCatalog] = useState<ToolCatalog | null>(null)
  const [error, setError] = useState(false)
  const [attempt, setAttempt] = useState(0)
  useEffect(() => {
    const controller = new AbortController()
    const timer = setTimeout(() => controller.abort(), 8000)
    setCatalog(null); setError(false)
    getCatalog(controller.signal).then(setCatalog).catch(() => { if (!controller.signal.aborted) setError(true) })
    controller.signal.addEventListener('abort', () => setError(true))
    return () => { clearTimeout(timer); controller.abort() }
  }, [attempt])
  return <section className="panel agent-api-inspection" aria-label="Agent API inspection">
    <div className="panel-heading"><div><div className="eyebrow">BOUNDED TOOLS / NON-LIVE</div><h1>Agent API</h1><p>Seven typed tools use the same backend authority as the application.</p></div></div>
    <p><strong>PROPOSE ONLY · SIMULATION REQUIRED · NO REAL FUNDS WILL MOVE</strong></p>
    <p>Inspection and examples only. Tool calls cannot sign, broadcast, submit RFQs, or modify wallet and portfolio rules.</p>
    {error ? <div role="alert"><p>The tool catalog is unavailable or could not be verified.</p><Button className="refresh-button" onClick={() => setAttempt(n => n + 1)}>Retry catalog</Button></div> : !catalog ? <p role="status">Loading tool schemas…</p> : <>
      <p>Backend: {catalog.ready ? 'Ready' : 'Unavailable'} · {dataLabel(catalog.data_mode)} · MCP stdio + bounded HTTP JSON</p>
      <pre>{'PYTHONPATH=backend .venv/bin/python -m app.mcp_server --port 8000'}</pre>
      <p>Proposal calls require an explicit risk budget and a stable idempotency key. A retry uses the same key; an uncertain response never authorizes another order.</p>
      <pre>{JSON.stringify({ tool: 'buy_stock_exposure', arguments: { ticker: 'NVDA', amount_usd: '50', risk_budget_usd: '5', mode: 'PROPOSE_ONLY', idempotency_key: '00000000-0000-4000-8000-000000000001' } }, null, 2)}</pre>
      <p>This is a request example, not a quote or completed trade. Provider routes, fees and simulation remain unavailable unless the existing backend verifies them.</p>
      {catalog.tools.map(tool => <details key={tool.name}><summary><code>{tool.name}</code> · {tool.annotations.readOnlyHint ? 'Read / analytical' : 'Decision / proposal'}</summary><p>{tool.description}</p><h3>Request schema</h3><pre>{JSON.stringify(tool.inputSchema, null, 2)}</pre><h3>Response schema</h3><pre>{JSON.stringify(tool.outputSchema, null, 2)}</pre></details>)}
    </>}
  </section>
}
