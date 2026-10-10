import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it, vi } from 'vitest'
import { RouteComparison } from '../components/RouteComparison'
import { AskFlow } from '../components/AskFlow'
import { DemoOpportunityFlow } from '../components/DemoOpportunityFlow'
import { parseRoute } from '../services/routing'
import { parseProposal } from '../services/exposure'
import { parseDemoResult } from '../services/demoSandbox'
import { parseOpportunity, parseRisk } from '../services/demoOpportunity'
import { parseQuote } from '../services/demoPreparation'
import f from './routingFixtures.json'

const route=()=>parseRoute(f.proposal.route_decision,'DEMO','NVDA','50')
afterEach(()=>{vi.unstubAllGlobals();vi.useRealTimers()})

it('displays actual two-candidate normalized ranking, selected identity and unknown costs',()=>{
  render(<RouteComparison route={route()} />)
  expect(screen.getByRole('heading',{name:'Route Decision: ROUTE_SELECTED'})).toBeInTheDocument()
  expect(screen.getByText('SELECTED')).toBeInTheDocument()
  expect(screen.getAllByText('All-in cost unavailable')).toHaveLength(2)
  expect(screen.getByText(/Ranking: TOKEN_PRICE_ONLY/)).toBeInTheDocument()
  const table=screen.getByRole('table')
  for(const heading of ['Issuer / Token','Liquidity / USD','Estimated fees / gas / USD','Estimated slippage / bps','Trust','Tradability','Decision']) expect(within(table).getByRole('columnheader',{name:heading})).toBeInTheDocument()
  expect(within(table).getByText(/test-second-issuer \/ TEST_NVDA_B/)).toBeInTheDocument()
})

it('shows explicit all-in estimated costs and chooses the cheaper total rather than cheaper token',()=>{
  const known=parseRoute(f.known_cost_comparison,'DEMO','NVDA','50')
  expect(known.issuer).toBe('test-second-issuer')
  render(<RouteComparison route={known} />)
  expect(screen.getByText(/Ranking: ALL_IN_ESTIMATE/)).toBeInTheDocument()
  expect(screen.getByText('All-in estimate: 51.000000000000000000')).toBeInTheDocument()
  expect(screen.getByText('All-in estimate: 50.500000000000000000')).toBeInTheDocument()
})

it('integrates the shared route contract into the existing Ask form without extra requests',async()=>{
  const fetch=vi.fn(async(_url:string,_init:RequestInit)=>new Response(JSON.stringify(f.proposal),{status:200}))
  vi.stubGlobal('fetch',fetch);render(<AskFlow mode="DEMO" />)
  await userEvent.click(screen.getByRole('button',{name:'Create exposure proposal'}))
  expect(await screen.findByRole('heading',{name:'Route Decision: ROUTE_SELECTED'})).toBeInTheDocument()
  expect(fetch).toHaveBeenCalledTimes(1)
  expect(JSON.parse(fetch.mock.calls[0][1].body as string)).toEqual({text:'I have $50 of Nvidia'})
  expect(parseProposal(f.proposal,'DEMO').route_decision?.issuer).toBe('test-second-issuer')
})

it.each(['steady','thin-move','supported-move'] as const)('preserves Trust/Opportunity/Risk/Quote contracts with a shared route: %s',scenario=>{
  const frame=f[scenario],trust=parseDemoResult(frame.trust,scenario)
  const opp=parseOpportunity(frame.opportunity,trust),risk=parseRisk(frame.risk,opp)
  const quote=parseQuote(frame.quote,trust,opp,risk)
  expect(opp.route_decision?.status).toBe(scenario==='supported-move'?'ROUTE_SELECTED':'NO_ROUTE')
  expect(quote.status).toBe(scenario==='supported-move'?'QUOTED':'BLOCKED')
  if(scenario!=='supported-move') {
    render(<RouteComparison route={opp.route_decision!} />)
    expect(screen.getByRole('heading',{name:'Route Decision: NO_ROUTE'})).toBeInTheDocument()
    expect(screen.getByText('REJECTED')).toBeInTheDocument()
    expect(screen.queryByText('SELECTED')).not.toBeInTheDocument()
  }
})

it('displays a routed Information result and retains manual downstream checks',async()=>{
  const frame=f['supported-move'],trust=parseDemoResult(frame.trust,'supported-move')
  const fetch=vi.fn(async(url:string)=>new Response(JSON.stringify(url.endsWith('/risk')?frame.risk:frame.opportunity),{status:200}))
  vi.stubGlobal('fetch',fetch);render(<DemoOpportunityFlow trust={trust} />)
  expect(fetch).not.toHaveBeenCalled()
  await userEvent.click(screen.getByRole('button',{name:'Analyze Opportunity'}))
  expect(await screen.findByRole('heading',{name:'Route Decision: ROUTE_SELECTED'})).toBeInTheDocument()
  await userEvent.click(screen.getByRole('button',{name:'Analyze Risk'}))
  expect(await screen.findByRole('heading',{name:'Risk: PASS'})).toBeInTheDocument()
  expect(screen.getByRole('button',{name:'Generate Illustrative Quote'})).toBeInTheDocument()
  expect(fetch).toHaveBeenCalledTimes(2)
})

it('removes current selection labels after expiry while retaining historical comparison',()=>{
  render(<RouteComparison route={route()} expired />)
  expect(screen.getByRole('heading',{name:'Route Decision: EXPIRED'})).toBeInTheDocument()
  expect(screen.queryByText('SELECTED')).not.toBeInTheDocument()
  expect(screen.getAllByText('Historical only')).toHaveLength(2)
})

it.each([
  ['live execution', (v:typeof f.proposal.route_decision)=>{v.execution_ready=true}],
  ['broadcast', (v:typeof f.proposal.route_decision)=>{v.transaction_broadcast=true}],
  ['mode mismatch', (v:typeof f.proposal.route_decision)=>{v.data_mode='LIVE'}],
  ['selected identity', (v:typeof f.proposal.route_decision)=>{v.selected_representation!.contract='demo:wrong'}],
  ['rank mismatch', (v:typeof f.proposal.route_decision)=>{v.selected_candidate!.rank=2}],
  ['unknown cost as known', (v:typeof f.proposal.route_decision)=>{v.ranking_basis='ALL_IN_ESTIMATE'}],
  ['float financial value', (v:typeof f.proposal.route_decision)=>{v.candidates[0].inputs.token_to_share_ratio=2 as unknown as string}],
  ['invalid price', (v:typeof f.proposal.route_decision)=>{v.candidates[0].effective_cost_per_share_usd='NaN'}],
  ['untradable selection', (v:typeof f.proposal.route_decision)=>{v.candidates[0].tradability='NOT_TRADABLE'}],
  ['unresolved selected', (v:typeof f.proposal.route_decision)=>{v.status='NO_ROUTE'}],
])('rejects unsafe/malformed routes: %s',(_name,mutate)=>{
  const v=structuredClone(f.proposal.route_decision);mutate(v)
  expect(()=>parseRoute(v,'DEMO','NVDA','50')).toThrow()
})

it('rejects detached proposal and Opportunity selections instead of treating them as routing authority',()=>{
  const v=structuredClone(f.proposal);v.selected!.contract='demo:wrong'
  expect(()=>parseProposal(v,'DEMO')).toThrow()
  const frame=structuredClone(f['supported-move']);frame.opportunity.route_decision.policy.require_trust=false
  expect(()=>parseOpportunity(frame.opportunity,parseDemoResult(frame.trust,'supported-move'))).toThrow()
})
