import type { RouteDecision } from '../services/routing'

export function RouteComparison({ route, expired = false }: { route: RouteDecision; expired?: boolean }) {
  return <section className="route-comparison" aria-label="Route Decision">
    <h4>Route Decision: <strong>{expired ? 'EXPIRED' : route.status}</strong></h4>
    <p>{route.data_mode === 'DEMO' ? 'Illustrative routing — synthetic inputs, not live market data' : 'Read-only routing — no execution'}</p>
    <p>{route.explanation}</p>
    <p>Purpose: {route.policy.purpose} · Ranking: {route.ranking_basis} · No weighted score; exact cost, then issuer/chain/contract/token.</p>
    {!expired && route.selected_representation && <p><strong>Selected route:</strong> {route.selected_representation.issuer} / {route.selected_representation.token} · {route.selected_representation.chain_id} / {route.selected_representation.contract}</p>}
    <div className="comparison-scroll" tabIndex={0} role="region" aria-label="Route comparison table"><table>
      <caption>Route Comparison — {route.underlying ?? 'unresolved stock'}</caption>
      <thead><tr><th>Issuer / Token</th><th>Effective exposure cost / USD per share</th><th>Liquidity / USD</th><th>Estimated fees / gas / USD</th><th>Estimated slippage / bps</th><th>Trust</th><th>Tradability</th><th>Decision</th></tr></thead>
      <tbody>{route.candidates.map(c => <tr key={`${c.candidate_id}:${c.inputs.identity.issuer}`}>
        <td>{c.inputs.identity.issuer} / {c.inputs.identity.token}</td>
        <td>{c.ranking_cost_per_share_usd ?? c.effective_cost_per_share_usd ?? 'Unavailable'}<br /><span>{c.all_in_cost_per_share_usd ? `All-in estimate: ${c.all_in_cost_per_share_usd}` : 'All-in cost unavailable'}</span></td>
        <td>{c.inputs.liquidity_usd ?? 'Unknown'} · {c.liquidity_state}</td>
        <td>{c.inputs.fees_usd ?? 'Unknown'} / {c.inputs.gas_usd ?? 'Unknown'} · {c.cost_state}</td>
        <td>{c.inputs.slippage_bps ?? 'Unknown'}</td>
        <td>{c.trust_state}</td><td>{c.tradability} / {c.inputs.market_state}</td>
        <td><strong>{expired ? 'Historical only' : c.rank === 1 ? 'SELECTED' : c.eligible ? `Eligible · rank ${c.rank}` : 'REJECTED'}</strong><br />{c.rejection_reasons.join(' · ') || c.limitations.join(' · ')}</td>
      </tr>)}</tbody>
    </table></div>
    <p>Source: {route.source} · As of {route.timestamp} · Valid until {route.valid_until}. Execution readiness: BLOCKED.</p>
    <details><summary>Route policy, ranking inputs and provenance</summary><pre>{JSON.stringify(route, null, 2)}</pre></details>
  </section>
}
