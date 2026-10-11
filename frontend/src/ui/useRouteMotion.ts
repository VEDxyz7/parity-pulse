import { useEffect, type RefObject } from 'react'

/** Financial content is visible immediately. Animate only a small heading translation. */
export function useRouteMotion(route: string, root: RefObject<HTMLElement | null>) {
  useEffect(() => {
    if (typeof window.matchMedia !== 'function') return
    let active = true
    let cleanup: (() => void) | undefined
    const reduced = matchMedia('(prefers-reduced-motion: reduce)')
    const stop = () => { cleanup?.(); cleanup = undefined }
    const start = () => {
      stop()
      if (reduced.matches || document.hidden) return
      void import('gsap').then(({ gsap }) => {
        if (!active || reduced.matches || document.hidden || !root.current) return
        stop()
        const context = gsap.context(() => {
          gsap.fromTo('main .page-heading > div, main > .workspace-view > h1', { y: 8 }, { y: 0, duration: .35, ease: 'power2.out', clearProps: 'transform' })
        }, root.current)
        cleanup = () => context.revert()
      }).catch(() => { /* Static layout is fully usable if the optional chunk fails. */ })
    }
    start()
    reduced.addEventListener('change', start)
    document.addEventListener('visibilitychange', start)
    return () => { active = false; stop(); reduced.removeEventListener('change', start); document.removeEventListener('visibilitychange', start) }
  }, [route, root])
}
