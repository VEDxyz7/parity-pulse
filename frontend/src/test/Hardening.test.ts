import { afterEach, expect, it, vi } from 'vitest'
import { apiRequest } from '../services/api'
import { validateWire } from '../services/contracts'
import fixtures from './workspaceFixtures.json'

afterEach(() => vi.unstubAllGlobals())

it.each(['2026-02-30T12:00:00Z', '2026-04-31T12:00:00Z', '2025-02-29T12:00:00Z', '2026-10-09T24:00:00Z', '2026-10-09 12:00:00Z'])('rejects non-calendar timestamp %s instead of JavaScript date coercion', generated_at => {
  expect(() => validateWire('WorkspaceState', { ...fixtures.workspace_empty, generated_at })).toThrow('could not be verified')
})

it.each(['2024-02-29T12:00:00Z', '2026-10-09T12:00:00.123456+05:30'])('retains valid timestamp %s without coercion', generated_at => {
  const body = { ...fixtures.workspace_empty, generated_at }
  expect(validateWire('WorkspaceState', body)).toBe(body)
})

it.each(['/api/../outside', '/api/%2e%2e/outside', '/api/\\outside', '/api/example#hidden', '/api//example'])('refuses non-canonical API path %s before fetch', async path => {
  const fetch = vi.fn(); vi.stubGlobal('fetch', fetch)
  await expect(apiRequest(path, v => v, { signal: new AbortController().signal })).rejects.toMatchObject({ code: 'INVALID_RESPONSE' })
  expect(fetch).not.toHaveBeenCalled()
})

it.each(['/api/audit/decisions/decision%3Arun_123?limit=25', '/api/audit/decisions/v1.0-run'])('preserves supported encoded/dotted decision path %s', async path => {
  const fetch = vi.fn(async (_path: string) => new Response('{}', { headers: { 'Content-Type': 'application/json' } })); vi.stubGlobal('fetch', fetch)
  await expect(apiRequest(path, v => v, { signal: new AbortController().signal })).resolves.toEqual({})
  expect(fetch).toHaveBeenCalledTimes(1)
  expect(fetch.mock.calls[0][0]).toBe(path)
})
