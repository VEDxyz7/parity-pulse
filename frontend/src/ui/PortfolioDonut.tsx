import { useState } from 'react'
import type { PresentationWorkspace_Holding as Holding } from '../types/backend.generated'
import { AssetIdentity, holdingColor } from './AssetIdentity'
const money=(v:string)=>new Intl.NumberFormat('en-US',{style:'currency',currency:'USD'}).format(Number(v))
const percent=(v:string)=>`${(Number(v)*100).toFixed(2)}%`
export function PortfolioDonut({holdings,total,filter='all'}:{holdings:Holding[];total:string;filter?:string}) {
  const [active,setActive]=useState<string|null>(null)
  const valid=holdings.filter(h=>Number(h.value)>0&&Number(h.weight)>0)
  let offset=0
  const slices=valid.map(h=>{const start=offset;offset+=Number(h.weight);return {h,start,key:`${h.ticker}:${h.issuer}`}})
  const selected=slices.find(s=>s.key===active)?.h
  return <figure className="allocation-chart" aria-label="Portfolio allocation">
    <div className="donut-plot"><svg viewBox="0 0 240 240" role="img" aria-label={`Full portfolio allocation, ${money(total)}, ${valid.length} holdings`}>
      <circle cx="120" cy="120" r="84" fill="none" stroke="#203d2e" strokeWidth="24"/>
      {slices.map(({h,start,key})=><circle key={key} className="allocation-slice" data-holding={key} cx="120" cy="120" r="84" fill="none" pathLength="1" stroke={holdingColor(h.ticker,h.issuer)} strokeWidth={active===key?30:24} strokeDasharray={`${Number(h.weight)} ${1-Number(h.weight)}`} strokeDashoffset={-start} transform="rotate(-90 120 120)" opacity={filter!=='all'&&filter!==h.ticker? .35:1} onPointerEnter={()=>setActive(key)} onPointerLeave={()=>setActive(null)}><title>{h.ticker} · {h.issuer} · {money(h.value)} · {percent(h.weight)}</title></circle>)}
      <text x="120" y="108" textAnchor="middle" className="donut-caption">{selected?selected.ticker:'TOTAL VALUE'}</text><text x="120" y="132" textAnchor="middle" className="donut-value">{money(selected?.value??total)}</text><text x="120" y="154" textAnchor="middle" className="donut-caption">{selected?percent(selected.weight):'MODELED HOLDINGS'}</text>
    </svg></div>
    <div className="allocation-legend">{slices.map(({h,key})=><button type="button" key={key} className="allocation-key" data-active={active===key} onPointerEnter={()=>setActive(key)} onPointerLeave={()=>setActive(null)} onFocus={()=>setActive(key)} onBlur={()=>setActive(null)} onClick={()=>setActive(active===key?null:key)} aria-label={`${h.ticker} ${h.issuer}: ${money(h.value)}, ${percent(h.weight)}`}><i style={{background:holdingColor(h.ticker,h.issuer)}}/><AssetIdentity ticker={h.ticker} issuer={h.issuer}/><span>{money(h.value)}<small>{percent(h.weight)}</small></span></button>)}{!valid.length&&<p>No valued holdings to display.</p>}<p className="muted">Full portfolio · {filter==='all'?'all holdings shown':`${filter} table filter highlighted`}. Backend weights and valuations; displayed percentages may round.</p></div>
  </figure>
}
