import { useEffect, useState } from 'react'

/** One compositor-only background, no WebGL context, RAF loop or financial state. */
export function AmbientBackground() {
  const [motion, setMotion] = useState('static')
  const [section, setSection] = useState(location.hash.slice(1) || 'overview')
  useEffect(() => {
    if (typeof window.matchMedia !== 'function') return
    const reduced = matchMedia('(prefers-reduced-motion: reduce)')
    const connection = (navigator as Navigator & { connection?: EventTarget & { saveData?: boolean } }).connection
    const update = () => setMotion(reduced.matches || connection?.saveData || navigator.hardwareConcurrency <= 2 ? 'static' : document.hidden ? 'paused' : 'running')
    const navigate = () => setSection(location.hash.slice(1) || 'overview')
    update()
    reduced.addEventListener('change', update)
    connection?.addEventListener('change', update)
    document.addEventListener('visibilitychange', update)
    window.addEventListener('hashchange', navigate)
    return () => {
      reduced.removeEventListener('change', update)
      connection?.removeEventListener('change', update)
      document.removeEventListener('visibilitychange', update)
      window.removeEventListener('hashchange', navigate)
    }
  }, [])
  return <div className="ambient-background" aria-hidden="true" data-motion={motion} data-section={section}><div className="ambient-light ambient-one" /><div className="ambient-light ambient-two" /><div className="ambient-grain" /></div>
}
