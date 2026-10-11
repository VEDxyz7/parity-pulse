import { useEffect, useRef, useState, type ReactNode } from 'react'
import { Activity, ArrowDown } from 'lucide-react'
import { PaperScene } from './PaperScene'
import { AmbientBackground } from '../ui/AmbientBackground'
import './landing.css'

export function isLandingLocation() {
  return new URLSearchParams(location.search).get('workspace') !== 'verified'
    && (!location.hash || location.hash === '#landing')
}

/** Hash routes remain owned by the existing application. Its instance never remounts. */
export function LandingEntrance({ children }: { children: ReactNode }) {
  const [landing, setLanding] = useState(isLandingLocation)
  const root = useRef<HTMLDivElement>(null)
  const dashboard = useRef<HTMLDivElement>(null)
  const progress = useRef(0)
  const lastLanding = useRef(landing)

  useEffect(() => {
    const restoration = history.scrollRestoration
    if (lastLanding.current) history.scrollRestoration = 'manual'
    let focusFrame = 0
    const navigate = () => {
      const next = isLandingLocation()
      if (next !== lastLanding.current) {
        history.scrollRestoration = next ? 'manual' : restoration
        window.scrollTo({ top: 0, behavior: 'instant' })
        cancelAnimationFrame(focusFrame)
        focusFrame = requestAnimationFrame(() => {
          if (next) { root.current?.querySelector<HTMLElement>('#landing-title')?.focus({ preventScroll: true }); return }
          const heading = dashboard.current?.querySelector<HTMLElement>('h1')
          heading?.setAttribute('tabindex', '-1')
          heading?.focus({ preventScroll: true })
        })
      }
      lastLanding.current = next; setLanding(next)
    }
    window.addEventListener('hashchange', navigate)
    window.addEventListener('popstate', navigate)
    return () => { cancelAnimationFrame(focusFrame); history.scrollRestoration = restoration; window.removeEventListener('hashchange', navigate); window.removeEventListener('popstate', navigate) }
  }, [])

  useEffect(() => {
    if (!landing) return
    let frame = 0
    const update = () => {
      frame = 0
      const height = root.current?.querySelector<HTMLElement>('.landing-spacer')?.offsetHeight || innerHeight
      progress.current = Math.max(0, Math.min(1, scrollY / height))
      root.current?.style.setProperty('--entrance-progress', String(progress.current))
      if (scrollY >= height - 1 && scrollY > 0) location.hash = '#overview'
    }
    const schedule = () => { if (!frame) frame = requestAnimationFrame(update) }
    // Passive native scroll: no wheel interception, pinned timeline or scroll lock.
    window.addEventListener('scroll', schedule, { passive: true })
    window.addEventListener('resize', schedule)
    update()
    return () => { cancelAnimationFrame(frame); window.removeEventListener('scroll', schedule); window.removeEventListener('resize', schedule) }
  }, [landing])

  return <div ref={root} className={`landing-entrance${landing ? ' entrance-active' : ''}`}>
    {landing && <><section className="landing-hero" aria-labelledby="landing-title">
      <div className="landing-wordmark" aria-hidden="true">PARITY PULSE</div>
      <div className="landing-halo" aria-hidden="true"/>
      <PaperScene progress={progress}/>
      <div className="landing-vignette" aria-hidden="true"/>
      <header className="landing-header"><span className="landing-brand"><Activity size={22} strokeWidth={1.5}/> PARITY PULSE</span><span className="landing-eyebrow">TOKENIZED EQUITY INTELLIGENCE</span></header>
      <div className="landing-copy"><h1 id="landing-title" tabIndex={-1}>Markets move around the clock.<br/><span>Evidence brings them into focus.</span></h1><p>Independent intelligence for tokenized equities.</p></div>
      <p className="landing-interaction" aria-hidden="true"><span className="landing-pointer-hint">Drag to turn. Hover to light.</span><span className="landing-touch-hint">Drag sideways to turn.</span></p>
      <span className="landing-scroll" aria-hidden="true"><ArrowDown size={16} strokeWidth={1}/></span>
    </section><div className="landing-spacer" aria-hidden="true"/></>}
    <div ref={dashboard} className="entrance-dashboard"><AmbientBackground/>{children}</div>
  </div>
}
