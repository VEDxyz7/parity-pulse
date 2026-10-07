import type { TrustResult } from '../services/trust'

export function TrustEvidence({ result }: { result: TrustResult }) {
  return <div aria-live="polite" className="trust-results">
      <p><strong>{result.ticker ?? 'Unsupported stock'} · {result.status}</strong> · {result.data_mode}</p>
      <p>Evaluated at: <time>{result.evaluated_at}</time></p>
      <p>Market regime: {result.regime?.state ?? 'UNAVAILABLE'} · {result.regime?.baseline_bucket ?? 'No verified schedule'}</p>
      {result.regime && <p>Previous actual regular close: {result.regime.previous_regular_close}</p>}
      {result.representations.map(row => <article className="trust-representation" key={`${row.issuer}:${row.contract}`}>
        <h3>{row.symbol} · {row.issuer}</h3>
        <p><strong>{row.classification}</strong> · Evidence: {row.evidence_quality} · Confidence: {row.confidence ?? 'UNAVAILABLE'}</p>
        <dl className="trust-facts">
          <div><dt>Token USD / token</dt><dd>{row.token_price_usd ?? 'UNAVAILABLE'}</dd></div>
          <div><dt>Shares / token</dt><dd>{row.token_to_share_ratio}</dd></div>
          <div><dt>Token timestamp</dt><dd>{row.token_timestamp ?? 'UNAVAILABLE'}</dd></div>
          <div><dt>Independent equity</dt><dd>{row.reference.status} · {row.reference.observation?.source ?? 'No source'} · {row.reference.observation?.data_quality ?? 'MISSING'} · {row.reference.observation?.price ?? 'No price'}</dd></div>
          <div><dt>Reference as of</dt><dd>{row.reference.reference_asof ?? 'UNAVAILABLE'}</dd></div>
          <div><dt>Timestamp skew / seconds</dt><dd>{row.reference.timestamp_skew_seconds ?? 'UNAVAILABLE'}</dd></div>
          <div><dt>Token age / seconds</dt><dd>{row.reference.token_age_seconds ?? 'UNAVAILABLE'}</dd></div>
          <div><dt>Effective USD / share</dt><dd>{row.economic_comparison?.effective_price_per_share_usd ?? 'UNAVAILABLE'}</dd></div>
          <div><dt>Comparable USD / token</dt><dd>{row.economic_comparison?.comparable_token_value_usd ?? 'UNAVAILABLE'}</dd></div>
          <div><dt>Deviation / fraction</dt><dd>{row.economic_comparison?.deviation ?? 'UNAVAILABLE'}</dd></div>
          <div><dt>Baseline episodes</dt><dd>{row.baseline.sample_count} / {row.baseline.minimum_sample_count} · {row.baseline.status}</dd></div>
          <div><dt>Liquidity / USD</dt><dd>{row.liquidity.liquidity_usd ?? 'UNAVAILABLE'} · {row.liquidity.status}</dd></div>
          <div><dt>News</dt><dd>{row.news.state} · {row.news.coverage} · {row.news.article_ids.length} articles</dd></div>
          <div><dt>Analogues</dt><dd>{row.analogues.retrieved_sample_count} of {row.analogues.eligible_sample_count} · {row.analogues.status}</dd></div>
        </dl>
        <p>Reasons: {row.reason_codes.join(' · ')}</p>
        {row.missing_evidence.length > 0 && <p>Missing evidence: {row.missing_evidence.join(' · ')}</p>}
      </article>)}
      <p>Limitations: {result.limitations.join(' · ')}</p>
      <p>{result.no_broadcast_statement}</p>
    </div>
}
