import { useState } from 'react'

// Bundled unmodified assets from official brand websites. No remote render-time requests.
const companies:Record<string,{name:string;logo?:string}>={
  NVDA:{name:'Nvidia',logo:'/brands/nvda.ico'},AAPL:{name:'Apple',logo:'/brands/aapl.ico'},
  MSFT:{name:'Microsoft'},GOOGL:{name:'Alphabet',logo:'/brands/googl.ico'},GOOG:{name:'Alphabet',logo:'/brands/googl.ico'},
  TSLA:{name:'Tesla'},AMZN:{name:'Amazon'},META:{name:'Meta'},
}
export const holdingColor=(ticker:string,issuer:string)=>ticker==='AAPL'?'#66c6dd':issuer.toLowerCase().includes('meridian')?'#d4c18b':'#86e8b8'
export function AssetLogo({ticker}:{ticker:string}) {
  const [failed,setFailed]=useState<string|null>(null),asset=companies[ticker]
  return <span className="asset-logo" aria-label={`${asset?.name??ticker} identity`}>
    {asset?.logo&&failed!==ticker?<img src={asset.logo} alt="" width="24" height="24" loading="lazy" onError={()=>setFailed(ticker)}/>:<span>{ticker.slice(0,2)}</span>}
  </span>
}
export function IssuerLogo({issuer}:{issuer:string}) {
  const [failed,setFailed]=useState(false),ondo=/^ondo(?: finance)?$/i.test(issuer)
  return <span className="issuer-logo" aria-label={`${issuer} issuer identity`} title={issuer}>
    {ondo&&!failed?<img src="/brands/ondo.ico" alt="" width="18" height="18" onError={()=>setFailed(true)}/>:issuer.split(/\s+/).filter(s=>s.toLowerCase()!=='model').map(s=>s[0]).slice(0,2).join('')}
  </span>
}
export function AssetIdentity({ticker,issuer,detail}:{ticker:string;issuer?:string;detail?:string}) {
  return <span className="asset-identity"><AssetLogo key={ticker} ticker={ticker}/><span><strong>{ticker}</strong>{(issuer||detail)&&<small className="cell-detail">{issuer&&<IssuerLogo key={issuer} issuer={issuer}/>} {detail??issuer}</small>}</span></span>
}
