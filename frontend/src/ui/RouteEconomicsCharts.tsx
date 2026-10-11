import { useState } from 'react'
import type { RouteDecision, RouteDecision_RouteCandidate as Candidate, RouteDecision_RouteInput as Input } from '../types/backend.generated'
import { AssetIdentity, holdingColor } from './AssetIdentity'
const money=(v:string|null|undefined)=>v==null?'Cost not established':new Intl.NumberFormat('en-US',{style:'currency',currency:'USD',maximumFractionDigits:4}).format(Number(v))
/** Render backend economics only. Scaling bars does not rank, normalize or authorize a route. */
type ChartRoute = Pick<RouteDecision,'underlying'|'requested_notional_usd'|'timestamp'|'data_mode'> & {
  selected_candidate: Pick<Candidate,'candidate_id'> | null
  candidates: (Pick<Candidate,'candidate_id'|'eligible'|'rejection_reasons'|'limitations'|'effective_cost_per_share_usd'|'all_in_cost_per_share_usd'|'estimated_costs_usd'> & {inputs:Pick<Input,'identity'|'fees_usd'|'gas_usd'|'slippage_bps'>})[]
}
export function RouteEconomicsCharts({route,expired=false}:{route:ChartRoute;expired?:boolean}) {
  const [active,setActive]=useState<string|null>(null)
  const selected=expired?null:route.selected_candidate?.candidate_id
  const fields=[['effective_cost_per_share_usd','Price per effective share'],['all_in_cost_per_share_usd','All-in cost per effective share']] as const
  const focus=route.candidates.find(c=>c.candidate_id===active)
  return <section className="route-graphics" aria-label="Synchronized route economics">
    <div className="route-chart-heading"><span className="eyebrow">{route.underlying} · {money(route.requested_notional_usd)} REQUEST</span><span>USD / real share · backend estimates</span></div>
    <div className="route-chart-grid">{fields.map(([field,label])=>{
      const values=route.candidates.map(c=>Number(c[field])).filter(v=>Number.isFinite(v)&&v>0),max=Math.max(...values,1)
      return <figure className="route-economics" key={field} aria-label={label}><figcaption>{label}</figcaption><div className="bar-scale"><span>$0</span><span>{money(String(max))}</span></div>{route.candidates.map(c=>{
        const value=c[field],finite=value!==null&&Number.isFinite(Number(value))&&Number(value)>=0
        return <button type="button" key={c.candidate_id} className="route-bar" data-active={active===c.candidate_id} data-selected={selected===c.candidate_id} data-eligible={c.eligible&&!expired} onPointerEnter={()=>setActive(c.candidate_id)} onPointerLeave={()=>setActive(null)} onFocus={()=>setActive(c.candidate_id)} onBlur={()=>setActive(null)} onClick={()=>setActive(active===c.candidate_id?null:c.candidate_id)} aria-label={`${c.inputs.identity.token}, ${label}: ${money(value)}, ${expired?'expired':!c.eligible?'rejected':selected===c.candidate_id?'selected proposal':'eligible alternative'}`}>
          <div className="bar-label"><span>{c.inputs.identity.token}</span><strong>{money(value)}</strong></div><div className="bar-track"><i style={{width:finite?`${Number(value)/max*100}%`:'0%',background:holdingColor(c.inputs.identity.underlying,c.inputs.identity.issuer)}}/></div><small>{expired?'Expired · historical comparison':!c.eligible?'Rejected · not eligible':selected===c.candidate_id?'Selected proposal':'Eligible alternative'}</small>
        </button>
      })}</figure>
    })}</div>
    <div className="route-hover" aria-live="polite">{focus?<><AssetIdentity ticker={focus.inputs.identity.underlying} issuer={focus.inputs.identity.issuer} detail={focus.inputs.identity.token}/><p>Fees {money(focus.inputs.fees_usd)} · gas {money(focus.inputs.gas_usd)} · slippage {focus.inputs.slippage_bps??'not established'} bps · total estimated costs {money(focus.estimated_costs_usd)}.</p><p>{focus.rejection_reasons.join('; ')||focus.limitations.join('; ')||'Values from the route response; no execution authorization.'}</p></>:<p>Hover, focus or tap a representation to inspect both charts. Same candidates and exact backend values as the table.</p>}</div>
    <p className="muted">{route.data_mode==='DEMO'?'Scenario costs and liquidity assumptions; not executable market quotes.':'Read-only estimates with provider provenance; missing costs remain unestablished.'} As of {new Date(route.timestamp).toUTCString()}. {expired?'Route expired.':'Comparison only.'}</p>
  </section>
}
