import { apiRequest } from './api'
export const toolNames = ['buy_stock_exposure', 'find_opportunity', 'compare_stock_tokens', 'get_stock_trust', 'get_route', 'get_portfolio', 'get_autopilot_status'] as const
export type ToolName = typeof toolNames[number]
export type ToolCatalog = {
  schema_version: 'agent-api-1'; transport: 'HTTP_JSON_AND_MCP_STDIO'; authority: 'EXISTING_BACKEND_SERVICES'
  execution_ready: false; ready: boolean; data_mode: 'DEMO' | 'LIVE_READ_ONLY'
  tools: { name: ToolName; description: string; inputSchema: Record<string, unknown>; outputSchema: Record<string, unknown>
    annotations: { readOnlyHint: boolean; destructiveHint: false; idempotentHint: true; openWorldHint: true } }[]
}
const obj = (v: unknown): v is Record<string, unknown> => typeof v === 'object' && v !== null && !Array.isArray(v)
export function parseCatalog(value: unknown): ToolCatalog {
  if (!obj(value) || value.schema_version !== 'agent-api-1' || value.transport !== 'HTTP_JSON_AND_MCP_STDIO' || value.authority !== 'EXISTING_BACKEND_SERVICES' || value.execution_ready !== false || typeof value.ready !== 'boolean' || !['DEMO', 'LIVE_READ_ONLY'].includes(String(value.data_mode)) || !Array.isArray(value.tools) || value.tools.length !== 7) throw new Error('Tool catalog could not be verified.')
  const seen = new Set()
  for (const tool of value.tools) {
    if (!obj(tool) || !toolNames.includes(tool.name as ToolName) || seen.has(tool.name) || typeof tool.description !== 'string' || !obj(tool.inputSchema) || !obj(tool.outputSchema) || tool.inputSchema.type !== 'object' || tool.inputSchema.additionalProperties !== false || !obj(tool.annotations) || tool.annotations.destructiveHint !== false || tool.annotations.idempotentHint !== true || tool.annotations.openWorldHint !== true || tool.annotations.readOnlyHint !== !['buy_stock_exposure', 'find_opportunity'].includes(String(tool.name))) throw new Error('Tool catalog could not be verified.')
    seen.add(tool.name)
  }
  return value as ToolCatalog
}
export async function getCatalog(signal: AbortSignal) {
  return apiRequest('/api/agent/tools', parseCatalog, { signal })
}
