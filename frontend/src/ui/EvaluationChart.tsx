import { useState } from 'react'
import type { PresentationWorkspace_EvaluationRecord as Evaluation } from '../types/backend.generated'
const pct=(v:string)=>`${(Number(v)*100).toFixed(2)}%`
/** Actual supplied fixture evaluations, not a manufactured performance/accuracy curve. */
export function EvaluationChart({records}:{records:Evaluation[]}) {
  const [selected,setSelected]=useState<string|null>(null)
  const sorted=[...records].sort((a,b)=>a.at.localeCompare(b.at)||a.id.localeCompare(b.id))
  if(!sorted.length)return <figure className="evaluation-chart"><p>No evaluation observations for this filter.</p></figure>
  const values=sorted.flatMap(r=>[Number(r.initial_deviation),Number(r.final_deviation)]),low=Math.min(...values,0)-.001,high=Math.max(...values,0)+.001
  const from=Date.parse(sorted[0].at),to=Date.parse(sorted.at(-1)!.at),x=(r:Evaluation)=>65+(Date.parse(r.at)-from)/Math.max(to-from,1)*500,y=(v:string)=>20+(high-Number(v))/(high-low)*150
  const active=sorted.find(r=>r.id===selected)
  return <figure className="evaluation-chart" aria-label="Scenario evaluation outcomes"><div className="history-heading"><span className="eyebrow">SCENARIO EVALUATION OUTCOMES</span><span>{sorted.length} supplied episodes · not validated performance</span></div><svg viewBox="0 0 610 208" role="img" aria-label="Recorded initial and outcome deviations, synthetic scenario evaluations">
    {[0,.5,1].map(p=><g key={p}><line x1="65" x2="565" y1={20+p*150} y2={20+p*150} stroke="#294035"/><text x="54" y={24+p*150} textAnchor="end">{pct(String(high-p*(high-low)))}</text></g>)}
    {sorted.map(r=><g key={r.id} opacity={active&&active.id!==r.id? .3:1} onPointerEnter={()=>setSelected(r.id)} onPointerLeave={()=>setSelected(null)}><circle cx={x(r)} cy={y(r.initial_deviation)} r="4.5" fill="none" stroke="#66c6dd" strokeWidth="1.5"/><circle cx={x(r)} cy={y(r.final_deviation)} r="3" fill="#9becbd"/><title>{r.ticker} {r.at}: initial {pct(r.initial_deviation)}, outcome {pct(r.final_deviation)}</title></g>)}
    <text x="65" y="195">{sorted[0].at.slice(0,10)}</text><text x="565" y="195" textAnchor="end">{sorted.at(-1)!.at.slice(0,10)}</text>
  </svg><div className="comparison-legend"><span><i style={{background:'#66c6dd'}}/>Initial deviation</span><span><i style={{background:'#9becbd'}}/>Outcome deviation</span></div><label className="chart-cursor">Inspect episode <input type="range" min="0" max={sorted.length-1} value={Math.max(0,sorted.findIndex(r=>r.id===selected))} aria-label="Inspect scenario evaluation" aria-valuetext={`${(active??sorted[0]).ticker}, ${(active??sorted[0]).at}, initial ${pct((active??sorted[0]).initial_deviation)}, outcome ${pct((active??sorted[0]).final_deviation)}`} onChange={e=>setSelected(sorted[Number(e.target.value)].id)}/></label><figcaption>{active?`${active.ticker} · ${active.at} · ${pct(active.initial_deviation)} → ${pct(active.final_deviation)} · ${active.correct?'Matched':'Diverged'}`:'Dots show provided episode observations. No interpolated performance curve, realized return or production backtest is implied.'}</figcaption></figure>
}
