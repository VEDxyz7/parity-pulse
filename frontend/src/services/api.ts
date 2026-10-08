// One bounded transport; no automatic retries or financial fallback.
export class ApiError extends Error {
  constructor(public readonly code: 'HTTP_ERROR' | 'NETWORK_UNAVAILABLE' | 'INVALID_RESPONSE' | 'REQUEST_TIMEOUT', public readonly status: number | null = null, public readonly requestId: string | null = null, public readonly correlationId: string | null = null) {
    super(`${code === 'REQUEST_TIMEOUT' ? 'Aborted: REQUEST_TIMEOUT' : code}${status === null ? '' : ` (${status})`}. No fallback data or execution was substituted.`)
  }
}
export async function apiRequest<T>(path: string, parse: (value: unknown) => T, options: { signal: AbortSignal; body?: object; method?: 'GET' | 'POST' | 'PUT'; timeout?: number; correlationId?: string }): Promise<T> {
  // Service paths are local canonical paths. Refuse browser normalization,
  // encoded traversal and fragments before any request leaves the client.
  const pathname = path.split('?')[0]
  if (!/^\/api\/(?:[A-Za-z0-9_.:-]|%3[aA]|\/)+(?:\?[^#\\\s]*)?$/.test(path) || pathname.includes('//') || pathname.split('/').some(segment => segment === '.' || segment === '..')) throw new ApiError('INVALID_RESPONSE')
  const controller = new AbortController(), abort = () => controller.abort()
  options.signal.addEventListener('abort', abort, { once: true })
  if (options.signal.aborted) abort()
  const timer = setTimeout(abort, options.timeout ?? 8000)
  try {
    let response: Response
    try {
      response = await fetch(path, { method: options.method ?? (options.body ? 'POST' : 'GET'), signal: controller.signal, cache: 'no-store', credentials: 'same-origin', redirect: 'error', headers: { Accept: 'application/json', 'X-Correlation-ID': options.correlationId ?? crypto.randomUUID(), ...(options.body ? { 'Content-Type': 'application/json' } : {}) }, ...(options.body ? { body: JSON.stringify(options.body) } : {}) })
    } catch {
      // An aborted proposal may already exist. Never automatically resubmit it.
      if (options.signal.aborted) throw new DOMException('Aborted', 'AbortError')
      throw new ApiError(controller.signal.aborted ? 'REQUEST_TIMEOUT' : 'NETWORK_UNAVAILABLE')
    }
    if (!response.ok) throw new ApiError('HTTP_ERROR', response.status, response.headers.get('X-Request-ID'), response.headers.get('X-Correlation-ID'))
    try { return parse(await response.json()) } catch { throw new ApiError('INVALID_RESPONSE') }
  } finally { clearTimeout(timer); options.signal.removeEventListener('abort', abort) }
}
