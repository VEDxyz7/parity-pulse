/** Presentation only. Backend mode, quality and provenance remain unchanged. */
export function dataLabel(mode: string) {
  return mode === 'DEMO' ? 'Illustrative data' : mode === 'LIVE_READ_ONLY' || mode === 'LIVE' ? 'Provider observations · read only' : 'Data unavailable'
}
export function DataContext({ mode }: { mode: string }) {
  return <p className="data-context"><span className="context-dot" aria-hidden="true" />{dataLabel(mode)}<span>·</span>{mode === 'DEMO' ? 'Synthetic inputs, not live market data.' : 'Cached observations; inspect source timestamps and quality.'}<span>·</span>No real funds will move.</p>
}
