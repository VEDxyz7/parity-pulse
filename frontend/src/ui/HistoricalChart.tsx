import { useEffect, useId, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { apiRequest } from '../services/api'
import { validateWire } from '../services/contracts'
import type { DisplayHistory } from '../types/backend.generated'
import { sessionGeometry } from './chartGeometry'
import { Button } from './Button'
import { AssetLogo } from './AssetIdentity'
const price=(v:string|number)=>new Intl.NumberFormat('en-US',{style:'currency',currency:'USD'}).format(Number(v))
const date=(at:string)=>new Date(at).toLocaleString('en-GB',{timeZone:'UTC',month:'short',day:'2-digit',hour:'2-digit',minute:'2-digit',hour12:false})
/** Observed historical bars only. Compress known session closures, never interpolate missing bars. */
export function HistoricalChart({ticker}:{ticker:'NVDA'|'AAPL'}) {
  const id=useId(),host=useRef<HTMLElement>(null),[width,setWidth]=useState(720),[selected,setSelected]=useState<number|null>(null),[period,setPeriod]=useState<'1D'|'1W'>('1W')
  useEffect(()=>{
    if(!host.current||typeof ResizeObserver==='undefined')return
    const observer=new ResizeObserver(entries=>setWidth(Math.max(300,Math.min(1000,entries[0].contentRect.width))))
    observer.observe(host.current);return()=>observer.disconnect()
  },[])
  const query=useQuery({queryKey:['display-history',ticker],queryFn:({signal})=>apiRequest(`/api/display-history/${ticker}`,v=>validateWire<DisplayHistory>('DisplayHistory',v),{signal}),staleTime:Infinity,retry:false})
  const data=query.data,all=data?.observations??[],lastDay=all.at(-1)?.source_timestamp?.slice(0,10)
  const rows=period==='1D'?all.filter(r=>r.source_timestamp?.slice(0,10)===lastDay):all
  const ready=data?.status==='AVAILABLE'&&rows.length>0
  if(!ready)return <figure ref={host} className="historical-chart chart-empty" aria-label={`${ticker} historical equity prices`}><span className="eyebrow">INDEPENDENT EQUITY HISTORY · {ticker}</span><p role="status">{query.isPending?'Reading historical capture…':'Historical series not captured.'}</p><figcaption>October 5–9, 2026 requested. No invented price curve is substituted. Scenario prices remain separate.</figcaption></figure>
  const geometry=sessionGeometry(rows.map(r=>r.source_timestamp!),rows.map(r=>Number(r.close)),width),{x,y,path,area,low,high,gaps}=geometry
  const index=Math.min(selected??rows.length-1,rows.length-1),row=rows[index],summary=data.periods?.find(p=>p.period===period)
  const days=rows.flatMap((r,i)=>i===0||r.source_timestamp!.slice(0,10)!==rows[i-1].source_timestamp!.slice(0,10)?[i]:[])
  const inspect=(e:React.PointerEvent<SVGSVGElement>)=>{const rect=e.currentTarget.getBoundingClientRect(),position=(e.clientX-rect.left)/rect.width*width;let nearest=0;rows.forEach((_,i)=>{if(Math.abs(x(i)-position)<Math.abs(x(nearest)-position))nearest=i});setSelected(nearest)}
  return <figure ref={host} className="historical-chart" aria-labelledby={`${id}-title`}>
    <div className="history-heading"><span id={`${id}-title`} className="eyebrow chart-brand"><AssetLogo ticker={ticker}/>{ticker} · HISTORICAL EQUITY</span><div className="chart-periods" role="group" aria-label={`${ticker} captured history period`}>{(['1D','1W'] as const).map(p=><Button key={p} type="button" variant="compact" aria-pressed={period===p} onClick={()=>{setPeriod(p);setSelected(null)}}>{p}</Button>)}</div></div>
    <div className="history-readout" aria-live="off"><strong>{price(row.close!)}</strong><span>{date(row.source_timestamp!)} UTC · bar start</span>{summary&&<span className={Number(summary.change_fraction)>=0?'positive-text':'negative-text'}>{Number(summary.change_fraction)>=0?'+':''}{(Number(summary.change_fraction)*100).toFixed(2)}% · {period} first → last close</span>}</div>
    <svg viewBox={`0 0 ${width} 215`} role="img" aria-label={`${ticker} actual five-minute equity closing prices, USD. Regular overnight closures compressed; missing bars remain gaps.`} onPointerDown={inspect} onPointerMove={inspect} onPointerLeave={()=>setSelected(null)}>
      <defs><linearGradient id={`${id}-fill`} x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#76eeb3" stopOpacity=".18"/><stop offset="100%" stopColor="#76eeb3" stopOpacity="0"/></linearGradient></defs>
      {[0,.5,1].map(p=><g key={p}><line x1="58" x2={width-24} y1={20+p*158} y2={20+p*158} stroke="#294035"/><text x="48" y={24+p*158} textAnchor="end">{price(high-p*(high-low))}</text></g>)}
      {days.map(i=><g key={i}><line x1={x(i)} x2={x(i)} y1="20" y2="178" stroke="#294035" strokeDasharray="2 7"/><text x={x(i)+5} y="202" textAnchor="start">Oct {rows[i].source_timestamp!.slice(8,10)}</text></g>)}
      <path className="price-area" d={area} fill={`url(#${id}-fill)`}/><path className="price-line" d={path} fill="none" stroke="#9becbd" strokeWidth="2" strokeLinejoin="round"/>
      <circle className="latest-point" cx={x(rows.length-1)} cy={y(rows.length-1)} r="3.5" fill="#9becbd"/>
      <line x1={x(index)} x2={x(index)} y1="20" y2="178" stroke="#a1edce" strokeOpacity=".35"/><circle cx={x(index)} cy={y(index)} r="4" fill="#a1edce" stroke="#08150e" strokeWidth="2"/>
    </svg>
    <label className="chart-cursor">Inspect observed bar <input aria-label={`Inspect ${ticker} historical bar`} aria-valuetext={`${date(row.source_timestamp!)} UTC, ${price(row.close!)}`} type="range" min="0" max={rows.length-1} value={index} onChange={e=>setSelected(Number(e.target.value))}/></label>
    <figcaption><span><i className="history-legend"/>Underlying equity close · USD · 5m</span><span>Alpaca / SIP · historical, not live</span></figcaption>
    <p className="chart-separation">Separate from the modeled token economics above. Verified token effective/share history unavailable: historical prices with as-of ratios are not established.</p>
    <details><summary>Coverage & source</summary><p>{rows.length} observed bars · {days.length} regular sessions · {gaps} genuine missing-data gaps. {date(rows[0].source_timestamp!)} — {date(rows.at(-1)!.source_timestamp!)} UTC.</p><p>Captured October 5–9 regular sessions: 09:30–16:00 America/New_York (13:30–20:00 UTC). Horizontal slots compress normal overnight closures only. Missing intraday bars, incomplete boundaries and missing whole dates remain breaks. Lines connect supplied closes, without interpolated observations.</p><p>1D selects the last stored session; 1W selects the captured week. Movement compares first and last observed closes, not an official prior-session close. Inspection changes the highlighted bar, not the period return.</p><p>Captured {data.captured_at?new Date(data.captured_at).toUTCString():'time not recorded'}. Raw unadjusted USD prices; SIP feed. No independently verified historical token series is available here.</p><ul>{data.limitations?.map(s=><li key={s}>{s}</li>)}</ul><p>This display capture does not price the scenario portfolio or replace its modeled equity reference.</p></details>
  </figure>
}
