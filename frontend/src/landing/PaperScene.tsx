import { useEffect, useRef, useState, type MutableRefObject } from 'react'
import type { PaperController, PaperState } from './paperRenderer'

// Share the module request across StrictMode replay and fast back/forward navigation.
let rendererModule: Promise<typeof import('./paperRenderer')> | undefined
const loadRenderer = () => rendererModule ??= import('./paperRenderer')

export function PaperScene({ progress }: { progress: MutableRefObject<number> }) {
  const host = useRef<HTMLDivElement>(null)
  const [state, setState] = useState<PaperState>('loading')
  useEffect(() => {
    let active = true, renderer: PaperController | undefined
    const motion = matchMedia('(prefers-reduced-motion: reduce)')
    const update = () => {
      renderer?.dispose(); renderer = undefined
      if (motion.matches) { setState('fallback'); return }
      setState('loading')
      // Separate chunk: deep links and reduced-motion never download Three.js.
      void loadRenderer().then(({ createPaperRenderer }) => {
        if (!active || motion.matches || !host.current || renderer) return
        try { renderer = createPaperRenderer(host.current, progress, value => { if (active) setState(value) }) }
        catch { if (active) setState('fallback') }
      }).catch(() => { if (active) setState('fallback') })
    }
    update(); motion.addEventListener('change', update)
    return () => { active = false; motion.removeEventListener('change', update); renderer?.dispose() }
  }, [progress])
  return <div className="landing-paper" ref={host} data-render-state={state} aria-hidden="true">
    <div className="landing-paper-fallback"><span className="paper-monogram">PARITY PULSE</span><span className="paper-category">TOKENIZED EQUITY<br/>INTELLIGENCE</span><strong>Clarity,<br/>before<br/><em>exposure.</em></strong><div className="paper-note">Evidence over impulse.<small>Independent intelligence<br/>for tokenized equities.</small></div><span className="paper-signature">PARITY PULSE</span></div>
  </div>
}
