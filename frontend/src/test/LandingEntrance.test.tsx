import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { StrictMode, useEffect, useState } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { LandingEntrance, isLandingLocation } from '../landing/LandingEntrance'
import { PaperScene } from '../landing/PaperScene'

const renderer = vi.hoisted(() => ({ create: vi.fn(), dispose: vi.fn() }))
vi.mock('../landing/paperRenderer', () => ({ createPaperRenderer: renderer.create }))
let reduce = false
let change: (() => void) | undefined
beforeEach(() => {
  history.replaceState(null, '', '/')
  Object.defineProperty(window, 'scrollY', { configurable: true, value: 0 })
  vi.stubGlobal('scrollTo', vi.fn())
  reduce = false
  vi.stubGlobal('matchMedia', vi.fn(() => ({
    get matches() { return reduce },
    addEventListener: (_: string, fn: () => void) => { change = fn },
    removeEventListener: vi.fn(),
  })))
  renderer.create.mockReset(); renderer.dispose.mockReset()
  renderer.create.mockImplementation((_host, _progress, state) => { state('ready'); return { dispose: renderer.dispose } })
})
afterEach(() => { vi.unstubAllGlobals(); vi.useRealTimers() })

describe('cinematic entrance navigation', () => {
  it('offers semantic copy and a working dashboard entry without remounting the application', async () => {
    let mounts = 0
    function Workspace() {
      const [value, set] = useState('preserved')
      useEffect(() => { mounts++ }, [])
      return <main><h1>Overview</h1><input aria-label="Workspace state" value={value} onChange={e => set(e.target.value)}/></main>
    }
    render(<LandingEntrance><Workspace/></LandingEntrance>)
    expect(screen.getByRole('heading', { name: /Markets move around the clock/ })).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('Workspace state'), { target: { value: 'my existing state' } })
    fireEvent.click(screen.getByRole('link', { name: 'Enter Parity Pulse' }))
    await waitFor(() => expect(screen.queryByText('Drag to turn. Hover to light.')).not.toBeInTheDocument())
    expect(location.hash).toBe('#overview')
    expect(mounts).toBe(1)
    expect(screen.getByLabelText('Workspace state')).toHaveValue('my existing state')
    act(() => { history.replaceState(null, '', '/'); window.dispatchEvent(new PopStateEvent('popstate')) })
    expect(screen.getByRole('link', { name: 'Enter Parity Pulse' })).toBeInTheDocument()
    expect(screen.getByLabelText('Workspace state')).toHaveValue('my existing state')
    expect(mounts).toBe(1)
  })
  it.each(['#markets', '#research', '#demo-sandbox', '?workspace=verified', '?workspace=verified#overview'])('preserves direct workspace URL %s', url => {
    history.replaceState(null, '', '/' + url)
    const restoration = history.scrollRestoration
    render(<LandingEntrance><main>Original workspace</main></LandingEntrance>)
    expect(isLandingLocation()).toBe(false)
    expect(screen.queryByRole('link', { name: 'Enter Parity Pulse' })).not.toBeInTheDocument()
    expect(screen.getByText('Original workspace')).toBeInTheDocument()
    expect(renderer.create).not.toHaveBeenCalled()
    expect(history.scrollRestoration).toBe(restoration)
  })
  it('uses a bounded native scroll reveal, then completes on the existing hash route', async () => {
    vi.useFakeTimers()
    const { container } = render(<LandingEntrance><h1>Overview</h1></LandingEntrance>)
    Object.defineProperty(window, 'scrollY', { configurable: true, value: innerHeight * .5 })
    fireEvent.scroll(window)
    await act(() => vi.advanceTimersByTimeAsync(30))
    expect(container.firstElementChild?.getAttribute('style')).toContain('--entrance-progress: 0.5')
    expect(location.hash).toBe('')
    Object.defineProperty(window, 'scrollY', { configurable: true, value: innerHeight })
    fireEvent.scroll(window)
    await act(() => vi.advanceTimersByTimeAsync(30))
    expect(location.hash).toBe('#overview')
    expect(screen.queryByRole('link', { name: 'Enter Parity Pulse' })).not.toBeInTheDocument()
  })
})

describe('paper lifecycle and fallbacks', () => {
  it('survives StrictMode effect replay without duplicate renderers', async () => {
    const view = render(<StrictMode><PaperScene progress={{ current: 0 }}/></StrictMode>)
    await waitFor(() => expect(renderer.create).toHaveBeenCalledTimes(1))
    view.unmount()
    expect(renderer.dispose).toHaveBeenCalledTimes(1)
  })
  it('creates once and disposes owned renderer on unmount', async () => {
    const view = render(<PaperScene progress={{ current: 0 }}/>)
    await waitFor(() => expect(renderer.create).toHaveBeenCalledTimes(1))
    expect(view.container.firstElementChild).toHaveAttribute('data-render-state', 'ready')
    view.unmount()
    expect(renderer.dispose).toHaveBeenCalledTimes(1)
  })
  it('does not load a renderer for reduced motion, and handles preference changes', async () => {
    reduce = true
    const view = render(<PaperScene progress={{ current: 0 }}/>)
    expect(view.container.firstElementChild).toHaveAttribute('data-render-state', 'fallback')
    expect(renderer.create).not.toHaveBeenCalled()
    act(() => { reduce = false; change?.() })
    await waitFor(() => expect(renderer.create).toHaveBeenCalledTimes(1))
    act(() => { reduce = true; change?.() })
    expect(renderer.dispose).toHaveBeenCalledTimes(1)
    expect(view.container.firstElementChild).toHaveAttribute('data-render-state', 'fallback')
  })
  it('retains the brand fallback and entry action when WebGL initialization fails', async () => {
    renderer.create.mockImplementation(() => { throw new Error('No WebGL context') })
    const view = render(<LandingEntrance><h1>Overview</h1></LandingEntrance>)
    await waitFor(() => expect(view.container.querySelector('.landing-paper')).toHaveAttribute('data-render-state', 'fallback'))
    expect(screen.getByRole('link', { name: 'Enter Parity Pulse' })).toHaveAttribute('href', '#overview')
  })
  it('ignores asynchronous initialization after unmount', async () => {
    const view = render(<PaperScene progress={{ current: 0 }}/>)
    view.unmount()
    await act(() => Promise.resolve())
    expect(renderer.create).not.toHaveBeenCalled()
  })
})
