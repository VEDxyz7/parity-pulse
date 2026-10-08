import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { AgentApi } from '../components/AgentApi'
import { parseCatalog, toolNames } from '../services/agentApi'
import saved from './agentApiFixtures.json'
const fixture = { ...saved.catalog, tools: saved.catalog.tools.map(tool => ({ ...tool, outputSchema: saved.outputSchema })) }
import scorecards from './scorecardFixtures.json'
import { parseEvaluation } from '../services/scorecard'

afterEach(() => vi.unstubAllGlobals())
describe('Phase 14 inspection only', () => {
  it('renders all seven tools, boundaries and structured examples using GET only', async () => {
    const mock = vi.fn(async (_url: string) => new Response(JSON.stringify(fixture)))
    vi.stubGlobal('fetch', mock)
    render(<AgentApi />)
    expect(screen.getByRole('status')).toHaveTextContent('Loading tool schemas')
    await screen.findByText(/Backend: Ready/)
    for (const name of toolNames) expect(screen.getByText(name)).toBeInTheDocument()
    expect(screen.getByText(/NO REAL FUNDS WILL MOVE/)).toBeInTheDocument()
    expect(screen.getByText(/explicit risk budget and a stable idempotency key/)).toBeInTheDocument()
    expect(mock).toHaveBeenCalledTimes(1)
    expect(mock.mock.calls[0][0]).toBe('/api/agent/tools')
    expect(screen.queryByRole('button', { name: /execute|trade|run|sign/i })).not.toBeInTheDocument()
  })
  it('shows a safe unavailable state and recovers without invoking a tool', async () => {
    const mock = vi.fn().mockResolvedValueOnce(new Response('', { status: 503 })).mockResolvedValueOnce(new Response(JSON.stringify(fixture)))
    vi.stubGlobal('fetch', mock)
    render(<AgentApi />)
    await screen.findByRole('alert')
    await userEvent.click(screen.getByRole('button', { name: 'Retry catalog' }))
    await screen.findByText(/Backend: Ready/)
    expect(mock.mock.calls.every(([url]) => url === '/api/agent/tools')).toBe(true)
  })
  it.each(['missing', 'duplicate', 'executable', 'foreign', 'weak-schema', 'wrong-boundary'])('refuses an unsafe %s catalog', kind => {
    const body = structuredClone(fixture)
    if (kind === 'missing') body.tools.pop()
    if (kind === 'duplicate') body.tools[1].name = body.tools[0].name
    if (kind === 'executable') body.execution_ready = true
    if (kind === 'foreign') body.tools[0].name = 'execute_trade'
    if (kind === 'weak-schema') body.tools[0].inputSchema.additionalProperties = true
    if (kind === 'wrong-boundary') body.tools[0].annotations.readOnlyHint = true
    expect(() => parseCatalog(body)).toThrow('Tool catalog could not be verified')
  })
  it('accepts the new observed invocation audit kind while keeping all prior boundaries', () => {
    const body = structuredClone(scorecards.trace)
    body.events[0].capture_kind = 'OBSERVED_TOOL_INVOCATION'
    expect(parseEvaluation(body, 'DEMO', true)).toBeDefined()
    body.events[0].capture_kind = 'FAKE_EXECUTION'
    expect(() => parseEvaluation(body, 'DEMO', true)).toThrow()
  })
})
