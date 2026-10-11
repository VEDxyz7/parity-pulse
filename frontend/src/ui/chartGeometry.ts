/** Geometry for the verified Oct 5–9 capture only; not a market calendar or price engine. */
export function sessionGeometry(timestamps: string[], values: number[], width: number) {
  const times=timestamps.map(Date.parse), start=times[0] ?? 0
  const startDay=Math.floor(start/86400000)
  // 78 five-minute slots in each captured 13:30–20:00 UTC regular session.
  // Missing whole dates retain their slots. Never infer a holiday or fill missing bars.
  const slots=times.map(t=>(Math.floor(t/86400000)-startDay)*78+(t%86400000-48600000)/300000)
  const begin=slots[0]??0, end=slots.at(-1)??begin
  const low=Math.min(...values), high=Math.max(...values), pad=Math.max((high-low)*.15,.05)
  const x=(i:number)=>58+(slots[i]-begin)/Math.max(end-begin,1)*(width-82)
  const y=(i:number)=>20+(high+pad-values[i])/(high-low+2*pad)*158
  const breaks=times.map((t,i)=>i===0 || !(t-times[i-1]===300000 || (
    Math.floor(t/86400000)-Math.floor(times[i-1]/86400000)===1 &&
    times[i-1]%86400000===71700000 && t%86400000===48600000)))
  const segments:number[][]=[]
  times.forEach((_,i)=>{if(breaks[i])segments.push([]);segments.at(-1)!.push(i)})
  const path=segments.map(indices=>indices.map((i,j)=>`${j?'L':'M'}${x(i).toFixed(2)},${y(i).toFixed(2)}`).join(' ')).join(' ')
  const area=segments.map(indices=>`${indices.map((i,j)=>`${j?'L':'M'}${x(i).toFixed(2)},${y(i).toFixed(2)}`).join(' ')} L${x(indices.at(-1)!).toFixed(2)},178 L${x(indices[0]).toFixed(2)},178 Z`).join(' ')
  return {x,y,path,area,low:low-pad,high:high+pad,gaps:Math.max(0,segments.length-1)}
}
