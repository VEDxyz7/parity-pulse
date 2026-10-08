import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { apiRequest, ApiError } from '../services/api'
import { validateWire } from '../services/contracts'
import { getWorkspace } from '../services/workspace'
import { OpportunityView } from '../components/OpportunityView'
import { PortfolioView, SystemView, AuditEvents, useWorkspace } from '../components/WorkspaceViews'
import { ProposalReview } from '../components/ProposalReview'
import fixtures from './workspaceFixtures.json'
import demo from './demoUiFixtures.json'
import { parseProposal } from '../services/exposure'
import routeFixtures from './routingFixtures.json'
const json = (v: unknown, status=200) => new Response(JSON.stringify(v),{status,headers:{'Content-Type':'application/json'}})
function mount(component: React.ReactNode) { const client = new QueryClient({defaultOptions:{queries:{retry:false,gcTime:0}}});return render(<QueryClientProvider client={client}>{component}</QueryClientProvider>) }
afterEach(()=>{vi.unstubAllGlobals();vi.useRealTimers()})
describe('Phase 15 bounded transport and generated contracts',()=>{
  it('retains precision and request correlation without automatic retries',async()=>{
    const fetch=vi.fn(async()=>json({money:'0.123456789123456789'}));vi.stubGlobal('fetch',fetch)
    const value=await apiRequest('/api/example',v=>v,{signal:new AbortController().signal,body:{amount:'0.123456789123456789'},correlationId:'fixed-correlation'})
    expect(value).toEqual({money:'0.123456789123456789'});expect(fetch).toHaveBeenCalledTimes(1)
    const o=fetch.mock.calls[0] as unknown as [string,RequestInit];expect(o[1].headers).toMatchObject({'X-Correlation-ID':'fixed-correlation'});expect(JSON.parse(o[1].body! as string).amount).toBe('0.123456789123456789')
  })
  it.each([401,403,404,408,409,429,500,502,503,504])('preserves HTTP %i without exposing raw provider errors or retrying',async status=>{
    const fetch=vi.fn(async()=>json({error:'Bearer secret-key private prompt'},status));vi.stubGlobal('fetch',fetch)
    await expect(apiRequest('/api/example',v=>v,{signal:new AbortController().signal})).rejects.toMatchObject({code:'HTTP_ERROR',status});expect(fetch).toHaveBeenCalledTimes(1)
  })
  it('cancels a timed-out request and leaves a proposal unretried',async()=>{
    vi.useFakeTimers();const fetch=vi.fn((_u:string,o:RequestInit)=>new Promise<Response>((_,reject)=>o.signal!.addEventListener('abort',()=>reject(new DOMException('Aborted','AbortError')))));vi.stubGlobal('fetch',fetch)
    const pending=expect(apiRequest('/api/example',v=>v,{signal:new AbortController().signal,body:{idempotency_key:'retained'}})).rejects.toMatchObject({code:'REQUEST_TIMEOUT'})
    await vi.advanceTimersByTimeAsync(8001);await pending;expect(fetch).toHaveBeenCalledTimes(1)
  })
  it('rejects non-JSON, malformed contracts and arbitrary external URL requests',async()=>{
    vi.stubGlobal('fetch',vi.fn(async()=>new Response('<script>secret</script>')))
    await expect(apiRequest('/api/example',v=>v,{signal:new AbortController().signal})).rejects.toMatchObject({code:'INVALID_RESPONSE'})
    await expect(apiRequest('https://evil.test',v=>v,{signal:new AbortController().signal})).rejects.toBeInstanceOf(ApiError)
  })
  it('validates actual backend wire samples without coercion',()=>{
    expect(validateWire('WorkspaceState',fixtures.workspace_ready)).toEqual(fixtures.workspace_ready)
    for(const sample of Object.values(fixtures.scans))expect(validateWire('OpportunityScan',sample)).toEqual(sample)
    expect(validateWire('AuditPage',fixtures.audit)).toEqual(fixtures.audit)
  })
  it.each(['precision','enum','nullability','timestamp','gate','extra'])('refuses %s contract mismatches',kind=>{
    const body=structuredClone(fixtures.workspace_ready) as any
    if(kind==='precision')body.portfolio.latest_decision.total_value_usd=100
    if(kind==='enum')body.positions[0].state='FILLED'
    if(kind==='nullability')body.positions[0].position_id=null
    if(kind==='timestamp')body.generated_at='yesterday'
    if(kind==='gate')body.production_gates.TRUST_GATE='PASS'
    if(kind==='extra')body.signing_secret='secret'
    expect(()=>validateWire('WorkspaceState',body)).toThrow('could not be verified')
  })
  it('refuses cross-mode embedded synthetic records even when root mode is changed',async()=>{
    vi.stubGlobal('fetch',vi.fn(async()=>json({...fixtures.workspace_ready,data_mode:'LIVE_READ_ONLY'})))
    await expect(getWorkspace('LIVE_READ_ONLY',new AbortController().signal)).rejects.toMatchObject({code:'INVALID_RESPONSE'})
  })
})
describe('Phase 15 backend-authoritative pages',()=>{
  it('shows loading, empty portfolio and unavailable wallet without fabricated holdings',async()=>{
    vi.stubGlobal('fetch',vi.fn(async()=>json(fixtures.workspace_empty)));mount(<PortfolioView mode="DEMO"/>)
    expect(screen.getByRole('status')).toHaveTextContent('Loading')
    await screen.findByText('No persisted positions in this data mode.')
    expect(screen.getByText(/No portfolio mandate is configured/)).toBeInTheDocument()
  })
  it('shows backend drift, original capture, risk and unresolved ownership',async()=>{
    vi.stubGlobal('fetch',vi.fn(async()=>json(fixtures.workspace_unresolved)));mount(<PortfolioView mode="DEMO" autopilot/>)
    await screen.findByText(/UNRESOLVED — no ownership confirmed/)
    expect(screen.getByText(/historical planning snapshot/)).toBeInTheDocument()
    expect(screen.getByRole('button',{name:'Save reviewed mandate'})).toBeInTheDocument()
    expect(screen.queryByRole('button',{name:/execute|sign|approve/i})).not.toBeInTheDocument()
  })
  it('renders blocked wallet/gates and recovers from API failure without zeros',async()=>{
    const fetch=vi.fn().mockResolvedValueOnce(json({},503)).mockResolvedValueOnce(json(fixtures.workspace_empty));vi.stubGlobal('fetch',fetch);mount(<SystemView mode="DEMO"/>)
    await screen.findByRole('alert');expect(screen.queryByText('WALLET_UNAVAILABLE')).not.toBeInTheDocument()
    await userEvent.click(screen.getByRole('button',{name:'Refresh workspace state'}));await screen.findByText(/WALLET_UNAVAILABLE/)
    expect(screen.getByText('TRUST_GATE')).toBeInTheDocument();expect(screen.queryByRole('checkbox')).not.toBeInTheDocument()
  })
  it.each(['steady','thin-move','supported-move'] as const)('displays the actual %s scan and selected candidate detail',async scenario=>{
    const fetch=vi.fn(async()=>json(fixtures.scans[scenario]));vi.stubGlobal('fetch',fetch);mount(<OpportunityView mode="DEMO" sandbox/>)
    await userEvent.type(screen.getByLabelText('Investment amount / USD notional'),'100');await userEvent.type(screen.getByLabelText('Risk budget / USD'),'10')
    await userEvent.click(screen.getByRole('button',{name:'Scan opportunities'}))
    await screen.findByRole('heading',{name:fixtures.scans[scenario].final_action})
    await userEvent.click(screen.getAllByRole('button',{name:/Inspect .* evidence/})[0]);expect(screen.getByRole('region',{name:'Opportunity detail'})).toBeInTheDocument()
    expect(screen.getByText(/Raw agent responses and hidden reasoning are not displayed/)).toBeInTheDocument()
    expect(fetch).toHaveBeenCalledTimes(1)
  })
  it('retains a scan identity on uncertain retry and prevents double click submission',async()=>{
    const fetch=vi.fn().mockRejectedValueOnce(new Error('private')).mockResolvedValueOnce(json(fixtures.scans.steady));vi.stubGlobal('fetch',fetch);mount(<OpportunityView mode="DEMO" sandbox={false}/>)
    await userEvent.type(screen.getByLabelText('Investment amount / USD notional'),'100');await userEvent.type(screen.getByLabelText('Risk budget / USD'),'10')
    await userEvent.click(screen.getByRole('button',{name:'Scan opportunities'}));await screen.findByRole('alert')
    await userEvent.dblClick(screen.getByRole('button',{name:'Scan opportunities'}));await screen.findByRole('heading',{name:fixtures.scans.steady.final_action})
    const bodies=fetch.mock.calls.map(([,o])=>JSON.parse(o.body));expect(bodies).toHaveLength(2);expect(bodies[0]).toEqual(bodies[1]);expect(bodies[0].demo_scenario).toBeUndefined()
  })
  it('displays untrusted ticker/issuer text as text, never executable HTML',async()=>{
    const body=structuredClone(fixtures.workspace_empty);(body.wallet.reasons as string[]).push('<img src=x onerror="window.pwned=true">')
    vi.stubGlobal('fetch',vi.fn(async()=>json(body)));const {container}=mount(<SystemView mode="DEMO"/>)
    await screen.findByText(/<img src=x/);expect(container.querySelector('img')).toBeNull();expect((window as any).pwned).toBeUndefined()
  })
  it('deduplicates shared polling and aborts when all observers unmount',async()=>{
    vi.useFakeTimers();const fetch=vi.fn((_url:string,o:RequestInit)=>new Promise<Response>((_,reject)=>o.signal!.addEventListener('abort',()=>reject(new DOMException('Aborted','AbortError')))));vi.stubGlobal('fetch',fetch)
    function Observer(){useWorkspace('DEMO');return null}
    const view=mount(<><Observer/><Observer/></>);expect(fetch).toHaveBeenCalledTimes(1);view.unmount();expect(fetch.mock.calls[0][1].signal!.aborted).toBe(true)
    await vi.advanceTimersByTimeAsync(120000);expect(fetch).toHaveBeenCalledTimes(1)
  })
  it('lists audit events and decision links using bounded backend pagination',async()=>{
    vi.stubGlobal('fetch',vi.fn(async()=>json(fixtures.audit)));mount(<AuditEvents mode="DEMO"/>);await screen.findByText(/Recorded backend evidence/)
    expect(screen.getByRole('heading',{name:'Audit events'})).toBeInTheDocument()
    expect(screen.getByRole('button',{name:'Previous events'})).toBeDisabled()
  })
})

describe('Phase 15 refresh, reviewed mandates and safe proposal lifecycle',()=>{
  it('keeps reviewed inputs and expected version through refresh; save is explicit and non-executable',async()=>{
    const ready=fixtures.workspace_ready
    const fetch=vi.fn(async(url:string)=>json(url==='/api/autopilot'?ready.portfolio.config:ready));vi.stubGlobal('fetch',fetch)
    mount(<PortfolioView mode="DEMO" autopilot/>);await screen.findByText(/Version /)
    for(const [label,v] of [['Stock ticker','NVDA'],['Stock target fraction','0.5'],['Cash target fraction','0.5'],['Drift band fraction','0.05'],['Rebalance cap USD','50'],['Risk budget USD','2'],['Stock exposure cap USD','100']])await userEvent.type(screen.getByLabelText(label),v)
    await userEvent.click(screen.getByRole('button',{name:'Save reviewed mandate'}))
    await screen.findByText(/Mandate saved by backend/)
    await waitFor(()=>expect(screen.getByRole('button',{name:'Refresh workspace state'})).not.toBeDisabled())
    expect(screen.getByLabelText('Stock ticker')).toHaveValue('NVDA')
    const write=fetch.mock.calls.filter(([url])=>url==='/api/autopilot') as unknown as [string,RequestInit][]
    expect(write).toHaveLength(1);expect(JSON.parse(write[0][1].body as string)).toMatchObject({expected_version:ready.portfolio.config!.version,risk_budget_usd:'2',max_rebalance_notional_usd:'50'})
    await userEvent.click(screen.getByRole('button',{name:'Refresh workspace state'}));await waitFor(()=>expect(screen.getByRole('button',{name:'Refresh workspace state'})).not.toBeDisabled())
    expect(fetch.mock.calls.filter(([url])=>url==='/api/autopilot')).toHaveLength(1)
    expect(screen.getByLabelText('Stock ticker')).toHaveValue('NVDA')
  })
  it('retains the planning key after a network failure and across successful read refresh',async()=>{
    let failures=1
    const fetch=vi.fn(async(url:string)=>{if(url==='/api/portfolio/plans'){if(failures-- >0)throw Error('unsafe');return json(fixtures.rebalance_plan)}return json(fixtures.workspace_ready)});vi.stubGlobal('fetch',fetch)
    mount(<PortfolioView mode="DEMO" autopilot/>);await screen.findByText(/Version /)
    await userEvent.click(screen.getByRole('button',{name:'Evaluate drift proposal'}));await screen.findByText(/Retain the same planning key/)
    await userEvent.click(screen.getByRole('button',{name:'Evaluate drift proposal'}));await screen.findByText(/Backend rebalance decision/)
    await waitFor(()=>expect(screen.getByRole('button',{name:'Evaluate drift proposal'})).not.toBeDisabled())
    await userEvent.click(screen.getByRole('button',{name:'Evaluate drift proposal'}));await screen.findByText(/Backend rebalance decision/)
    const writes=fetch.mock.calls.filter(([url])=>url==='/api/portfolio/plans') as unknown as [string,RequestInit][]
    expect(writes).toHaveLength(3);expect(new Set(writes.map(([,o])=>JSON.parse(o.body as string).idempotency_key)).size).toBe(1)
  })
  it('cancels an in-flight mandate when the page unmounts',async()=>{
    const fetch=vi.fn(async(url:string,o:RequestInit)=>url==='/api/portfolio/plans'?new Promise<Response>((_,reject)=>o.signal!.addEventListener('abort',()=>reject(new DOMException('Aborted','AbortError')))):json(fixtures.workspace_ready));vi.stubGlobal('fetch',fetch)
    const view=mount(<PortfolioView mode="DEMO" autopilot/>);await screen.findByText(/Version /)
    await userEvent.click(screen.getByRole('button',{name:'Evaluate drift proposal'}));view.unmount()
    const write=fetch.mock.calls.find(([url])=>url==='/api/portfolio/plans')!;expect(write[1].signal!.aborted).toBe(true)
  })
  it('retrieves a persisted scan by GET without repeating the scan action',async()=>{
    const scan=fixtures.scans.steady;const fetch=vi.fn(async()=>json(scan));vi.stubGlobal('fetch',fetch)
    mount(<OpportunityView mode="DEMO" sandbox scanId={scan.run_id}/>);await screen.findByRole('heading',{name:scan.final_action})
    expect(fetch).toHaveBeenCalledTimes(1);expect((fetch.mock.calls[0] as unknown as [string,RequestInit])[0]).toBe('/api/opportunities/'+scan.run_id)
    expect((fetch.mock.calls[0] as unknown as [string,RequestInit])[1].method).toBe('GET')
    expect(screen.getByText(/Historical scan snapshot/)).toBeInTheDocument()
  })
  it('reviews canonical Trust without substituting approval, execution or an updated quote',async()=>{
    const fetch=vi.fn(async()=>json({...demo.canonical_trust,evaluated_at:new Date().toISOString()}));vi.stubGlobal('fetch',fetch)
    const proposal=parseProposal(routeFixtures.proposal,'DEMO');const view=render(<ProposalReview proposal={proposal} mode="DEMO" expired={false}/>)
    expect(fetch).not.toHaveBeenCalled();await userEvent.dblClick(screen.getByRole('button',{name:'Review proposal'}))
    await screen.findByText(/Independent assessment as of/)
    expect(screen.getByText(/Execution: BLOCKED/)).toBeInTheDocument()
    expect(screen.queryByRole('button',{name:/execute|sign|approve/i})).toBeNull()
    expect((fetch.mock.calls as unknown as [string,RequestInit][]).every(([url])=>url==='/api/assets/NVDA/trust')).toBe(true)
    view.rerender(<ProposalReview proposal={proposal} mode="DEMO" expired/>);expect(screen.getByRole('button',{name:'Review proposal'})).toBeDisabled()
    expect(screen.getByText(/EXPIRED/)).toBeInTheDocument()
  })
  it('periodic read refresh never submits an action and stops after unmount',async()=>{
    vi.useFakeTimers();const fetch=vi.fn(async()=>json(fixtures.workspace_empty));vi.stubGlobal('fetch',fetch)
    function Observer(){useWorkspace('DEMO');return null}
    const view=mount(<Observer/>);await act(async()=>{await vi.advanceTimersByTimeAsync(30100)})
    expect(fetch.mock.calls.length).toBeGreaterThan(1)
    expect(fetch.mock.calls.every((call)=>(call as unknown as [string,RequestInit])[1].method==='GET')).toBe(true)
    const before=fetch.mock.calls.length;view.unmount();await act(async()=>{await vi.advanceTimersByTimeAsync(90000)});expect(fetch).toHaveBeenCalledTimes(before)
  })
})

 it('expires reviewed Trust evidence after the unchanged 120-second display window',async()=>{
   vi.useFakeTimers();vi.setSystemTime(new Date(demo.canonical_trust.evaluated_at))
   vi.stubGlobal('fetch',vi.fn(async()=>json(demo.canonical_trust)))
   render(<ProposalReview proposal={parseProposal(routeFixtures.proposal,'DEMO')} mode="DEMO" expired={false}/>)
   await act(async()=>{fireEvent.click(screen.getByRole('button',{name:'Review proposal'}))})
   expect(screen.getByText(/Independent assessment as of/)).toBeInTheDocument()
   await act(async()=>{await vi.advanceTimersByTimeAsync(120001)})
   expect(screen.getByRole('alert')).toHaveTextContent('STALE');expect(screen.queryByText(/Independent assessment as of/)).toBeNull()
 })
 it('keeps approval and execution blocked when canonical Trust fails',async()=>{
   vi.stubGlobal('fetch',vi.fn(async()=>json({},403)))
   render(<ProposalReview proposal={parseProposal(routeFixtures.proposal,'DEMO')} mode="DEMO" expired={false}/>)
   await userEvent.click(screen.getByRole('button',{name:'Review proposal'}));await screen.findByRole('alert')
   expect(screen.getByText(/Execution: BLOCKED/)).toBeInTheDocument();expect(screen.queryByText(/Independent assessment as of/)).toBeNull()
 })
