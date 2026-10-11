import { fireEvent, render, screen, within } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, expect, it, vi } from 'vitest'
import { sessionGeometry } from '../ui/chartGeometry'
import { HistoricalChart } from '../ui/HistoricalChart'
import { AssetIdentity, AssetLogo, IssuerLogo } from '../ui/AssetIdentity'
import { PortfolioDonut } from '../ui/PortfolioDonut'
import { RouteEconomicsCharts } from '../ui/RouteEconomicsCharts'
import { ObservationComparison } from '../ui/ObservationComparison'
import { EvaluationChart } from '../ui/EvaluationChart'
import { Button } from '../ui/Button'
import history from './historyFixture.json'
import fixtures from './presentationFixtures.json'
import type { PresentationAnalysis, PresentationWorkspace_Holding, PresentationWorkspace_EvaluationRecord, RouteDecision } from '../types/backend.generated'
const route=fixtures.route as RouteDecision
const holdings=fixtures.workspace.holdings as PresentationWorkspace_Holding[]
afterEach(()=>vi.unstubAllGlobals())
it('joins complete regular-session boundaries using session slots without generating observations',()=>{
 const times=['2026-10-05T19:50:00Z','2026-10-05T19:55:00Z','2026-10-06T13:30:00Z','2026-10-06T13:35:00Z']
 const geometry=sessionGeometry(times,[100,101,102,103],720)
 expect(geometry.path.match(/M/g)).toHaveLength(1)
 expect(geometry.path.match(/L/g)).toHaveLength(3)
 expect(geometry.x(2)-geometry.x(1)).toBeCloseTo(geometry.x(1)-geometry.x(0))
 expect(geometry.gaps).toBe(0)
})
it('keeps intraday, incomplete session and missing whole-date gaps separate',()=>{
 for(const times of [ ['2026-10-05T13:30:00Z','2026-10-05T13:40:00Z'], ['2026-10-05T19:50:00Z','2026-10-06T13:30:00Z'], ['2026-10-05T19:55:00Z','2026-10-07T13:30:00Z'] ]) {
  const geometry=sessionGeometry(times,[100,101],720)
  expect(geometry.path.match(/M/g)).toHaveLength(2);expect(geometry.area.match(/Z/g)).toHaveLength(2);expect(geometry.gaps).toBe(1)
 }
})
it('period controls change the captured observations and accessible cursor without additional provider requests',async()=>{
 const fetch=vi.fn().mockResolvedValue(new Response(JSON.stringify(history),{status:200}));vi.stubGlobal('fetch',fetch)
 const view=render(<QueryClientProvider client={new QueryClient({defaultOptions:{queries:{retry:false}}})}><HistoricalChart ticker="NVDA"/></QueryClientProvider>)
 await screen.findByRole('img',{name:/actual five-minute/})
 expect(screen.getByRole('slider')).toHaveAttribute('max','2')
 fireEvent.click(screen.getByRole('button',{name:'1D'}))
 expect(screen.getByRole('slider')).toHaveAttribute('max','0');expect(screen.getByRole('button',{name:'1D'})).toHaveAttribute('aria-pressed','true')
 expect(view.container.querySelector('.price-line')?.getAttribute('d')?.match(/M/g)).toHaveLength(1)
 expect(screen.getByText(/historical prices with as-of ratios/)).toBeInTheDocument()
 fireEvent.click(screen.getByRole('button',{name:'1W'}));expect(screen.getByRole('slider')).toHaveAttribute('max','2');expect(fetch).toHaveBeenCalledTimes(1)
})
it('uses local company assets, honest model issuer initials and safe image fallbacks',()=>{
 const view=render(<AssetIdentity ticker="NVDA" issuer="Atlas model"/>)
 expect(view.container.querySelector('img')).toHaveAttribute('src','/brands/nvda.ico')
 expect(screen.getByLabelText('Atlas model issuer identity')).toHaveTextContent('A')
 fireEvent.error(view.container.querySelector('img')!);expect(view.container.querySelector('img')).toBeNull();expect(screen.getByLabelText('Nvidia identity')).toHaveTextContent('NV')
 view.rerender(<AssetLogo ticker="UNKNOWN"/>);expect(screen.getByLabelText('UNKNOWN identity')).toHaveTextContent('UN')
 view.rerender(<IssuerLogo issuer="Ondo"/>);expect(view.container.querySelector('img')).toHaveAttribute('src','/brands/ondo.ico')
})
it('allocation slices and legend use identical backend weights and values; filtering retains full total',()=>{
 const view=render(<PortfolioDonut holdings={holdings} total={fixtures.workspace.portfolio_value}/>)
 const slices=view.container.querySelectorAll('.allocation-slice');expect(slices).toHaveLength(holdings.length)
 slices.forEach((s,i)=>expect(s.getAttribute('stroke-dasharray')?.split(' ')[0]).toBe(String(Number(holdings[i].weight))))
 expect(holdings.reduce((sum,h)=>sum+Number(h.weight),0)).toBeCloseTo(1)
 const first=screen.getAllByRole('button')[0];fireEvent.focus(first)
 expect(view.container.querySelector('.donut-value')).toHaveTextContent(new Intl.NumberFormat('en-US',{style:'currency',currency:'USD'}).format(Number(holdings[0].value)))
 fireEvent.blur(first);view.rerender(<PortfolioDonut holdings={holdings} total={fixtures.workspace.portfolio_value} filter="AAPL"/>)
 expect(view.container.querySelector('.donut-value')).toHaveTextContent('$812.92');expect(view.container.querySelector('.allocation-slice')).toHaveAttribute('opacity','0.35')
 expect(screen.getByText(/AAPL table filter highlighted/)).toBeInTheDocument()
})
it('empty allocation has no fabricated slices',()=>{
 const view=render(<PortfolioDonut holdings={[]} total="0"/>);expect(view.container.querySelectorAll('.allocation-slice')).toHaveLength(0);expect(screen.getByText('No valued holdings to display.')).toBeInTheDocument();expect(screen.getByText('$0.00')).toBeInTheDocument()
})
it('route charts reconcile exact backend economics, synchronize inspection and preserve selected proposal',()=>{
 const view=render(<RouteEconomicsCharts route={route}/>)
 const graphs=screen.getAllByRole('figure');expect(graphs).toHaveLength(2)
 for(const graph of graphs)expect(within(graph).getAllByRole('button')).toHaveLength(route.candidates.length)
 fireEvent.focus(within(graphs[0]).getAllByRole('button')[0])
 expect(view.container.querySelectorAll('.route-bar[data-active="true"]')).toHaveLength(2)
 expect(view.container.querySelectorAll('.route-bar[data-selected="true"]')).toHaveLength(2)
 expect(screen.getByText(/total estimated costs/)).toHaveTextContent('$0.27')
 const changed=structuredClone(route);changed.requested_notional_usd='120';changed.candidates[0].all_in_cost_per_share_usd='105'
 view.rerender(<RouteEconomicsCharts route={changed}/>);expect(screen.getByText(/\$120.00 REQUEST/)).toBeInTheDocument();expect(within(graphs[1]).getAllByText('$105.00')[0]).toBeInTheDocument()
})
it('unknown costs stay empty, rejected and expired routes cannot look selected',()=>{
 const rejected=structuredClone(route);rejected.candidates[0].eligible=false;rejected.candidates[0].all_in_cost_per_share_usd=null;rejected.candidates[0].rejection_reasons=['INSUFFICIENT_LIQUIDITY'];rejected.selected_candidate=null
 const view=render(<RouteEconomicsCharts route={rejected} expired/>)
 expect(screen.getByText('Cost not established')).toBeInTheDocument();expect(view.container.querySelectorAll('[data-selected="true"]')).toHaveLength(0)
 expect(view.container.querySelectorAll('.route-bar[data-eligible="false"]')).toHaveLength(4)
 fireEvent.focus(screen.getAllByRole('button')[0]);expect(screen.getByText('INSUFFICIENT_LIQUIDITY')).toBeInTheDocument()
})
it('two scenario series use separately recorded timestamps and backend-normalized prices without historical interpolation',()=>{
 const analysis=structuredClone(fixtures.workspace.assets[0]) as PresentationAnalysis
 analysis.effective_cost='110';analysis.token_price='55';analysis.share_ratio='.5'
 const view=render(<ObservationComparison analysis={analysis}/>)
 const points=view.container.querySelectorAll('circle[data-series]');expect(points).toHaveLength(2);expect(view.container.querySelector('path')).toBeNull()
 expect(screen.getByText('$110.00')).toBeInTheDocument();expect(screen.getByText(/No token history is inferred/)).toBeInTheDocument()
 const [a,b]=Array.from(points);expect(a.getAttribute('cy')).not.toBe(b.getAttribute('cy'))
 expect(screen.getByText(/Snapshot, not a historical series/)).toBeInTheDocument()
})
it('scorecard plots supplied outcomes, changes with filtered records and invents no performance curve',()=>{
 const records=fixtures.workspace.evaluations as PresentationWorkspace_EvaluationRecord[]
 const view=render(<EvaluationChart records={records}/>)
 expect(view.container.querySelectorAll('circle')).toHaveLength(records.length*2);expect(view.container.querySelector('path')).toBeNull()
 fireEvent.change(screen.getByRole('slider'),{target:{value:'1'}});expect(view.container.querySelector('figcaption')).toHaveTextContent(/Matched|Diverged/)
 view.rerender(<EvaluationChart records={[]}/>);expect(screen.getByText(/No evaluation observations/)).toBeInTheDocument();expect(view.container.querySelector('svg')).toBeNull()
})
it('tertiary actions retain native button semantics and do not create extra actions',()=>{
 const click=vi.fn();render(<Button type="button" className="text-link" onClick={click}>Inspect</Button>);const button=screen.getByRole('button');expect(button).toHaveAttribute('data-variant','tertiary');fireEvent.click(button);expect(click).toHaveBeenCalledTimes(1)
})
it('does not plot a token snapshot or a fake timeline when its source timestamp is missing',()=>{
 const analysis=structuredClone(fixtures.workspace.assets[0]) as PresentationAnalysis
 analysis.trust.representations[0].token_timestamp=null
 const view=render(<ObservationComparison analysis={analysis}/>)
 expect(view.container.querySelectorAll('circle[data-series]')).toHaveLength(1)
 expect(view.container.querySelector('[data-series="token"]')).toBeNull()
 expect(screen.getByText(/Token effective\/share observation not available/)).toBeInTheDocument()
 expect(view.container.querySelectorAll('svg text')).toHaveLength(4)
})
