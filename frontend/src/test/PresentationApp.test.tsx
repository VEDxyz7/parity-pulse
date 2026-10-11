import { render, screen, waitFor, within, fireEvent } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { beforeEach, expect, it, vi } from 'vitest'
import { PresentationApp } from '../PresentationApp'
import fixtures from './presentationFixtures.json'
import { presentation } from '../services/presentation'

let requests: {path: string; body?: Record<string, unknown>}[]
beforeEach(()=>{
  location.hash='#overview'; requests=[]
  vi.stubGlobal('scrollTo',vi.fn())
  vi.stubGlobal('fetch',vi.fn(async (url: string, options: RequestInit)=>{
    const body=options.body?JSON.parse(options.body as string):undefined
    requests.push({path:url,body})
    const result=url.startsWith('/api/display-history/')?{ticker:url.split('/').pop(),status:'UNAVAILABLE',observations:[]}:url.endsWith('/workspace')?fixtures.workspace:url.endsWith('/scan')?fixtures.scan:url.endsWith('/exposure')?fixtures.route:fixtures.studies[(body?.preset??'news') as keyof typeof fixtures.studies]
    return new Response(JSON.stringify(result),{status:200,headers:{'Content-Type':'application/json'}})
  }))
})
function mount(){return render(<QueryClientProvider client={new QueryClient({defaultOptions:{queries:{retry:false},mutations:{retry:false}}})}><PresentationApp/></QueryClientProvider>)}
async function nav(name:string){fireEvent.click(screen.getByRole('link',{name}));await waitFor(()=>expect(screen.getByRole('heading',{name,level:1})).toBeInTheDocument())}
it('populates the normal workspace without operational diagnostics or raw development labels',async()=>{
  mount();await screen.findByRole('heading',{name:'Market intelligence'})
  expect(screen.getByText(/Scenario workspace/)).toBeInTheDocument()
  expect(screen.queryByText('System Health')).not.toBeInTheDocument()
  expect(screen.queryByText('Capability Gates')).not.toBeInTheDocument()
  expect(document.body.textContent).not.toMatch(/DEMO|Illustrative data|Unavailable|Disabled on this backend|No real transaction was broadcast/)
  await nav('Markets'); fireEvent.change(screen.getByRole('searchbox'),{target:{value:'Apple'}})
  const table=screen.getAllByRole('table')[0]
  expect(within(table).getAllByText('AAPL').length).toBe(2)
  expect(within(table).queryByText('NVDA')).not.toBeInTheDocument()
  fireEvent.change(screen.getByRole('searchbox'),{target:{value:'no-matching-stock'}})
  expect(screen.getByText(/No matching assets/)).toBeInTheDocument()
  expect(requests.every(r=>r.path.startsWith('/api/presentation/')||r.path.startsWith('/api/display-history/'))).toBe(true)
})
it('reassesses a selected representation and generates a shared-router comparison',async()=>{
  location.hash='#trust';mount();await screen.findByRole('button',{name:'Reassess signal'})
  fireEvent.click(screen.getByRole('button',{name:'Reassess signal'}))
  await waitFor(()=>expect(requests.some(r=>r.path.endsWith('/research'))).toBe(true))
  fireEvent.click(screen.getByRole('button',{name:'Compare routes'}))
  await screen.findByText('Exposure proposal ready')
  expect(screen.getByText('Selected · best economics')).toBeInTheDocument()
  expect(requests.find(r=>r.path.endsWith('/exposure'))?.body?.budget).toBe('60')
})
it('scans with the entered mandate, ranks and inspects a prepared proposal',async()=>{
  location.hash='#opportunities';mount();await screen.findByRole('button',{name:'Run scan'})
  fireEvent.change(screen.getByLabelText('Investment amount ($)'),{target:{value:'70'}})
  fireEvent.click(screen.getByRole('button',{name:'Run scan'}))
  await screen.findByText('Ranking policy')
  expect(requests.find(r=>r.path.endsWith('/scan'))?.body?.budget).toBe('70')
  fireEvent.click(screen.getAllByRole('button',{name:'Inspect proposal'})[0])
  expect(screen.getByText(/Prepared proposal/)).toBeInTheDocument()
  expect(screen.getByText(/local constraints passed/)).toBeInTheDocument()
  fireEvent.click(screen.getAllByRole('button',{name:'Inspect stand-down'})[0])
  expect(screen.getByText(/Wait for a stronger signal/)).toBeInTheDocument()
})
it('research presets call the backend, compare, reset and preserve baseline state',async()=>{
  location.hash='#research';mount();await screen.findByRole('button',{name:'Run study'})
  fireEvent.change(screen.getByLabelText('Preset'),{target:{value:'low-liquidity'}})
  fireEvent.click(screen.getByRole('button',{name:'Run study'}))
  await screen.findByText(/Thin liquidity weakens/)
  expect(requests.at(-1)?.body?.preset).toBe('low-liquidity')
  fireEvent.click(screen.getByRole('button',{name:'Pin for comparison'}))
  expect(screen.getAllByText(/Thin liquidity weakens/)).toHaveLength(2)
  fireEvent.change(screen.getByLabelText('Preset'),{target:{value:'normal'}})
  fireEvent.click(screen.getByRole('button',{name:'Run study'}))
  await screen.findByText(/Wait for a stronger signal/)
  fireEvent.change(screen.getByLabelText('Token price ($)'),{target:{value:'55'}})
  fireEvent.click(screen.getByRole('button',{name:'Run study'}))
  await waitFor(()=>expect(requests.at(-1)?.body?.token_price).toBe('55'))
  fireEvent.click(screen.getByRole('button',{name:'Reset baseline'}))
  expect(screen.getByLabelText('Token price ($)')).toHaveValue(null)
  expect(screen.getAllByText(/Persistent movement/)).toHaveLength(2)
})
it('portfolio and scorecard filters operate on the shared workspace records',async()=>{
  location.hash='#portfolio';mount();await screen.findByText('Portfolio exposure')
  fireEvent.change(screen.getByLabelText('Holdings filter'),{target:{value:'AAPL'}})
  expect(within(screen.getAllByRole('table')[0]).queryByText(/NVDA/)).not.toBeInTheDocument()
  await nav('Scorecard')
  fireEvent.change(screen.getByLabelText('Asset filter'),{target:{value:'NVDA'}})
  expect(screen.getAllByRole('button',{name:'Trace decision'})).toHaveLength(30)
  fireEvent.click(screen.getAllByRole('button',{name:'Trace decision'})[0])
  expect(screen.getByText(/not a real-market backtest/)).toBeInTheDocument()
  fireEvent.change(screen.getByLabelText('Outcome filter'),{target:{value:'incorrect'}})
  const count=fixtures.workspace.evaluations.filter(e=>e.ticker==='NVDA'&&!e.correct).length
  expect(screen.queryAllByRole('button',{name:'Trace decision'})).toHaveLength(count)
})
it('reports connection failures professionally and refreshes without changing source',async()=>{
  vi.mocked(fetch).mockRejectedValueOnce(new Error('offline'))
  mount();await screen.findByRole('alert')
  expect(document.body.textContent).not.toMatch(/NETWORK_UNAVAILABLE|gate|DEMO/)
  fireEvent.click(screen.getByRole('button',{name:'Refresh workspace'}))
  await screen.findByRole('heading',{name:'Market intelligence'})
})
it('validates response provenance and rejects production promotion or malformed data',async()=>{
  const broken=structuredClone(fixtures.workspace);broken.provenance.production_eligible=true as false
  vi.mocked(fetch).mockResolvedValueOnce(new Response(JSON.stringify(broken),{status:200}))
  await expect(presentation.workspace(new AbortController().signal)).rejects.toThrow('INVALID_RESPONSE')
})

it('refreshes once, reports unchanged scenario data and retains the selected page',async()=>{
  location.hash='#markets';mount();await screen.findByRole('button',{name:'Refresh workspace'})
  await screen.findByText('Representation terminal')
  const before=requests.filter(r=>r.path.endsWith('/workspace')).length
  fireEvent.click(screen.getByRole('button',{name:'Refresh workspace'}))
  fireEvent.click(screen.getByRole('button',{name:/Refresh/}))
  await screen.findByText(/Scenario inputs unchanged/)
  expect(requests.filter(r=>r.path.endsWith('/workspace'))).toHaveLength(before+1)
  expect(location.hash).toBe('#markets')
  expect(screen.getByText(/Provider prices were not refreshed/)).toBeInTheDocument()
})
it('searches token identity and qualifies liquidity without replacing backend values',async()=>{
  location.hash='#markets';mount();await screen.findByText('Representation terminal')
  expect(screen.getAllByText('Scenario USD assumption')).toHaveLength(4)
  fireEvent.change(screen.getByRole('searchbox'),{target:{value:fixtures.workspace.assets[0].token_symbol}})
  expect(within(screen.getAllByRole('table')[0]).getAllByRole('row')).toHaveLength(2)
  expect(screen.getByText('Scenario USD input · not measured depth')).toBeInTheDocument()
})

it('skip navigation focuses content without changing the active financial page',async()=>{
  location.hash='#portfolio';mount();await screen.findByText('Portfolio exposure')
  fireEvent.click(screen.getByRole('link',{name:'Skip to content'}))
  expect(location.hash).toBe('#portfolio')
  expect(document.activeElement?.id).toBe('product-main')
})
