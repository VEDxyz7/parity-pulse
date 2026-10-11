import { CanvasTexture, SRGBColorSpace } from 'three'

/** Print is local, deterministic brand artwork, never a market observation. */
export function createPaperTexture(compact: boolean) {
  const canvas = document.createElement('canvas')
  const scale = compact ? 1 : 1.5
  canvas.width = 1000 * scale
  canvas.height = 1350 * scale
  const ctx = canvas.getContext('2d')
  if (!ctx) throw new Error('Paper texture unavailable')
  ctx.scale(scale, scale)
  const text = (value: string, x: number, y: number, size: number, weight = 500, color = '#F1F7F4') => {
    ctx.fillStyle = color
    ctx.font = `${weight} ${size}px Arial, sans-serif`
    ctx.fillText(value, x, y)
  }
  for (const [inset, opacity] of [[16, .42], [29, .14]]) {
    ctx.strokeStyle = `rgba(168,230,202,${opacity})`
    ctx.lineWidth = 1.3
    ctx.beginPath()
    ctx.roundRect(inset, inset, 1000 - inset * 2, 1350 - inset * 2, 12)
    ctx.stroke()
  }
  text('PARITY PULSE', 74, 145, 40, 650)
  text('TOKENIZED EQUITY', 74, 277, 23, 500, '#ACD1BC')
  text('INTELLIGENCE', 74, 310, 23, 500, '#ACD1BC')
  text('Clarity,', 66, 486, 130, 500)
  text('before', 66, 626, 130, 500)
  text('exposure.', 66, 766, 130, 500, '#9AEAC4')
  ctx.strokeStyle = 'rgba(160,221,191,.28)'
  ctx.beginPath(); ctx.moveTo(76, 851); ctx.lineTo(925, 851); ctx.stroke()
  text('Evidence over impulse.', 510, 977, 25, 600)
  text('Independent intelligence', 510, 1018, 22, 400, '#BDCEC3')
  text('for tokenized equities.', 510, 1048, 22, 400, '#BDCEC3')
  // Abstract engraved contour, deliberately not a financial price chart.
  ctx.beginPath()
  for (let i = 0; i <= 170; i++) {
    const x = 510 + i * 2.4
    const y = 1106 + Math.sin(i * .06) * 8 + Math.sin(i * .14) * 4
    if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y)
  }
  ctx.strokeStyle = 'rgba(154,234,196,.65)'; ctx.stroke()
  text('PARITY PULSE', 74, 1246, 28, 600)
  const texture = new CanvasTexture(canvas)
  texture.colorSpace = SRGBColorSpace
  return texture
}
