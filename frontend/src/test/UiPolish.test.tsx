import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, expect, it, vi } from 'vitest'
import { HistoricalChart } from '../ui/HistoricalChart'
import { AmbientBackground } from '../ui/AmbientBackground'
import { Button } from '../ui/Button'
import history from './historyFixture.json'

// Three genuine captured bars exercise geometry only, never count as Trust evidence.
afterEach(()=>vi.unstubAllGlobals())
const mountChart=()=>render(<QueryClientProvider client={new QueryClient({defaultOptions:{queries:{retry:false}}})}><HistoricalChart ticker="NVDA"/></QueryClientProvider>)
it('renders only observed historical closes, leaves overnight gaps and exposes keyboard/touch inspection',async()=>{
  const fetch=vi.fn().mockResolvedValue(new Response(JSON.stringify(history),{status:200}))
  vi.stubGlobal('fetch',fetch)
  const view=mountChart()
  const chart=await screen.findByRole('img',{name:/actual five-minute/})
  expect(screen.getByText('Alpaca / SIP · historical, not live')).toBeInTheDocument()
  expect(view.container.querySelector('svg path')?.getAttribute('d')?.match(/M/g)).toHaveLength(2)
  const slider=screen.getByRole('slider',{name:'Inspect NVDA historical bar'})
  fireEvent.change(slider,{target:{value:'0'}})
  expect(slider.getAttribute('aria-valuetext')).toContain('05 Oct, 13:30 UTC')
  fireEvent.pointerMove(chart,{clientX:100})
  expect(screen.getByText(/Underlying equity close/)).toBeInTheDocument()
  expect(fetch.mock.calls[0][0]).toBe('/api/display-history/NVDA')
  expect(fetch.mock.calls).toHaveLength(1)
})
it('keeps unavailable and malformed history empty rather than substituting a curve',async()=>{
  vi.stubGlobal('fetch',vi.fn().mockResolvedValue(new Response(JSON.stringify({...history,production_reference_eligible:true}),{status:200})))
  const view=mountChart()
  await screen.findByText('Historical series not captured.')
  expect(view.container.querySelector('svg')).toBeNull()
  expect(screen.getByText(/No invented price curve/)).toBeInTheDocument()
})
it('button effects never submit actions, loading prevents clicks and keyboard keeps native semantics',async()=>{
  vi.stubGlobal('matchMedia',vi.fn(()=>({matches:false})))
  const clicked=vi.fn(), submitted=vi.fn((e: React.FormEvent)=>e.preventDefault())
  const view=render(<form onSubmit={submitted}><Button onClick={clicked} variant="primary">Prepare proposal</Button></form>)
  const button=screen.getByRole('button',{name:'Prepare proposal'})
  fireEvent.pointerDown(button,{button:0,clientX:20,clientY:20})
  expect(clicked).not.toHaveBeenCalled();expect(submitted).not.toHaveBeenCalled()
  fireEvent.click(button)
  expect(clicked).toHaveBeenCalledTimes(1);expect(submitted).toHaveBeenCalledTimes(1)
  view.rerender(<Button loading onClick={clicked}>Prepare proposal</Button>)
  expect(screen.getByRole('button')).toBeDisabled()
  expect(screen.getByRole('button')).toHaveAttribute('aria-busy','true')
  fireEvent.click(screen.getByRole('button'));expect(clicked).toHaveBeenCalledTimes(1)
})
it('ambient layer uses static low-power/reduced-motion fallbacks, pauses while hidden and cleans listeners',async()=>{
  let reduced=false, hidden=false
  const media=new EventTarget(), connection=Object.assign(new EventTarget(),{saveData:false})
  const remove=vi.spyOn(media,'removeEventListener')
  Object.defineProperty(media,'matches',{get:()=>reduced})
  vi.stubGlobal('matchMedia',()=>media)
  Object.defineProperty(document,'hidden',{configurable:true,get:()=>hidden})
  Object.defineProperty(navigator,'hardwareConcurrency',{configurable:true,value:8})
  Object.defineProperty(navigator,'connection',{configurable:true,value:connection})
  const view=render(<AmbientBackground/>)
  const background=view.container.firstElementChild!
  expect(background).toHaveAttribute('data-motion','running')
  act(()=>{hidden=true;document.dispatchEvent(new Event('visibilitychange'))})
  expect(background).toHaveAttribute('data-motion','paused')
  act(()=>{hidden=false;connection.saveData=true;connection.dispatchEvent(new Event('change'))})
  expect(background).toHaveAttribute('data-motion','static')
  act(()=>{connection.saveData=false;reduced=true;media.dispatchEvent(new Event('change'))})
  await waitFor(()=>expect(background).toHaveAttribute('data-motion','static'))
  expect(background).toHaveAttribute('aria-hidden','true')
  view.unmount();expect(remove).toHaveBeenCalledWith('change',expect.any(Function))
  delete (document as unknown as Record<string,unknown>).hidden
  delete (navigator as unknown as Record<string,unknown>).connection
})

it('read refresh prevents concurrent reads and distinguishes a completed read from updated provider prices',async()=>{
  const { ReadRefresh } = await import('../ui/ReadRefresh')
  let resolve!: (result:{isError:boolean})=>void
  const refetch=vi.fn(()=>new Promise<{isError:boolean}>(r=>{resolve=r}))
  render(<ReadRefresh refetch={refetch} busy={false}>Refresh evidence</ReadRefresh>)
  fireEvent.click(screen.getByRole('button',{name:'Refresh evidence'}))
  fireEvent.click(screen.getByRole('button',{name:'Refresh evidence'}))
  expect(refetch).toHaveBeenCalledTimes(1)
  expect(screen.getByRole('button')).toBeDisabled()
  await act(async()=>resolve({isError:false}))
  expect(screen.getByRole('status')).toHaveTextContent('this does not poll providers')
  expect(screen.getByRole('button')).toBeEnabled()
})
