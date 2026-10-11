import { useState, type ComponentProps, type PointerEvent } from 'react'

type Variant = 'primary' | 'secondary' | 'outline' | 'icon' | 'compact' | 'destructive' | 'tertiary'

function useRipple() {
  const [ripple, setRipple] = useState<{ x: number; y: number; id: number } | null>(null)
  return {
    start(event: PointerEvent<HTMLElement>) {
      if (event.button !== 0 || typeof window.matchMedia !== 'function' || window.matchMedia('(prefers-reduced-motion: reduce)').matches) return
      const rect = event.currentTarget.getBoundingClientRect()
      setRipple({ x: event.clientX - rect.left, y: event.clientY - rect.top, id: event.timeStamp })
    },
    node: ripple && <span key={ripple.id} aria-hidden="true" className="metal-ripple" style={{ left: ripple.x, top: ripple.y }} onAnimationEnd={() => setRipple(null)} />,
  }
}

/** Native semantics and handlers are preserved; visual effects never invoke actions. */
export function Button({ variant, loading = false, className = '', children, onPointerDown, disabled, ...props }:
  ComponentProps<'button'> & { variant?: Variant; loading?: boolean }) {
  const ripple = useRipple()
  const style = variant ?? (className.includes('primary-button') ? 'primary' : className.includes('text-link') ? 'tertiary' : 'secondary')
  return <button {...props} className={`pp-button ${className}`} data-variant={style} disabled={disabled || loading} aria-busy={loading || undefined}
    onPointerDown={event => { onPointerDown?.(event); if (!event.defaultPrevented && !disabled && !loading) ripple.start(event) }}>
    {loading && <span className="button-spinner" aria-hidden="true" />}{children}{ripple.node}
  </button>
}

export function MetalLink({ className = '', children, onPointerDown, ...props }: ComponentProps<'a'>) {
  const ripple = useRipple()
  return <a {...props} className={`pp-button ${className}`} data-variant="primary" onPointerDown={event => { onPointerDown?.(event); if (!event.defaultPrevented) ripple.start(event) }}>
    {children}{ripple.node}
  </a>
}
