import { useEffect, useRef, useState } from 'react'
import type { Proposal } from '../services/exposure'
import { fetchTrust, type TrustResult } from '../services/trust'
import { TrustEvidence } from './TrustEvidence'
export function ProposalReview({ proposal, mode, expired }: { proposal: Proposal; mode: 'DEMO'|'LIVE_READ_ONLY'; expired: boolean }) {
  const [open,setOpen]=useState(false),[trust,setTrust]=useState<TrustResult|null>(null),[error,setError]=useState(''),[busy,setBusy]=useState(false)
  const pending=useRef<AbortController|null>(null)
  useEffect(()=>()=>{pending.current?.abort();pending.current=null},[])
  useEffect(()=>{
    if(!trust)return
    const timer=setTimeout(()=>{setTrust(null);setError('STALE — assessment expired. Request fresh evidence; execution remains blocked.')},Math.max(0,Date.parse(trust.evaluated_at)+120_000-Date.now()))
    return ()=>clearTimeout(timer)
  },[trust])
  async function review(){
    if(busy||expired||!proposal.ticker)return
    setOpen(true);setBusy(true);setTrust(null);setError('')
    const controller=new AbortController();pending.current=controller
    try{const result=await fetchTrust(proposal.ticker,mode,controller.signal);if(pending.current===controller&&!controller.signal.aborted)setTrust(result)}
    catch{if(pending.current===controller)setError('Canonical Trust evidence unavailable. No approval or execution was substituted.')}
    finally{if(pending.current===controller)setBusy(false)}
  }
  return <section aria-label="Proposal safety review"><button className="refresh-button" disabled={busy||expired||!proposal.ticker} onClick={()=>void review()}>{busy?'Loading safety evidence…':'Review proposal'}</button>
    {open&&<><h3>Confirm Trade — proposal review only</h3><p>Review only · indicative proposal · live execution blocked</p><p>Quote: indicative estimate · Risk: not assessed for execution · Simulation: UNAVAILABLE · Approval: PUBLIC_APPROVAL_UNAVAILABLE</p><p>Execution: BLOCKED · No confirmed transaction or position results from this proposal. No real transaction was broadcast.</p><p>Original estimate {proposal.proposal_id} · Valid until {proposal.valid_until}. A new analytical Trust assessment does not change the stored proposal or approve a trade.</p>{busy&&<p role="status">Loading canonical Trust assessment…</p>}{expired&&<p role="status">EXPIRED — obtain fresh proposal and safety evidence.</p>}{error&&<p role="alert">{error}</p>}{trust&&<><p>Independent assessment as of {trust.evaluated_at}; it is not execution approval or a refreshed quote.</p><TrustEvidence result={trust}/></>}<p>Blocked steps cannot be approved in this public runtime. Signing and RFQ submission are unavailable.</p><a href="#portfolio" className="refresh-button">Inspect persisted positions</a><a href={`#audit/${proposal.proposal_id}`} className="refresh-button">Inspect proposal audit</a></>}
  </section>
}
