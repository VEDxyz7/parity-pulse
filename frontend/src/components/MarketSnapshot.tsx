import { useQuery } from '@tanstack/react-query'
import { ArrowUpRight, Clock3, Layers3, ShieldCheck, TrendingUp } from 'lucide-react'
import { fetchTerminal, type TerminalResult } from '../services/terminal'
import { readRefresh } from '../hooks/readRefresh'
import { DataContext } from './DataContext'
import { StatusBadge } from './StatusBadge'

// Financial fields are exact backend decimal strings. No prices or signals are calculated here.
const money = (value: string | null | undefined) => value == null ? 'Unavailable' : `$${value}`
const label = (value: string | null | undefined) => value?.replaceAll('_', ' ').toLowerCase() ?? 'unavailable'
export function MarketSnapshot({ mode }: { mode?: TerminalResult['data_mode'] }) {
  const query = useQuery({ queryKey: ['terminal', mode, '', 0], queryFn: ({ signal }) => { if (!mode) throw new Error('Verified data context required.'); return fetchTerminal(mode, '', 0, signal) }, ...readRefresh, enabled: mode !== undefined })
  const data = !mode || query.isError || query.isFetching ? null : query.data
  const rows = data?.issuers.items
  const fresh = rows?.filter(row => row.freshness === 'FRESH').length ?? 0
  const freshness = !rows?.length ? 'Unavailable' : fresh === rows.length ? 'Fresh' : fresh === 0 ? 'Not fresh' : 'Mixed'
  return <section className="market-snapshot" aria-label="Market overview">
    <div className="metrics" aria-label="Snapshot coverage">
      <article className="metric"><span>Tracked Assets <Layers3 size={16} /></span><strong>{rows ? new Set(rows.map(row => row.ticker)).size : '—'}</strong><small>In this snapshot{data?.issuers.has_more ? ' · more records available in Markets' : ''}</small></article>
      <article className="metric"><span>Eligible Observations <ShieldCheck size={16} /></span><strong>{rows ? rows.filter(row => row.eligibility === 'ANALYTICAL_ONLY').length : '—'}</strong><small>Backend analytical eligibility · no execution authority</small></article>
      <article className="metric"><span>Largest Verified Deviation <TrendingUp size={16} /></span><strong className="metric-unavailable">Unavailable</strong><small>No verified aggregate supplied by this snapshot</small></article>
      <article className="metric"><span>Data Freshness <Clock3 size={16} /></span><strong className="metric-word">{freshness}</strong><small>{rows?.length ? `${fresh} / ${rows.length} backend-classified fresh${mode === 'DEMO' ? ' · illustrative clock' : ''}` : 'Awaiting verified observations'}</small></article>
    </div>
    <div className="snapshot-context">{mode ? <DataContext mode={mode} /> : <p className="data-context">Data context unavailable · no market values substituted.</p>}<button className="refresh-button" disabled={!mode || query.isFetching} onClick={() => void query.refetch()}>{query.isFetching ? 'Updating snapshot…' : 'Refresh observations'}</button></div>
    {!mode && <p className="snapshot-notice">A verified read-only workflow is required before market values can be displayed.</p>}
    {query.isFetching && <div className="empty-state" role="status"><Clock3 size={22} /><h3>Reading market evidence</h3><p>Prices and comparisons will appear after the backend response is verified.</p></div>}
    {query.isError && <div className="empty-state" role="alert"><h3>Market observations unavailable</h3><p>No prior prices or substitute references are displayed. Retry the snapshot or inspect Data Sources.</p><a href="#settings">Inspect Data Sources <ArrowUpRight size={14} /></a></div>}
    <div className="observation-grid">
      <section className="panel observations-panel" aria-labelledby="recent-observations-title">
        <div className="analytical-heading"><h2 id="recent-observations-title">Recent Market Observations <ArrowUpRight size={16} /></h2><a className="text-link" href="#terminal">View all <ArrowUpRight size={14} /></a></div>
        {!data && <div className="observation-empty"><Layers3 size={22} /><h3>Market observations await verification.</h3><p>{query.isFetching ? 'Reading mode-scoped market observations…' : 'Token prices, independent references and deviations remain unavailable until verified.'}</p></div>}
        {data && <>
      <div className="comparison-scroll snapshot-table" tabIndex={0} role="region" aria-label="Tokenized equity comparison">
        <table><caption>Tokenized equity comparison <span>USD · backend-computed values · timestamps in UTC</span></caption><thead><tr>{['Underlying / issuer', 'Token price', 'Effective $/share', 'Independent equity', 'Spread / deviation', 'Session / evidence', 'Observation'].map(name => <th scope="col" key={name}>{name}</th>)}</tr></thead>
          <tbody>{data.issuers.items.map(row => <tr key={`${row.ticker}:${row.chain_id}:${row.contract}`}>
            <td><strong>{row.ticker}</strong><small>{row.token}</small><details><summary>Representation</summary><p>{row.company} · {row.issuer}</p><p>{row.chain_id} / {row.contract}</p><p>{row.token_to_share_ratio} shares/token</p><p>Ratio observed <time>{row.ratio_observed_at}</time></p><p>Ratio source as of {row.ratio_source_timestamp ?? 'Unavailable'}</p></details></td>
            <td>{money(row.token_price_usd)}</td><td>{money(row.effective_price_per_share_usd)}</td>
            <td>{money(row.independent_equity_price_usd)}<small>{label(row.reference.status)}</small><details><summary>Reference time</summary><time>{row.reference.reference_asof ?? 'No verified reference time'}</time></details></td>
            <td>{money(row.spread_usd_per_share)}<small>{row.deviation_percent === null ? 'Deviation unavailable' : `${row.deviation_percent}%`}</small><details><summary>Alignment</summary><p>{row.reference.timestamp_skew_seconds ?? 'Unavailable'} seconds</p></details></td>
            <td><span>{label(row.regime)}</span><small>{label(row.trust.classification)}</small><details><summary>Why this classification?</summary><p>{label(row.eligibility)}</p><p>{row.reasons.join(' · ') || 'No rejection recorded'}</p><p>Liquidity: {money(row.liquidity.liquidity_usd)} · {label(row.liquidity.status)}</p><p>24h USD volume: {money(row.liquidity.volume_24h_usd)}</p><p>Tradable: {row.tradable === null ? 'Unknown' : row.tradable ? 'Yes' : 'No'} · {row.market_state}</p><p>Route: {row.route_status}</p></details></td>
            <td><StatusBadge tone={row.freshness === 'FRESH' ? 'green' : 'amber'}>{label(row.freshness)}</StatusBadge><details><summary>Source &amp; timestamps</summary>{row.observations.map((observation, index) => <div key={index} className="source-record"><p>{observation.source} · {observation.data_quality === 'DEMO' ? 'Illustrative data' : observation.data_quality}</p><p>Observed <time>{observation.observed_at ?? 'Unavailable'}</time></p><p>Available <time>{observation.available_at}</time></p><p>{observation.provider_identifier}</p><code>{observation.digest}</code></div>)}</details></td>
          </tr>)}</tbody></table>
      </div>
      {!data.issuers.items.length && <div className="empty-state"><h3>No cached representations</h3><p>This snapshot has no asset observations. Missing prices and independent references remain unavailable.</p></div>}
        </>}
      </section>
      <section className="panel deviation-panel" aria-labelledby="deviation-trend-title">
        <div className="analytical-heading"><h2 id="deviation-trend-title">Deviation Trend <ArrowUpRight size={16} /></h2><span className="status-badge amber">Unavailable</span></div>
        <div className="trend-empty"><div className="trend-grid" aria-hidden="true" /><div className="trend-message"><TrendingUp size={26} /><h3>Evidence takes a timeline.</h3><p>A verified trend cannot currently be plotted. This snapshot does not supply an aligned token/equity historical series.</p><a className="text-link" href="#trust">Inspect evidence requirements <ArrowUpRight size={14} /></a></div></div>
        <div className="trend-footnote"><span className="context-dot" aria-hidden="true" />No series plotted · no asset pair selected</div>
      </section>
    </div>
    {data && <>
      <div className="snapshot-footer"><span>Snapshot generated <time>{data.generated_at}</time> · Observation times are recorded separately.</span><a href="#terminal">Explore Markets <ArrowUpRight size={14} /></a></div>
      <div className="insight-grid">
        <section className="panel insight-panel"><span className="eyebrow">02 / TRUST &amp; SIGNALS</span><h2>Evidence before conviction.</h2><article className="assessment-coverage"><strong>{data.trust.items.filter(row => row.assessment_id !== null).length}</strong><small>Stored assessment IDs in this snapshot</small></article><p>Existing assessments retain their original age and limitations. A historical classification is not a current opportunity.</p>
          {!data.trust.items.length && <p className="empty-copy">No stored Trust assessments. Run an assessment below to inspect current evidence.</p>}
          {data.trust.items.slice(0, 3).map((row, index) => <article key={index} className="evidence-row"><strong>{row.ticker} <span>{row.issuer}</span></strong><p>{label(row.classification)} · {label(row.freshness)}</p><small>Assessed <time>{row.assessed_at ?? 'Unavailable'}</time> · Age {row.age_seconds ?? 'Unavailable'} seconds</small><details><summary>Evidence limitations</summary><p>{row.reasons.join(' · ')}</p>{row.stored_evidence && <p>Baseline: {row.stored_evidence.baseline.sample_count} ({row.stored_evidence.baseline.status}) · Analogues: {row.stored_evidence.analogues.retrieved_sample_count} ({row.stored_evidence.analogues.status}) · News: {row.stored_evidence.news.coverage}</p>}</details></article>)}
          <a className="text-link" href="#trust">Inspect Trust &amp; Signals <ArrowUpRight size={14} /></a>
        </section>
        <section className="panel insight-panel"><span className="eyebrow">03 / ACTIVITY &amp; CONTEXT</span><h2>A traceable decision trail.</h2><p>Proposals, simulations and settled trades remain separate.</p>
          {!data.executions.items.length && <p className="empty-copy">No recorded execution attempts in this snapshot.</p>}
          {data.executions.items.slice(0, 3).map(row => <article className="evidence-row" key={row.execution_id}><strong>{label(row.category)}</strong><p>{row.synthetic ? 'Illustrative record — not a real trade' : row.source} · Completed trade: {row.actual_completed_trade ? 'Yes' : 'No'}</p><small><time>{row.updated_at}</time></small><a className="text-link" href="#audit">Inspect decision <ArrowUpRight size={14} /></a></article>)}
          <p className="empty-copy">News and event context are not exposed by this snapshot API. No event feed is inferred.</p><a className="text-link" href="#audit">View Scorecard &amp; Audit <ArrowUpRight size={14} /></a>
        </section>
      </div>
      <details className="snapshot-provenance"><summary>Snapshot provenance &amp; coverage limitations</summary><p>Request {data.request_id} · Run {data.run_id}</p><p>{data.limitations.join(' · ') || 'No additional limitations recorded.'}</p><p>Lists are bounded to the first 25 records. See Markets for filters and pagination. No provider refresh or execution is triggered by this view.</p></details>
    </>}
  </section>
}
