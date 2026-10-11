import {
  DoubleSide, Mesh, PerspectiveCamera, PlaneGeometry, Scene, ShaderMaterial,
  Vector3, WebGLRenderer,
} from 'three'
import { createPaperTexture } from './paperTexture'
import { paperFragment, paperVertex } from './paperShaders'

export type PaperController = { dispose: () => void }
export type PaperState = 'loading' | 'ready' | 'paused' | 'fallback'

/** Owns all GPU resources and listeners. React never participates in the render loop. */
export function createPaperRenderer(
  host: HTMLElement,
  progress: { current: number },
  state: (state: PaperState) => void,
): PaperController {
  const compact = matchMedia('(max-width: 767px)').matches
  const canvas = document.createElement('canvas')
  const context = canvas.getContext('webgl2', { alpha: true, antialias: !compact, powerPreference: 'low-power' })
  if (!context) throw new Error('WebGL unavailable')
  const renderer = new WebGLRenderer({ canvas, context, alpha: true, antialias: !compact, powerPreference: 'low-power' })
  const scene = new Scene()
  const camera = new PerspectiveCamera(32, 1, .1, 30)
  camera.position.z = 8.5
  const geometry = new PlaneGeometry(2.3, 3.1, compact ? 36 : 56, compact ? 48 : 72)
  let texture: ReturnType<typeof createPaperTexture> | undefined
  let material: ShaderMaterial | undefined
  let frame = 0, disposed = false, broken = false, visible = true, previous = 0, elapsed = 0
  let resizeObserver: ResizeObserver | undefined, intersection: IntersectionObserver | undefined
  const listeners: (() => void)[] = []
  canvas.setAttribute('aria-hidden', 'true')
  canvas.dataset.paperCanvas = ''
  const dispose = () => {
    if (disposed) return
    disposed = true
    cancelAnimationFrame(frame)
    resizeObserver?.disconnect(); intersection?.disconnect()
    for (const remove of listeners) remove()
    geometry.dispose(); texture?.dispose(); material?.dispose()
    renderer.dispose(); renderer.forceContextLoss(); canvas.remove()
  }
  const fail = () => {
    if (disposed || broken) return
    broken = true
    state('fallback')
    // A lost context or shader failure must never take down the application.
    queueMicrotask(dispose)
  }
  const listen = <K extends keyof HTMLElementEventMap>(target: HTMLElement, event: K, handler: (event: HTMLElementEventMap[K]) => void) => {
    target.addEventListener(event, handler)
    listeners.push(() => target.removeEventListener(event, handler))
  }
  try {
    texture = createPaperTexture(compact)
    material = new ShaderMaterial({
      vertexShader: paperVertex, fragmentShader: paperFragment,
      uniforms: { uTime: { value: 0 }, uProgress: { value: 0 }, uPrint: { value: texture }, uLight: { value: new Vector3(1.5, 2.5, 5) } },
      transparent: true, side: DoubleSide, depthWrite: false,
    })
    renderer.debug.onShaderError = fail
    renderer.setClearColor(0x050908, 0)
    host.appendChild(canvas)
    const paper = new Mesh(geometry, material)
    scene.add(paper)
    const light = material.uniforms.uLight.value as Vector3
    const pointer = { x: 0, y: 0 }, eased = { x: 0, y: 0 }
    let yaw = -.12, pitch = .04, targetYaw = -.12, targetPitch = .04
    let drag: { id: number; x: number; y: number } | null = null
    let width = 1, height = 1, scale = 1, centerX = 0, centerY = 0
    const clamp = (n: number, max: number) => Math.max(-max, Math.min(max, n))
    const resize = () => {
      width = Math.max(1, host.clientWidth); height = Math.max(1, host.clientHeight)
      const small = width < 768
      renderer.setPixelRatio(Math.min(devicePixelRatio || 1, small ? 1.25 : 1.75))
      renderer.setSize(width, height)
      camera.aspect = width / height; camera.updateProjectionMatrix()
      const worldHeight = 2 * Math.tan(32 * Math.PI / 360) * camera.position.z
      const heightFraction = small ? (height < 740 ? .47 : .54) : .66
      const targetHeight = Math.min(height * heightFraction, width * (small ? .80 : .48) * 3.1 / 2.3)
      scale = targetHeight / height * worldHeight / 3.1
      centerX = small ? 0 : worldHeight * camera.aspect * .035
      centerY = worldHeight * (small ? .13 : .07)
      // First frame after a resize uses the new projection, including orientation changes.
    }
    const tick = (now: number) => {
      frame = 0
      if (disposed || broken || !visible || document.hidden) return
      const dt = Math.min((now - previous) / 1000 || 0, .04); previous = now; elapsed += dt
      const blend = 1 - Math.exp(-dt * 7)
      eased.x += (pointer.x - eased.x) * blend; eased.y += (pointer.y - eased.y) * blend
      if (!drag) {
        targetYaw += (-.12 - targetYaw) * dt * .8
        targetPitch += (.04 - targetPitch) * dt * .8
      }
      yaw += (targetYaw - yaw) * blend; pitch += (targetPitch - pitch) * blend
      const p = Math.max(0, Math.min(1, progress.current))
      material!.uniforms.uTime.value = elapsed
      material!.uniforms.uProgress.value = p
      light.set(1.5 + eased.x * 4, 2.5 - eased.y * 4, 5)
      paper.rotation.set(pitch + eased.y * .035 + p * .2, yaw + eased.x * .06 - p * .12, -.025 + Math.sin(elapsed * .3) * .008)
      paper.position.set(centerX, centerY + Math.sin(elapsed * .4) * .035 + p * .3, -p * 2.4)
      paper.scale.setScalar(scale * (1 - p * .13))
      try { renderer.render(scene, camera) } catch { fail(); return }
      if (!broken) frame = requestAnimationFrame(tick)
    }
    const resume = () => {
      cancelAnimationFrame(frame); frame = 0; previous = performance.now()
      if (disposed || broken) return
      state(visible && !document.hidden ? 'ready' : 'paused')
      if (visible && !document.hidden) frame = requestAnimationFrame(tick)
    }
    listen(host, 'pointermove', event => {
      const box = host.getBoundingClientRect()
      pointer.x = clamp((event.clientX - box.left) / width * 2 - 1, 1)
      pointer.y = clamp((event.clientY - box.top) / height * 2 - 1, 1)
      if (!drag || event.pointerId !== drag.id) return
      targetYaw = clamp(targetYaw + (event.clientX - drag.x) * .0035, .55)
      targetPitch = clamp(targetPitch + (event.clientY - drag.y) * .002, .25)
      drag.x = event.clientX; drag.y = event.clientY
    })
    listen(host, 'pointerdown', event => {
      if (event.button !== 0) return
      const rect = host.getBoundingClientRect()
      const x = (event.clientX - rect.left) / width
      const y = (event.clientY - rect.top) / height
      if (Math.abs(x - (width < 768 ? .5 : .535)) > .3 || y < .08 || y > .78) return
      drag = { id: event.pointerId, x: event.clientX, y: event.clientY }
      host.setPointerCapture(event.pointerId)
      host.dataset.dragging = 'true'
    })
    const release = () => {
      const id = drag?.id
      drag = null; delete host.dataset.dragging
      if (id !== undefined && host.hasPointerCapture(id)) host.releasePointerCapture(id)
    }
    listeners.push(release)
    listen(host, 'pointerup', release); listen(host, 'pointercancel', release)
    listen(host, 'lostpointercapture', release)
    listen(host, 'pointerleave', () => { if (!drag) { pointer.x = 0; pointer.y = 0 } })
    const contextLost = (event: Event) => { event.preventDefault(); fail() }
    canvas.addEventListener('webglcontextlost', contextLost)
    listeners.push(() => canvas.removeEventListener('webglcontextlost', contextLost))
    document.addEventListener('visibilitychange', resume)
    listeners.push(() => document.removeEventListener('visibilitychange', resume))
    window.addEventListener('resize', resize)
    listeners.push(() => window.removeEventListener('resize', resize))
    if (typeof ResizeObserver !== 'undefined') { resizeObserver = new ResizeObserver(resize); resizeObserver.observe(host) }
    if (typeof IntersectionObserver !== 'undefined') {
      intersection = new IntersectionObserver(entries => { visible = entries[0]?.isIntersecting ?? true; resume() })
      intersection.observe(host)
    }
    resize(); resume()
    return { dispose }
  } catch (error) {
    dispose()
    throw error
  }
}
