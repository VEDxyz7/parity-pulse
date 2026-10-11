import { useState } from 'react'
import type { PresentationAnalysis } from '../types/backend.generated'
const usd=(v:string)=>new Intl.NumberFormat('en-US',{style:'currency',currency:'USD'}).format(Number(v))
/** Single observed snapshot per series, already normalized by the backend. No historical bridge. */
export function ObservationComparison({analysis}:{analysis:PresentationAnalysis}) {
  const [selected,setSelected]=useState<'equity'|'token'|null>(null),row=analysis.trust.representations[0]
  const observations=[{id:'equity' as const,label:'Modeled independent equity',price:analysis.equity_price,at:row.reference.reference_asof,color:'#9becbd'}, {id:'token' as const,label:`${analysis.token_symbol} · effective / share`,price:analysis.effective_cost,at:row.token_timestamp,color:'#66c6dd'}].filter(p=>p.at&&Number.isFinite(Date.parse(p.at))&&Number(p.price)>0)
  const prices=observations.map(p=>Number(p.price)),lo=Math.min(...prices),hi=Math.max(...prices),padding=Math.max((hi-lo)*.35,1),low=lo-padding,high=hi+padding
  const times=observations.map(p=>Date.parse(p.at!)),begin=Math.min(...times),end=Math.max(...times)
  const x=(at:string)=>end===begin?300:100+(Date.parse(at)-begin)/(end-begin)*400
  const y=(value:string)=>25+(high-Number(value))/(high-low)*115
  return <figure className="snapshot-comparison" aria-label="Token and equity scenario comparison"><div className="history-heading"><span className="eyebrow">SCENARIO OBSERVATIONS · USD / SHARE</span><span>Snapshot, not a historical series</span></div>{observations.length?<svg viewBox="0 0 600 180" role="img" aria-label="Independent modeled equity and backend-normalized token observations at recorded timestamps">
    {[0,.5,1].map(p=><g key={p}><line x1="80" x2="550" y1={25+p*115} y2={25+p*115} stroke="#294035"/><text x="70" y={29+p*115} textAnchor="end">{usd(String(high-p*(high-low)))}</text></g>)}
    {observations.map(p=><g key={p.id}><circle data-series={p.id} cx={x(p.at!)} cy={y(p.price)} r={selected===p.id?7:5} fill={p.color} onPointerEnter={()=>setSelected(p.id)} onPointerLeave={()=>setSelected(null)}><title>{p.label}: {usd(p.price)} · {new Date(p.at!).toUTCString()}</title></circle></g>)}
    {[...new Set(observations.map(p=>p.at!))].map(at=><text key={at} x={x(at)} y="166" textAnchor="middle">{new Date(at).toISOString().slice(11,19)} UTC</text>)}
  </svg>:<p>No timestamped comparison observations.</p>}{!observations.some(p=>p.id==='token')&&<p>Token effective/share observation not available with a verified scenario timestamp.</p>}{!observations.some(p=>p.id==='equity')&&<p>Independent modeled equity observation not available with a verified scenario timestamp.</p>}<div className="comparison-legend">{observations.map(p=><button key={p.id} type="button" data-active={selected===p.id} onFocus={()=>setSelected(p.id)} onBlur={()=>setSelected(null)} onClick={()=>setSelected(selected===p.id?null:p.id)}><i style={{background:p.color}}/>{p.label} <strong>{usd(p.price)}</strong><small>{new Date(p.at!).toUTCString()}</small></button>)}</div><figcaption>Isolated scenario sources · {analysis.issuer_name} · backend ratio {analysis.share_ratio} shares/token. Cyan values are already normalized by the backend. No token history is inferred from this snapshot.</figcaption></figure>
}
