import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { apiRequest } from '../services/api'

beforeEach(() => { vi.stubEnv('VITE_API_BASE_URL', ''); vi.stubEnv('DEV', false) })
afterEach(() => { vi.unstubAllEnvs(); vi.unstubAllGlobals() })
const options = () => ({ signal: new AbortController().signal })

it.each(['', '   '])('keeps same-origin requests when API origin is empty (%s)', async value => {
  vi.stubEnv('VITE_API_BASE_URL', value)
  const fetch = vi.fn(async (_url: string, _options?: RequestInit) => new Response('{}')); vi.stubGlobal('fetch', fetch)
  await apiRequest('/api/health', v => v, options())
  expect(fetch.mock.calls[0]).toEqual(['/api/health', expect.objectContaining({ credentials: 'same-origin', redirect: 'error', cache: 'no-store' })])
})

it('preserves the unset environment default', async () => {
  vi.stubEnv('VITE_API_BASE_URL', undefined)
  const fetch = vi.fn(async (_url: string, _options?: RequestInit) => new Response('{}')); vi.stubGlobal('fetch', fetch)
  await apiRequest('/api/health', v => v, options())
  expect(fetch.mock.calls[0][0]).toBe('/api/health')
})

it.each(['https://API.EXAMPLE.TEST/', ' https://api.example.test:443/ '])('normalizes origin %s without changing canonical paths', async base => {
  vi.stubEnv('VITE_API_BASE_URL', base)
  const fetch = vi.fn(async (_url: string, _options?: RequestInit) => new Response('{}')); vi.stubGlobal('fetch', fetch)
  const path = '/api/audit/decisions/decision%3Arun_123?limit=25'
  await apiRequest(path, v => v, options())
  expect(fetch.mock.calls[0][0]).toBe('https://api.example.test' + path)
})

it.each([
  '//api.example.test', 'https:api.example.test', 'https:/api.example.test',
  'http://api.example.test', 'http://localhost:8000', 'javascript:alert(1)',
  'https://user:password@api.example.test', 'https://@api.example.test',
  'https://api.example.test/api', 'https://api.example.test/path/..',
  'https://api.example.test/?', 'https://api.example.test/#',
  'https://api.example.test?key=value', 'https://api.example.test#fragment',
  'https://api.example.test\\evil', 'https://api.example.test\nevil',
  'https://api.example.test:0', 'https://*.example.test', 'https://%61pi.example.test', 'https://api.example.test:99999',
])('refuses invalid production origin %s before fetch', async base => {
  vi.stubEnv('VITE_API_BASE_URL', base)
  const fetch = vi.fn(); vi.stubGlobal('fetch', fetch)
  await expect(apiRequest('/api/health', v => v, options())).rejects.toMatchObject({ code: 'INVALID_RESPONSE' })
  expect(fetch).not.toHaveBeenCalled()
})

it.each(['http://localhost:8000', 'http://127.0.0.1:8000', 'http://[::1]:8000'])('allows explicit local development origin %s', async base => {
  vi.stubEnv('DEV', true); vi.stubEnv('VITE_API_BASE_URL', base)
  const fetch = vi.fn(async (_url: string, _options?: RequestInit) => new Response('{}')); vi.stubGlobal('fetch', fetch)
  await apiRequest('/api/health', v => v, options())
  expect(fetch.mock.calls[0][0]).toBe(base + '/api/health')
})

it.each([
  'https://other.test/api/health', '//other.test/api/health', '/outside',
  '/api/../outside', '/api/%2e%2e/outside', '/api/%252e%252e/outside',
  '/api/\\other.test', '/api//other.test', '/api/example#hidden', '/api/%2f%2fother.test',
])('configured origin cannot be escaped by path %s', async path => {
  vi.stubEnv('VITE_API_BASE_URL', 'https://api.example.test')
  const fetch = vi.fn(); vi.stubGlobal('fetch', fetch)
  await expect(apiRequest(path, v => v, options())).rejects.toMatchObject({ code: 'INVALID_RESPONSE' })
  expect(fetch).not.toHaveBeenCalled()
})

it('retains POST precision, credentials policy, error IDs and no retries cross-origin', async () => {
  vi.stubEnv('VITE_API_BASE_URL', 'https://api.example.test:8443')
  const fetch = vi.fn(async (_url: string, _options?: RequestInit) => new Response('{}', { status: 503, headers: { 'X-Request-ID': 'request-id', 'X-Correlation-ID': 'correlation-id' } })); vi.stubGlobal('fetch', fetch)
  await expect(apiRequest('/api/presentation/research', v => v, { ...options(), body: { budget: '50.123456789' }, correlationId: 'correlation-id' })).rejects.toMatchObject({ code: 'HTTP_ERROR', status: 503, requestId: 'request-id', correlationId: 'correlation-id' })
  expect(fetch).toHaveBeenCalledExactlyOnceWith('https://api.example.test:8443/api/presentation/research', expect.objectContaining({ method: 'POST', credentials: 'same-origin', redirect: 'error', body: '{"budget":"50.123456789"}', headers: expect.objectContaining({ 'X-Correlation-ID': 'correlation-id', 'Content-Type': 'application/json' }) }))
})
